"""2D re-implementation of the opening test in Doom's P_CheckSight.

Design-time check only: a straight line from the looker's eye to a point
on the target must pass through every two-sided line's opening
(max of the two floors .. min of the two ceilings) and cross no
one-sided line. Doom accepts sight if any part of the target is visible,
so callers pass the target's top (z + height) as the target point.
"""


def _cross(a, b, c, d):
    """Fraction t along a->b where it crosses segment c-d, else None."""
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = a, b, c, d
    rx, ry = bx - ax, by - ay
    sx, sy = dx - cx, dy - cy
    den = rx * sy - ry * sx
    if den == 0:
        return None
    t = ((cx - ax) * sy - (cy - ay) * sx) / den
    u = ((cx - ax) * ry - (cy - ay) * rx) / den
    if 0 < t < 1 and 0 <= u <= 1:
        return t
    return None


def sight_clear(lines, eye, target):
    (ex, ey, ez), (tx, ty, tz) = eye, target
    for l in lines:
        t = _cross((ex, ey), (tx, ty), l.v1, l.v2)
        if t is None:
            continue
        if l.back is None:
            return False, f"one-sided line {l.v1}-{l.v2}"
        bottom = max(l.front.floor, l.back.floor)
        top = min(l.front.ceil, l.back.ceil)
        z = ez + (tz - ez) * t
        if not bottom < z < top:
            return False, (f"line {l.v1}-{l.v2}: z {z:.1f} outside opening "
                           f"{bottom}..{top}")
    return True, "clear"
