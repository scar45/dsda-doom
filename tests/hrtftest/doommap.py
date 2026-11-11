"""doommap: tiny Doom-format (Boom) map builder and PWAD writer.

Sectors are polygons in map units (y points north). Edges shared by two
sectors become two-sided lines. Edges of a child sector (drawn inside its
parent without touching the parent's boundary) become two-sided lines
with the parent behind them. Every other edge is a one-sided wall.
Nodes are NOT built here; run zdbsp on the output.

Python 3 standard library only. Untracked test tooling for the HRTF fork.
"""
import struct
import sys

ML_BLOCKING = 0x0001
ML_BLOCKMONSTERS = 0x0002
ML_TWOSIDED = 0x0004

MAP_LUMPS = ("THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES", "SEGS",
             "SSECTORS", "NODES", "SECTORS", "REJECT", "BLOCKMAP")

TAGGED_SPECIALS = {73, 97}     # tag must name at least one sector
TELEPORT_SPECIALS = {97}       # tagged sector must hold a thing 14
THING_TELEPORT_DEST = 14


class MapError(Exception):
    pass


def signed_area(poly):
    a = 0
    for i, (x1, y1) in enumerate(poly):
        x2, y2 = poly[(i + 1) % len(poly)]
        a += x1 * y2 - x2 * y1
    return a / 2


def point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xc = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xc:
                inside = not inside
    return inside


def on_segment(p, a, b):
    """True if p lies on segment a-b, endpoints excluded."""
    if p == a or p == b:
        return False
    (px, py), (ax, ay), (bx, by) = p, a, b
    if (bx - ax) * (py - ay) - (by - ay) * (px - ax) != 0:
        return False
    return (min(ax, bx) <= px <= max(ax, bx)
            and min(ay, by) <= py <= max(ay, by))


def _within(p, a, b):
    return p == a or p == b or on_segment(p, a, b)


def aprox_distance(dx, dy):
    """Doom's P_AproxDistance (what the sound code uses)."""
    dx, dy = abs(dx), abs(dy)
    return dx + dy - min(dx, dy) / 2


def _name(s):
    raw = s.upper().encode("ascii")
    if len(raw) > 8:
        raise MapError(f"name too long: {s}")
    return raw


class Sector:
    def __init__(self, poly, floor, ceil, light=192, floor_tex="FLOOR4_8",
                 ceil_tex="CEIL3_5", wall="STARTAN3", tag=0, special=0,
                 parent=None, group=""):
        poly = [(int(x), int(y)) for x, y in poly]
        if signed_area(poly) > 0:   # clockwise => interior on the right
            poly.reverse()
        self.poly = poly
        self.floor, self.ceil = int(floor), int(ceil)
        self.light = light
        self.floor_tex, self.ceil_tex, self.wall = floor_tex, ceil_tex, wall
        self.tag, self.special = tag, special
        self.parent = parent
        self.group = group
        self.index = None

    def contains(self, pt):
        return point_in_poly(pt, self.poly)

    def centre(self):
        xs = [p[0] for p in self.poly]
        ys = [p[1] for p in self.poly]
        return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


class Line:
    def __init__(self, v1, v2, front, back):
        self.v1, self.v2 = v1, v2
        self.front, self.back = front, back
        self.flags = ML_TWOSIDED if back is not None else 0
        self.special = 0
        self.tag = 0
        self.front_upper = None

    def flip(self):
        self.v1, self.v2 = self.v2, self.v1
        self.front, self.back = self.back, self.front


class MapBuilder:
    def __init__(self):
        self.sectors = []
        self.things = []
        self._marks = []
        self.lines = None

    def add_sector(self, poly, floor, ceil, **kw):
        s = Sector(poly, floor, ceil, **kw)
        s.index = len(self.sectors)
        self.sectors.append(s)
        return s

    def rect(self, x1, y1, x2, y2, floor, ceil, **kw):
        return self.add_sector([(x1, y1), (x1, y2), (x2, y2), (x2, y1)],
                               floor, ceil, **kw)

    def thing(self, x, y, angle, type_, flags=7):
        self.things.append((int(x), int(y), int(angle), type_, flags))

    def mark(self, p1, p2, special=0, tag=0, flags=0, front=None,
             front_upper=None):
        self._marks.append(dict(p1=(int(p1[0]), int(p1[1])),
                                p2=(int(p2[0]), int(p2[1])),
                                special=special, tag=tag, flags=flags,
                                front=front, front_upper=front_upper))

    def build(self):
        verts = set()
        for s in self.sectors:
            verts.update(s.poly)
        edges = {}
        for s in self.sectors:
            n = len(s.poly)
            for i in range(n):
                a, b = s.poly[i], s.poly[(i + 1) % n]
                inner = sorted((v for v in verts if on_segment(v, a, b)),
                               key=lambda v: (v[0] - a[0]) ** 2
                               + (v[1] - a[1]) ** 2)
                pts = [a] + inner + [b]
                for p, q in zip(pts, pts[1:]):
                    edges.setdefault(frozenset((p, q)), []).append((s, p, q))
        lines = []
        for key, occ in edges.items():
            if len(occ) == 1:
                s, p, q = occ[0]
                lines.append(Line(p, q, s, s.parent))
            elif len(occ) == 2:
                (s1, p1, q1), (s2, p2, q2) = occ
                if (p1, q1) != (q2, p2):
                    raise MapError(f"sectors {s1.index} and {s2.index} "
                                   f"overlap along {p1}-{q1}")
                lines.append(Line(p1, q1, s1, s2))
            else:
                raise MapError(f"edge {sorted(key)} used by {len(occ)} sectors")
        for m in self._marks:
            hit = [l for l in lines if _within(l.v1, m["p1"], m["p2"])
                   and _within(l.v2, m["p1"], m["p2"])]
            if not hit:
                raise MapError(f"mark {m['p1']}-{m['p2']} matched no line")
            for l in hit:
                if m["front"] is not None and l.front is not m["front"]:
                    if l.back is not m["front"]:
                        raise MapError(f"mark {m['p1']}-{m['p2']}: requested "
                                       "front sector is on neither side")
                    l.flip()
                l.flags |= m["flags"]
                if m["special"]:
                    l.special = m["special"]
                if m["tag"]:
                    l.tag = m["tag"]
                if m["front_upper"]:
                    l.front_upper = m["front_upper"]
        self.lines = lines
        return lines

    def validate(self):
        lines = self.lines if self.lines is not None else self.build()
        errors = []
        for s in self.sectors:
            balance = {}
            used = False
            for l in lines:
                if l.front is s:
                    a, b = l.v1, l.v2
                elif l.back is s:
                    a, b = l.v2, l.v1
                else:
                    continue
                used = True
                balance[a] = balance.get(a, 0) + 1
                balance[b] = balance.get(b, 0) - 1
            if not used:
                errors.append(f"sector {s.index} has no lines")
            bad = [v for v, c in balance.items() if c != 0]
            if bad:
                errors.append(f"sector {s.index} not closed at {bad}")
        for l in lines:
            if (l.back is not None) != bool(l.flags & ML_TWOSIDED):
                errors.append(f"line {l.v1}-{l.v2}: TWOSIDED flag mismatch")
            if l.special in TAGGED_SPECIALS:
                targets = [s for s in self.sectors if l.tag and s.tag == l.tag]
                if not targets:
                    errors.append(f"line {l.v1}-{l.v2}: special {l.special} "
                                  f"tag {l.tag} matches no sector")
                elif l.special in TELEPORT_SPECIALS and not any(
                        t[3] == THING_TELEPORT_DEST and s.contains(t[:2])
                        for s in targets for t in self.things):
                    errors.append(f"line {l.v1}-{l.v2}: teleport tag {l.tag} "
                                  "has no destination thing")
        for s in self.sectors:
            for x, y in s.poly:
                if not (-32768 < x < 32768 and -32768 < y < 32768):
                    errors.append(f"sector {s.index}: vertex out of range")
        if errors:
            raise MapError("\n".join(errors))

    def write_wad(self, path, mapname="MAP01"):
        lines = self.lines if self.lines is not None else self.build()
        self.validate()
        vindex = {}
        verts = []

        def vid(v):
            if v not in vindex:
                vindex[v] = len(verts)
                verts.append(v)
            return vindex[v]

        def sidedef(sec, other, upper=None):
            two = other is not None
            up = upper or (sec.wall if two else "-")
            low = sec.wall if two else "-"
            mid = "-" if two else sec.wall
            return struct.pack("<hh8s8s8sh", 0, 0, _name(up), _name(low),
                               _name(mid), sec.index)

        sides = bytearray()
        ldefs = bytearray()
        nsides = 0
        for l in lines:
            f = nsides
            sides += sidedef(l.front, l.back, l.front_upper)
            nsides += 1
            b = 0xFFFF
            if l.back is not None:
                b = nsides
                sides += sidedef(l.back, l.front)
                nsides += 1
            ldefs += struct.pack("<7H", vid(l.v1), vid(l.v2), l.flags,
                                 l.special, l.tag, f, b)
        vbytes = b"".join(struct.pack("<hh", x, y) for x, y in verts)
        secs = b"".join(struct.pack("<hh8s8shhh", s.floor, s.ceil,
                                    _name(s.floor_tex), _name(s.ceil_tex),
                                    s.light, s.special, s.tag)
                        for s in self.sectors)
        things = b"".join(struct.pack("<hhhhh", *t) for t in self.things)
        data = {"THINGS": things, "LINEDEFS": bytes(ldefs),
                "SIDEDEFS": bytes(sides), "VERTEXES": vbytes, "SECTORS": secs}
        lumps = [(mapname, b"")] + [(n, data.get(n, b"")) for n in MAP_LUMPS]
        write_pwad(path, lumps)


def write_pwad(path, lumps):
    out = bytearray(b"PWAD" + struct.pack("<ii", len(lumps), 0))
    entries = []
    for name, blob in lumps:
        entries.append((len(out), len(blob), name))
        out += blob
    diroff = len(out)
    for off, size, name in entries:
        out += struct.pack("<ii8s", off, size, _name(name))
    struct.pack_into("<i", out, 8, diroff)
    with open(path, "wb") as f:
        f.write(out)


def read_wad(path):
    with open(path, "rb") as f:
        d = f.read()
    ident, n, off = struct.unpack("<4sii", d[:12])
    if ident not in (b"PWAD", b"IWAD"):
        raise MapError(f"{path}: not a WAD")
    lumps = []
    for i in range(n):
        pos, size, name = struct.unpack("<ii8s", d[off + 16 * i:off + 16 * i + 16])
        lumps.append((name.rstrip(b"\0").decode("ascii"), d[pos:pos + size]))
    return lumps


RECORD_SIZES = {"THINGS": 10, "LINEDEFS": 14, "SIDEDEFS": 30, "VERTEXES": 4,
                "SEGS": 12, "SSECTORS": 4, "NODES": 28, "SECTORS": 26}


def dump(path):
    rows = []
    for name, blob in read_wad(path):
        rec = RECORD_SIZES.get(name)
        count = f"{len(blob) // rec} records" if rec else ""
        rows.append(f"{name:<9} {len(blob):>7} bytes  {count}")
    return "\n".join(rows)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "dump":
        print(dump(sys.argv[2]))
    else:
        print("usage: doommap.py dump FILE.wad")
        sys.exit(2)
