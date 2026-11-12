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
//	DSDA Sound Occlusion
//

#ifndef __DSDA_SOUND_OCCLUSION__
#define __DSDA_SOUND_OCCLUSION__

#include "r_defs.h"

// True if no clear sight line exists from the eye point to any part of the
// target's vertical span [zlo, zhi] at (tx, ty). Read-only on level data: it
// never touches validcount, REJECT, mobjs or the RNG, so it is safe to call
// from anywhere, including inside game traversals.
//   ignore_sector: two-sided lines bordering this sector don't block (the
//                  sound belongs to that sector, e.g. a closed door)
//   ignore_line:   this line never blocks (the sound belongs to it, e.g. a
//                  switch on a one-sided wall)
dboolean dsda_SoundOccluded(fixed_t ex, fixed_t ey, fixed_t ez,
                            fixed_t tx, fixed_t ty, fixed_t zlo, fixed_t zhi,
                            const sector_t *ignore_sector, const line_t *ignore_line);

// Ramp helper: move current toward target by at most step; result in [0, 1].
float dsda_OcclusionStep(float current, float target, float step);

#endif
