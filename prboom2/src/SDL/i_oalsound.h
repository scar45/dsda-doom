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

#ifndef __I_OALSOUND__
#define __I_OALSOUND__

#include "doomtype.h"
#include "sounds.h"

typedef struct
{
  int sfxid;
  const unsigned char *data;
  int length;
  int samplerate;
  int bits;
} i_oal_sample_t;

dboolean I_OAL_Init(void);
void I_OAL_Shutdown(void);
dboolean I_OAL_Active(void);
dboolean I_OAL_OcclusionAvailable(void);
int I_OAL_StartSound(int channel, const i_oal_sample_t *sample,
                     const sfx_params_t *params, float pitch);
void I_OAL_UpdateSoundParams(int channel, const sfx_params_t *params, float pitch);
void I_OAL_StopSound(int channel);
dboolean I_OAL_SoundIsPlaying(int channel);
dboolean I_OAL_AnySoundStillPlaying(void);

#endif
