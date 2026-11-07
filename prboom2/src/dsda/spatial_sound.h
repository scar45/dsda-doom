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

#ifndef __DSDA_SPATIAL_SOUND__
#define __DSDA_SPATIAL_SOUND__

#include "tables.h"

// Converts a listener-relative Doom position into a unit direction vector in
// OpenAL listener space (+x right, +y up, -z ahead).
//   azimuth: source angle minus listener facing (0 ahead, ANG90 left, ANG180 behind)
//   dist:    horizontal listener->source distance, fixed point
//   dz:      source height minus listener eye height, fixed point
// Writes (0, 0, 0) when the source is on the listener (no direction).
void dsda_SpatialSoundVector(angle_t azimuth, fixed_t dist, fixed_t dz, float out[3]);

#endif
