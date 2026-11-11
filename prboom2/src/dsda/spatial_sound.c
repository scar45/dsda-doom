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
//	DSDA Spatial Sound Direction
//

#include <math.h>

#include "spatial_sound.h"

#define SPATIAL_PI 3.14159265358979323846
#define SPATIAL_ANGLE_TO_RAD (2.0 * SPATIAL_PI / 4294967296.0)

void dsda_SpatialSoundVector(angle_t azimuth, fixed_t dist, fixed_t dz,
                             angle_t view_pitch, float out[3])
{
  double yaw, elevation, horizontal, look_up;
  double right, up, ahead;

  if (dist < 0)
    dist = 0;

  if (dist == 0 && dz == 0)
  {
    out[0] = out[1] = out[2] = 0.0f;
    return;
  }

  yaw = (double) azimuth * SPATIAL_ANGLE_TO_RAD;
  elevation = atan2((double) dz, (double) dist);
  horizontal = cos(elevation);

  right = -sin(yaw) * horizontal;
  up = sin(elevation);
  ahead = cos(yaw) * horizontal;

  // Tilt the head with freelook (rotate about the ear-to-ear axis).
  look_up = -(double) (int) view_pitch * SPATIAL_ANGLE_TO_RAD;

  out[0] = (float) right;
  out[1] = (float) (up * cos(look_up) - ahead * sin(look_up));
  out[2] = (float) -(ahead * cos(look_up) + up * sin(look_up));
}
