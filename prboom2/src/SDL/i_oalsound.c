//
// Copyright(C) 2026 by George Merlocco
//
// This program is free software; you can redistribute it and/or
// modify it under the terms of the GNU General Public License
// as published by the Free Software Foundation; either version 2
// of the License, or (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// DESCRIPTION:
//	OpenAL Soft HRTF sound effects backend
//

#ifdef HAVE_CONFIG_H
#include "config.h"
#endif

#include "i_oalsound.h"
#include "lprintf.h"

#ifdef HAVE_LIBOPENAL

#include <math.h>
#include <string.h>

#include "al.h"
#include "alc.h"
#include "alext.h"
#include "efx.h"

#include "s_sound.h"
#include "z_zone.h"

#include "dsda/sound_occlusion.h"
#include "dsda/spatial_sound.h"

// Stock mixer: full-scale sample at vol 127 lands at 127/191 per side, and a
// centred sound loses ~25% more to the x^2 pan law -> ~0.5. Tune by ear.
#define OAL_GAIN_SCALE 0.5f

static ALCdevice *oal_device;
static ALCcontext *oal_context;
static ALuint oal_sources[MAX_CHANNELS];
static ALuint *oal_buffers; // indexed by sfx id, 0 = not uploaded yet
static int oal_buffer_count;
static dboolean oal_active;

// Occlusion: a low-pass per source, faded toward fully muffled (1) or clear
// (0) by OCCL_STEP per tic (8 tics, ~230 ms). The gains are interpolated in
// dB so each tic changes the sound by the same audible amount. Tune by ear on
// hrtftest WALLS.
#define OCCL_GAIN   0.6f
#define OCCL_GAINHF 0.07f
#define OCCL_STEP   0.125f

static dboolean oal_efx;
static ALuint oal_filters[MAX_CHANNELS];
static float oal_occl[MAX_CHANNELS];
static LPALGENFILTERS p_alGenFilters;
static LPALDELETEFILTERS p_alDeleteFilters;
static LPALFILTERI p_alFilteri;
static LPALFILTERF p_alFilterf;

static void I_OAL_CloseDevice(void)
{
  alcMakeContextCurrent(NULL);

  if (oal_context)
    alcDestroyContext(oal_context);

  if (oal_device)
    alcCloseDevice(oal_device);

  oal_context = NULL;
  oal_device = NULL;
}

static void I_OAL_LogHRTFStatus(void)
{
  ALCint status = ALC_HRTF_DISABLED_SOFT;
  const char *name;
  dboolean on = false;

  alcGetIntegerv(oal_device, ALC_HRTF_STATUS_SOFT, 1, &status);

  switch (status)
  {
    case ALC_HRTF_ENABLED_SOFT:
      name = "enabled"; on = true; break;
    case ALC_HRTF_REQUIRED_SOFT:
      name = "enabled (required by alsoft.conf)"; on = true; break;
    case ALC_HRTF_HEADPHONES_DETECTED_SOFT:
      name = "enabled (headphones detected)"; on = true; break;
    case ALC_HRTF_DENIED_SOFT:
      name = "denied by alsoft.conf"; break;
    case ALC_HRTF_UNSUPPORTED_FORMAT_SOFT:
      name = "unavailable (output is not stereo)"; break;
    case ALC_HRTF_DISABLED_SOFT:
    default:
      name = "disabled"; break;
  }

  if (on)
    lprintf(LO_INFO, "I_OAL_Init: HRTF %s, dataset \"%s\"\n", name,
            alcGetString(oal_device, ALC_HRTF_SPECIFIER_SOFT));
  else
    lprintf(LO_WARN, "I_OAL_Init: HRTF %s; sound effects use plain stereo panning\n", name);
}

static void I_OAL_InitEFX(void)
{
  int i;

  oal_efx = false;

  if (!alcIsExtensionPresent(oal_device, "ALC_EXT_EFX"))
  {
    lprintf(LO_WARN, "I_OAL_Init: ALC_EXT_EFX not supported, occlusion unavailable\n");
    return;
  }

  p_alGenFilters = (LPALGENFILTERS) alGetProcAddress("alGenFilters");
  p_alDeleteFilters = (LPALDELETEFILTERS) alGetProcAddress("alDeleteFilters");
  p_alFilteri = (LPALFILTERI) alGetProcAddress("alFilteri");
  p_alFilterf = (LPALFILTERF) alGetProcAddress("alFilterf");

  if (!p_alGenFilters || !p_alDeleteFilters || !p_alFilteri || !p_alFilterf)
  {
    lprintf(LO_WARN, "I_OAL_Init: EFX filter functions missing, occlusion unavailable\n");
    return;
  }

  alGetError();
  p_alGenFilters(MAX_CHANNELS, oal_filters);
  if (alGetError() != AL_NO_ERROR)
  {
    lprintf(LO_WARN, "I_OAL_Init: couldn't create EFX filters, occlusion unavailable\n");
    return;
  }

  for (i = 0; i < MAX_CHANNELS; i++)
    p_alFilteri(oal_filters[i], AL_FILTER_TYPE, AL_FILTER_LOWPASS);

  if (alGetError() != AL_NO_ERROR)
  {
    lprintf(LO_WARN, "I_OAL_Init: low-pass filter unsupported, occlusion unavailable\n");
    p_alDeleteFilters(MAX_CHANNELS, oal_filters);
    return;
  }

  memset(oal_occl, 0, sizeof(oal_occl));
  oal_efx = true;
}

dboolean I_OAL_Init(void)
{
  ALCint attrs[3] = { 0, 0, 0 };
  int i;

  if (oal_active)
    return true;

  oal_device = alcOpenDevice(NULL);
  if (!oal_device)
  {
    lprintf(LO_WARN, "I_OAL_Init: couldn't open an OpenAL device, using stock mixer\n");
    return false;
  }

  if (alcIsExtensionPresent(oal_device, "ALC_SOFT_HRTF"))
  {
    attrs[0] = ALC_HRTF_SOFT;
    attrs[1] = ALC_TRUE;
  }
  else
    lprintf(LO_WARN, "I_OAL_Init: ALC_SOFT_HRTF not supported by this OpenAL\n");

  oal_context = alcCreateContext(oal_device, attrs);
  if (!oal_context || !alcMakeContextCurrent(oal_context))
  {
    lprintf(LO_WARN, "I_OAL_Init: couldn't create an OpenAL context, using stock mixer\n");
    I_OAL_CloseDevice();
    return false;
  }

  alDistanceModel(AL_NONE);

  alGetError();
  alGenSources(MAX_CHANNELS, oal_sources);
  if (alGetError() != AL_NO_ERROR)
  {
    lprintf(LO_WARN, "I_OAL_Init: couldn't create %d OpenAL sources, using stock mixer\n",
            MAX_CHANNELS);
    I_OAL_CloseDevice();
    return false;
  }

  for (i = 0; i < MAX_CHANNELS; i++)
  {
    alSourcei(oal_sources[i], AL_SOURCE_RELATIVE, AL_TRUE);
    alSourcef(oal_sources[i], AL_ROLLOFF_FACTOR, 0.0f);
  }

  lprintf(LO_INFO, "I_OAL_Init: OpenAL device \"%s\"\n",
          alcGetString(oal_device, ALC_DEVICE_SPECIFIER));
  I_OAL_LogHRTFStatus();
  I_OAL_InitEFX();

  oal_active = true;
  return true;
}

void I_OAL_Shutdown(void)
{
  int i;

  if (!oal_active)
    return;

  for (i = 0; i < MAX_CHANNELS; i++)
  {
    alSourceStop(oal_sources[i]);
    alSourcei(oal_sources[i], AL_BUFFER, 0);
    if (oal_efx)
      alSourcei(oal_sources[i], AL_DIRECT_FILTER, AL_FILTER_NULL);
  }

  if (oal_efx)
  {
    p_alDeleteFilters(MAX_CHANNELS, oal_filters);
    oal_efx = false;
  }

  alDeleteSources(MAX_CHANNELS, oal_sources);

  for (i = 0; i < oal_buffer_count; i++)
    if (oal_buffers[i])
      alDeleteBuffers(1, &oal_buffers[i]);

  Z_Free(oal_buffers);
  oal_buffers = NULL;
  oal_buffer_count = 0;

  I_OAL_CloseDevice();
  oal_active = false;
}

dboolean I_OAL_Active(void)
{
  return oal_active;
}

dboolean I_OAL_OcclusionAvailable(void)
{
  return oal_active && oal_efx;
}

static ALuint I_OAL_GetBuffer(const i_oal_sample_t *sample)
{
  ALuint *slot;

  if (sample->sfxid < 0)
    return 0;

  if (sample->sfxid >= oal_buffer_count)
  {
    int new_count = sample->sfxid + 64;

    oal_buffers = Z_Realloc(oal_buffers, new_count * sizeof(*oal_buffers));
    memset(oal_buffers + oal_buffer_count, 0,
           (new_count - oal_buffer_count) * sizeof(*oal_buffers));
    oal_buffer_count = new_count;
  }

  slot = &oal_buffers[sample->sfxid];
  if (*slot)
    return *slot;

  alGetError();
  alGenBuffers(1, slot);
  alBufferData(*slot, sample->bits == 16 ? AL_FORMAT_MONO16 : AL_FORMAT_MONO8,
               sample->data, sample->length, sample->samplerate);

  if (alGetError() != AL_NO_ERROR)
  {
    lprintf(LO_WARN, "I_OAL_GetBuffer: couldn't upload sfx %d\n", sample->sfxid);
    alDeleteBuffers(1, slot);
    *slot = 0;
  }

  return *slot;
}

// snap: jump straight to the target (new sound), else fade one step (per tic)
static void I_OAL_ApplyOcclusion(int channel, float target, dboolean snap)
{
  ALuint filter = oal_filters[channel];
  float c;

  if (!oal_efx)
    return;

  c = snap ? target : dsda_OcclusionStep(oal_occl[channel], target, OCCL_STEP);
  if (!snap && c == oal_occl[channel])
    return; // unchanged: the attached filter already has these values
  oal_occl[channel] = c;

  // OCCL_GAIN^c: linear in dB from 1 (c = 0) to OCCL_GAIN (c = 1)
  p_alFilterf(filter, AL_LOWPASS_GAIN, powf(OCCL_GAIN, c));
  p_alFilterf(filter, AL_LOWPASS_GAINHF, powf(OCCL_GAINHF, c));
  // filter parameters are copied on attach, so re-attach after every change
  alSourcei(oal_sources[channel], AL_DIRECT_FILTER, filter);
}

static void I_OAL_ApplyParams(int channel, const sfx_params_t *params, float pitch)
{
  ALuint source = oal_sources[channel];
  float pos[3] = { 0.0f, 0.0f, 0.0f };
  float gain = params->volume / 127.0f * OAL_GAIN_SCALE;

  if (gain < 0.0f)
    gain = 0.0f;
  else if (gain > 1.0f)
    gain = 1.0f;

  if (params->spatial)
    dsda_SpatialSoundVector(params->azimuth, params->dist, params->dz,
                            params->listener_pitch, pos);

  alSourcef(source, AL_GAIN, gain);
  alSourcef(source, AL_PITCH, pitch);
  alSourcei(source, AL_LOOPING, params->loop ? AL_TRUE : AL_FALSE);
  alSource3f(source, AL_POSITION, pos[0], pos[1], pos[2]);
}

int I_OAL_StartSound(int channel, const i_oal_sample_t *sample,
                     const sfx_params_t *params, float pitch)
{
  ALuint buffer;

  if (!oal_active || channel < 0 || channel >= MAX_CHANNELS)
    return -1;

  buffer = I_OAL_GetBuffer(sample);
  if (!buffer)
    return -1;

  alSourceStop(oal_sources[channel]);
  alSourcei(oal_sources[channel], AL_BUFFER, buffer);
  I_OAL_ApplyParams(channel, params, pitch);
  I_OAL_ApplyOcclusion(channel, params->occlusion, true);
  alSourcePlay(oal_sources[channel]);

  return channel;
}

void I_OAL_UpdateSoundParams(int channel, const sfx_params_t *params, float pitch)
{
  if (!oal_active || channel < 0 || channel >= MAX_CHANNELS)
    return;

  I_OAL_ApplyParams(channel, params, pitch);
  I_OAL_ApplyOcclusion(channel, params->occlusion, false);
}

void I_OAL_StopSound(int channel)
{
  if (!oal_active || channel < 0 || channel >= MAX_CHANNELS)
    return;

  alSourceStop(oal_sources[channel]);
}

dboolean I_OAL_SoundIsPlaying(int channel)
{
  ALint state;

  if (!oal_active || channel < 0 || channel >= MAX_CHANNELS)
    return false;

  alGetSourcei(oal_sources[channel], AL_SOURCE_STATE, &state);
  return state == AL_PLAYING;
}

dboolean I_OAL_AnySoundStillPlaying(void)
{
  int i;

  for (i = 0; i < MAX_CHANNELS; i++)
    if (I_OAL_SoundIsPlaying(i))
      return true;

  return false;
}

#else // HAVE_LIBOPENAL

dboolean I_OAL_Init(void)
{
  lprintf(LO_WARN, "I_OAL_Init: built without OpenAL, snd_hrtf has no effect\n");
  return false;
}

void I_OAL_Shutdown(void) {}
dboolean I_OAL_Active(void) { return false; }
dboolean I_OAL_OcclusionAvailable(void) { return false; }
int I_OAL_StartSound(int channel, const i_oal_sample_t *sample,
                     const sfx_params_t *params, float pitch) { return -1; }
void I_OAL_UpdateSoundParams(int channel, const sfx_params_t *params, float pitch) {}
void I_OAL_StopSound(int channel) {}
dboolean I_OAL_SoundIsPlaying(int channel) { return false; }
dboolean I_OAL_AnySoundStillPlaying(void) { return false; }

#endif // HAVE_LIBOPENAL
