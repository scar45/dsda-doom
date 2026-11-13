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
//  A sight trace for the sound code. It walks the BSP from the eye to the
//  target like the game's sight check, but keeps all state on the stack and
//  works in doubles (sound-side only, never feeds the simulation).
//

#include <math.h>

#include "doomdata.h"
#include "r_state.h"

#include "sound_occlusion.h"

// Fractions below this along the trace are treated as this, so a line under
// the listener's feet still narrows the window instead of dividing by zero.
#define OCCL_MIN_FRAC (1.0 / 65536.0)

typedef struct
{
  double ex, ey, ez;    // eye
  double tx, ty;        // target
  double top, bottom;   // slope window: z at frac f is ez + slope * f
  const sector_t *ignore_sector;
  const line_t *ignore_line;
} occl_trace_t;

#define FIX2D(x) ((double) (x) / FRACUNIT)

// 0 = front, 1 = back (points on the partition count as back, as in the
// renderer). Only used to find which children to visit.
static int OCCL_NodeSide(double x, double y, const node_t *node)
{
  double ndx = FIX2D(node->dx), ndy = FIX2D(node->dy);

  return (y - FIX2D(node->y)) * ndx >= ndy * (x - FIX2D(node->x));
}

// Signed area of (a, b, p): > 0 left of a->b, < 0 right, 0 on the line.
static double OCCL_Cross(double ax, double ay, double bx, double by, double px, double py)
{
  return (bx - ax) * (py - ay) - (by - ay) * (px - ax);
}

// False if this seg stops the trace.
static dboolean OCCL_CrossSeg(occl_trace_t *tr, const seg_t *seg)
{
  const line_t *line = seg->linedef;
  const sector_t *front, *back;
  double x1, y1, x2, y2, s1, s2, c1, c2, frac, opentop, openbottom;

  if (!line || line == tr->ignore_line)
    return true;

  x1 = FIX2D(seg->v1->x); y1 = FIX2D(seg->v1->y);
  x2 = FIX2D(seg->v2->x); y2 = FIX2D(seg->v2->y);

  // eye and target on the same side of the seg (or trace along it)?
  s1 = OCCL_Cross(x1, y1, x2, y2, tr->ex, tr->ey);
  s2 = OCCL_Cross(x1, y1, x2, y2, tr->tx, tr->ty);
  if ((s1 > 0 && s2 > 0) || (s1 < 0 && s2 < 0) || s1 == s2)
    return true;

  // seg endpoints on the same side of the trace?
  c1 = OCCL_Cross(tr->ex, tr->ey, tr->tx, tr->ty, x1, y1);
  c2 = OCCL_Cross(tr->ex, tr->ey, tr->tx, tr->ty, x2, y2);
  if ((c1 > 0 && c2 > 0) || (c1 < 0 && c2 < 0))
    return true;

  front = seg->frontsector;
  back = seg->backsector;

  if (!(line->flags & ML_TWOSIDED) || !front || !back)
    return false;

  if (front == tr->ignore_sector || back == tr->ignore_sector)
    return true;

  opentop = FIX2D(front->ceilingheight < back->ceilingheight ?
                  front->ceilingheight : back->ceilingheight);
  openbottom = FIX2D(front->floorheight > back->floorheight ?
                     front->floorheight : back->floorheight);

  if (openbottom >= opentop)
    return false;

  frac = s1 / (s1 - s2);
  if (frac < OCCL_MIN_FRAC)
    frac = OCCL_MIN_FRAC;

  if ((openbottom - tr->ez) / frac > tr->bottom)
    tr->bottom = (openbottom - tr->ez) / frac;

  if ((opentop - tr->ez) / frac < tr->top)
    tr->top = (opentop - tr->ez) / frac;

  // >= so a zero-height target (a point) passes an opening that contains it
  return tr->top >= tr->bottom;
}

static dboolean OCCL_CrossSubsector(occl_trace_t *tr, int num)
{
  const subsector_t *ss = &subsectors[num];
  int i;

  for (i = 0; i < ss->numlines; i++)
    if (!OCCL_CrossSeg(tr, &segs[ss->firstline + i]))
      return false;

  return true;
}

static dboolean OCCL_CrossNode(occl_trace_t *tr, int bspnum)
{
  while (!(bspnum & NF_SUBSECTOR))
  {
    const node_t *node = &nodes[bspnum];
    int side = OCCL_NodeSide(tr->ex, tr->ey, node);

    if (side == OCCL_NodeSide(tr->tx, tr->ty, node))
      bspnum = node->children[side];
    else if (!OCCL_CrossNode(tr, node->children[side]))
      return false;
    else
      bspnum = node->children[side ^ 1];
  }

  return OCCL_CrossSubsector(tr, bspnum & ~NF_SUBSECTOR);
}

static int OCCL_PointSubsector(double x, double y)
{
  int bspnum = numnodes - 1;

  while (!(bspnum & NF_SUBSECTOR))
  {
    const node_t *node = &nodes[bspnum];

    bspnum = node->children[OCCL_NodeSide(x, y, node)];
  }

  return bspnum & ~NF_SUBSECTOR;
}

dboolean dsda_SoundOccluded(fixed_t ex, fixed_t ey, fixed_t ez,
                            fixed_t tx, fixed_t ty, fixed_t zlo, fixed_t zhi,
                            const sector_t *ignore_sector, const line_t *ignore_line)
{
  occl_trace_t tr;

  // a single-subsector map has no nodes and nothing to cross
  if (numnodes <= 0 || !nodes || !subsectors || !segs)
    return false;

  tr.ex = FIX2D(ex); tr.ey = FIX2D(ey); tr.ez = FIX2D(ez);
  tr.tx = FIX2D(tx); tr.ty = FIX2D(ty);
  tr.top = FIX2D(zhi) - tr.ez;
  tr.bottom = FIX2D(zlo) - tr.ez;
  tr.ignore_sector = ignore_sector;
  tr.ignore_line = ignore_line;

  if (OCCL_PointSubsector(tr.ex, tr.ey) == OCCL_PointSubsector(tr.tx, tr.ty))
    return false;

  return !OCCL_CrossNode(&tr, numnodes - 1);
}

// Parallel rays at 0, +-OCCL_RAY_SPACING, +-2 * OCCL_RAY_SPACING map units.
#define OCCL_RAY_PAIRS   2
#define OCCL_RAY_SPACING 40.0

float dsda_SoundOcclusion(fixed_t ex, fixed_t ey, fixed_t ez,
                          fixed_t tx, fixed_t ty, fixed_t zlo, fixed_t zhi,
                          const sector_t *ignore_sector, const line_t *ignore_line)
{
  double dx = FIX2D(tx) - FIX2D(ex), dy = FIX2D(ty) - FIX2D(ey);
  double len = sqrt(dx * dx + dy * dy);
  fixed_t tz = (zlo >> 1) + (zhi >> 1); // halves first: zhi - zlo can overflow
  int blocked, rays, i, sign;

  if (len < 1.0)
    return 0.0f;

  blocked = dsda_SoundOccluded(ex, ey, ez, tx, ty, zlo, zhi, ignore_sector, ignore_line);
  rays = 1;

  for (i = 1; i <= OCCL_RAY_PAIRS; i++)
    for (sign = -1; sign <= 1; sign += 2)
    {
      double k = sign * i * OCCL_RAY_SPACING / len;
      fixed_t ox = (fixed_t) (-dy * k * FRACUNIT);
      fixed_t oy = (fixed_t) (dx * k * FRACUNIT);

      // offset ends must be reachable from their centre points
      if (dsda_SoundOccluded(ex, ey, ez, ex + ox, ey + oy, ez, ez, NULL, NULL) ||
          dsda_SoundOccluded(tx, ty, tz, tx + ox, ty + oy, zlo, zhi,
                             ignore_sector, ignore_line))
        continue;

      blocked += dsda_SoundOccluded(ex + ox, ey + oy, ez, tx + ox, ty + oy, zlo, zhi,
                                    ignore_sector, ignore_line);
      rays++;
    }

  // squared: partial blockers (pillars) muffle lightly, walls (all rays) fully
  return (float) (blocked * blocked) / (rays * rays);
}

float dsda_OcclusionStep(float current, float target, float step)
{
  if (current < target)
  {
    current += step;
    if (current > target)
      current = target;
  }
  else if (current > target)
  {
    current -= step;
    if (current < target)
      current = target;
  }

  if (current < 0.0f)
    current = 0.0f;
  else if (current > 1.0f)
    current = 1.0f;

  return current;
}
