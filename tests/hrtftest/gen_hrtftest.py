#!/usr/bin/env python3
"""Generate MAP01 of hrtftest.wad (no nodes; zdbsp adds them).

Design: .plan/worklog/2026-11-10-hrtf-test-map/hrtf-test-map-design.md
Usage:  python3 -B tests/hrtftest/gen_hrtftest.py [OUT.wad]
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from doommap import ML_BLOCKING, MapBuilder, aprox_distance  # noqa: E402
from sightcheck import sight_clear  # noqa: E402

# Line specials, thing types, angles
TELEPORT_WR, CRUSHER_WR, DOOR_DR = 97, 73, 1
T_PLAYER1, T_TELEDEST, T_IMP = 1, 14, 3001
EAST, NORTH, WEST, SOUTH = 0, 90, 180, 270

# Tags
TAG_HUB_DEST, TAG_RING_DEST, TAG_WALLS_DEST, TAG_TOWER_DEST = 1, 2, 3, 4
TAG_RING_CRUSH, TAG_WALLS_CRUSH = 10, 11

# Layout
RING_C = (0, 3000)
WALLS_X0, WALLS_X1 = -6200, -2800
BAYS_X = {"a": -5800, "b": -4400, "c": -3000}
TOWER_C = (3200, 0)

IMP_EYE = 42        # 3/4 of imp height 56 (P_CheckSight looker eye)
PLAYER_TOP = 56     # player height; sight target top
SOUND_RANGE = 1200  # SNDCURVE length
ROOM_GAP = 1500


def square(m, cx, cy, half, floor, ceil, **kw):
    return m.rect(cx - half, cy - half, cx + half, cy + half, floor, ceil, **kw)


def block_edges(m, s):
    n = len(s.poly)
    for i in range(n):
        m.mark(s.poly[i], s.poly[(i + 1) % n], flags=ML_BLOCKING)


def return_alcove(m, room, x1, y1, x2, y2, mouth_a, mouth_b, group):
    m.rect(x1, y1, x2, y2, room.floor, room.ceil, light=room.light,
           wall="GRAY1", group=group)
    m.mark(mouth_a, mouth_b, special=TELEPORT_WR, tag=TAG_HUB_DEST, front=room)


def build_hub(m):
    hub = m.rect(-256, -256, 256, 256, 0, 128, light=160, wall="GRAY1",
                 group="hub")
    pad = square(m, 0, 0, 32, 0, 128, light=160, floor_tex="FLAT14",
                 wall="GRAY1", tag=TAG_HUB_DEST, parent=hub, group="hub")
    m.thing(0, 0, NORTH, T_PLAYER1)
    m.thing(0, 0, NORTH, T_TELEDEST)
    # Alcoves: N -> RING (green marble), W -> WALLS (bronze), E -> TOWER (skin)
    m.rect(-32, 256, 32, 320, 0, 128, light=160, wall="MARBLE1", group="hub")
    m.mark((-32, 256), (32, 256), special=TELEPORT_WR, tag=TAG_RING_DEST,
           front=hub)
    m.rect(-320, -32, -256, 32, 0, 128, light=160, wall="BRONZE1", group="hub")
    m.mark((-256, -32), (-256, 32), special=TELEPORT_WR, tag=TAG_WALLS_DEST,
           front=hub)
    m.rect(256, -32, 320, 32, 0, 128, light=160, wall="SKIN2", group="hub")
    m.mark((256, -32), (256, 32), special=TELEPORT_WR, tag=TAG_TOWER_DEST,
           front=hub)
    return {"hub": hub, "pad": pad}


def build_ring(m):
    cx, cy = RING_C
    room = m.rect(cx - 512, cy - 512, cx + 512, cy + 512, 0, 256,
                  wall="MARBLE1", group="ring")
    beacon = square(m, cx, cy, 64, 0, 128, wall="METAL", tag=TAG_RING_CRUSH,
                    parent=room, group="ring")
    block_edges(m, beacon)
    markers = []
    for ang in range(0, 360, 45):
        mx = cx + round(256 * math.cos(math.radians(ang)))
        my = cy + round(256 * math.sin(math.radians(ang)))
        markers.append(square(m, mx, my, 16, 0, 256, floor_tex="FLOOR1_6",
                              wall="MARBLE1", parent=room, group="ring",
                              tag=TAG_RING_DEST if ang == SOUTH else 0))
    m.thing(cx, cy - 256, NORTH, T_TELEDEST)
    # First step north off the landing marker starts the crusher.
    m.mark((cx - 16, cy - 240), (cx + 16, cy - 240), special=CRUSHER_WR,
           tag=TAG_RING_CRUSH)
    return_alcove(m, room, cx - 32, cy - 576, cx + 32, cy - 512,
                  (cx - 32, cy - 512), (cx + 32, cy - 512), "ring")
    return {"room": room, "beacon": beacon, "markers": markers}


def build_walls(m):
    cor = m.rect(WALLS_X0, -128, WALLS_X1, 128, 0, 128, wall="BRONZE1",
                 group="walls")
    pad = square(m, WALLS_X0 + 100, 0, 16, 0, 128, floor_tex="FLAT14",
                 wall="BRONZE1", tag=TAG_WALLS_DEST, parent=cor, group="walls")
    m.thing(WALLS_X0 + 100, 0, EAST, T_TELEDEST)
    # First step east off the landing pad starts all three crushers.
    m.mark((WALLS_X0 + 116, -16), (WALLS_X0 + 116, 16), special=CRUSHER_WR,
           tag=TAG_WALLS_CRUSH)
    return_alcove(m, cor, WALLS_X0 - 64, -32, WALLS_X0, 32,
                  (WALLS_X0, -32), (WALLS_X0, 32), "walls")
    bays = {}
    for name, bx in BAYS_X.items():
        marker = square(m, bx, 0, 16, 0, 128, floor_tex="FLOOR1_6",
                        wall="BRONZE1", parent=cor, group="walls")
        if name == "a":     # open: bay room shares a 256-wide opening
            room = m.rect(bx - 128, 128, bx + 128, 384, 0, 256,
                          wall="BRONZE1", group="walls")
        else:               # b sealed by a 16-unit void; c behind a door
            room = m.rect(bx - 128, 144, bx + 128, 400, 0, 256,
                          wall="BRONZE1", group="walls")
        if name == "c":
            m.rect(bx - 32, 128, bx + 32, 144, 0, 0, wall="DOORTRAK",
                   group="walls")
            m.mark((bx - 32, 128), (bx + 32, 128), special=DOOR_DR,
                   front=cor, front_upper="BIGDOOR2")
        beacon = square(m, bx, 256, 64, 0, 128, wall="METAL",
                        tag=TAG_WALLS_CRUSH, parent=room, group="walls")
        block_edges(m, beacon)
        bays[name] = {"marker": marker, "room": room, "beacon": beacon}
    return {"corridor": cor, "pad": pad, "bays": bays}


def build_tower(m):
    cx, cy = TOWER_C

    def p(x, y):
        return (cx + x, cy + y)

    # Room with a notch cut into its south side; the pit fills the notch.
    room = m.add_sector([p(-288, -288), p(-288, 288), p(288, 288),
                         p(288, -288), p(96, -288), p(96, -32), p(-96, -32),
                         p(-96, -288)], 0, 768, wall="SKIN2", group="tower")
    pad = square(m, cx, cy, 16, 0, 768, floor_tex="FLAT14", wall="SKIN2",
                 tag=TAG_TOWER_DEST, parent=room, group="tower")
    m.thing(cx, cy, NORTH, T_TELEDEST)
    ledges = {
        "N": m.rect(cx - 64, cy + 288, cx + 64, cy + 352, 256, 384,
                    wall="SKIN2", group="tower"),
        "E": m.rect(cx + 288, cy - 64, cx + 352, cy + 64, 0, 128,
                    wall="SKIN2", group="tower"),
        "W": m.rect(cx - 352, cy - 64, cx - 288, cy + 64, 128, 256,
                    wall="SKIN2", group="tower"),
    }
    m.mark(p(-64, 288), p(64, 288), flags=ML_BLOCKING)
    m.mark(p(288, -64), p(288, 64), flags=ML_BLOCKING)
    m.mark(p(-288, -64), p(-288, 64), flags=ML_BLOCKING)
    pit = m.rect(cx - 96, cy - 416, cx + 96, cy - 32, -256, 768,
                 wall="SKIN2", group="tower")
    for a, b in ((p(-96, -288), p(-96, -32)), (p(-96, -32), p(96, -32)),
                 (p(96, -32), p(96, -288))):
        m.mark(a, b, flags=ML_BLOCKING)
    cell = square(m, cx, cy - 288, 64, -256, 768, wall="SKIN2", parent=pit,
                  group="tower")
    block_edges(m, cell)
    imps = {"N": (cx, cy + 320, SOUTH, ledges["N"]),
            "E": (cx + 320, cy, WEST, ledges["E"]),
            "W": (cx - 320, cy, EAST, ledges["W"]),
            "S": (cx, cy - 288, NORTH, cell)}
    imp_eyes = {}
    for k, (x, y, ang, sec) in imps.items():
        m.thing(x, y, ang, T_IMP)
        imp_eyes[k] = (x, y, sec.floor + IMP_EYE)
    return_alcove(m, room, cx + 160, cy + 288, cx + 224, cy + 352,
                  p(160, 288), p(224, 288), "tower")
    return {"room": room, "pad": pad, "ledges": ledges, "pit": pit,
            "cell": cell, "imp_eyes": imp_eyes}


def build_map():
    m = MapBuilder()
    refs = {"hub": build_hub(m), "ring": build_ring(m),
            "walls": build_walls(m), "tower": build_tower(m)}
    m.build()
    return m, refs


def _bbox(sectors):
    xs = [x for s in sectors for x, _ in s.poly]
    ys = [y for s in sectors for _, y in s.poly]
    return min(xs), min(ys), max(xs), max(ys)


def _gap(a, b):
    dx = max(0, b[0] - a[2], a[0] - b[2])
    dy = max(0, b[1] - a[3], a[1] - b[3])
    return math.hypot(dx, dy)


def design_checks(m, refs):
    fails = []
    lines = m.lines

    # 1. Rooms far enough apart that sound can't leak between them.
    groups = sorted({s.group for s in m.sectors})
    boxes = {g: _bbox([s for s in m.sectors if s.group == g]) for g in groups}
    for i, g1 in enumerate(groups):
        for g2 in groups[i + 1:]:
            gap = _gap(boxes[g1], boxes[g2])
            if gap < ROOM_GAP:
                fails.append(f"room gap {g1}-{g2} is {gap:.0f} < {ROOM_GAP}")

    # 2. RING markers 256 from the beacon.
    bc = refs["ring"]["beacon"].centre()
    for mk in refs["ring"]["markers"]:
        d = math.dist(mk.centre(), bc)
        if abs(d - 256) > 1:
            fails.append(f"ring marker {mk.centre()} is {d:.1f} from beacon")

    # 3. WALLS: own beacon 256 away, every other beacon out of earshot.
    bays = refs["walls"]["bays"]
    for name, bay in bays.items():
        mc = bay["marker"].centre()
        d = math.dist(mc, bay["beacon"].centre())
        if abs(d - 256) > 1:
            fails.append(f"walls bay {name}: marker {d:.1f} from beacon")
        for other, ob in bays.items():
            if other == name:
                continue
            oc = ob["beacon"].centre()
            dx, dy = oc[0] - mc[0], oc[1] - mc[1]
            if min(math.hypot(dx, dy), aprox_distance(dx, dy)) <= SOUND_RANGE:
                fails.append(f"walls bay {name} hears beacon {other}")

    # 4. TOWER heights relative to the room floor.
    t = refs["tower"]
    want = {"N": 256, "E": 0, "W": 128}
    for k, h in want.items():
        if t["ledges"][k].floor - t["room"].floor != h:
            fails.append(f"tower ledge {k} height wrong")
    if t["pit"].floor - t["room"].floor != -256:
        fails.append("tower pit depth wrong")

    # 5. Blocking: cage/pit lips, the imp cell, and every crusher beacon.
    cages = set(t["ledges"].values()) | {t["pit"]}
    beacons = {refs["ring"]["beacon"]} | {b["beacon"] for b in bays.values()}
    for l in lines:
        sides = {l.front, l.back}
        lip = t["room"] in sides and sides & cages
        if (lip or t["cell"] in sides or sides & beacons) \
                and not l.flags & ML_BLOCKING:
            fails.append(f"line {l.v1}-{l.v2} should be ML_BLOCKING")

    # 6. Sight: every imp can see the player standing on the centre marker.
    pc = t["pad"].centre()
    target = (pc[0], pc[1], t["room"].floor + PLAYER_TOP)
    for k, eye in t["imp_eyes"].items():
        ok, why = sight_clear(lines, eye, target)
        if not ok:
            fails.append(f"tower imp {k} sight blocked: {why}")
    return fails


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        here, "build", "hrtftest_raw.wad")
    m, refs = build_map()
    m.validate()
    fails = design_checks(m, refs)
    if fails:
        print("DESIGN CHECKS FAILED:")
        for f in fails:
            print("  " + f)
        sys.exit(1)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    m.write_wad(out)
    print(f"wrote {out}: {len(m.sectors)} sectors, {len(m.lines)} lines, "
          f"{len(m.things)} things; design checks passed")


if __name__ == "__main__":
    main()
