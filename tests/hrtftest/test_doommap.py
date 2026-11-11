import os
import struct
import tempfile
import unittest

from doommap import (ML_BLOCKING, ML_TWOSIDED, MapBuilder, MapError,
                     point_in_poly, read_wad)


def right_of(line, dist=1.0):
    """Point just to the right of the line's midpoint (Doom: front side)."""
    (x1, y1), (x2, y2) = line.v1, line.v2
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    dx, dy = x2 - x1, y2 - y1
    n = (dx * dx + dy * dy) ** 0.5
    return (mx + dy / n * dist, my - dx / n * dist)


class GeometryTests(unittest.TestCase):
    def test_single_square_is_four_one_sided_walls_facing_inside(self):
        m = MapBuilder()
        s = m.rect(0, 0, 128, 128, 0, 128)
        lines = m.build()
        self.assertEqual(len(lines), 4)
        for l in lines:
            self.assertIs(l.front, s)
            self.assertIsNone(l.back)
            self.assertEqual(l.flags & ML_TWOSIDED, 0)
            self.assertTrue(point_in_poly(right_of(l), s.poly))

    def test_adjacent_squares_share_one_two_sided_line(self):
        m = MapBuilder()
        a = m.rect(0, 0, 128, 128, 0, 128)
        b = m.rect(128, 0, 256, 128, 0, 128)
        lines = m.build()
        self.assertEqual(len(lines), 7)
        shared = [l for l in lines if l.back is not None]
        self.assertEqual(len(shared), 1)
        self.assertTrue(shared[0].flags & ML_TWOSIDED)
        self.assertEqual({shared[0].front, shared[0].back}, {a, b})
        self.assertTrue(point_in_poly(right_of(shared[0]), shared[0].front.poly))

    def test_child_sector_lines_have_parent_behind(self):
        m = MapBuilder()
        room = m.rect(0, 0, 256, 256, 0, 128)
        kid = m.rect(64, 64, 128, 128, 0, 64, parent=room)
        lines = m.build()
        self.assertEqual(len(lines), 8)
        kid_lines = [l for l in lines if kid in (l.front, l.back)]
        self.assertEqual(len(kid_lines), 4)
        for l in kid_lines:
            self.assertIs(l.front, kid)
            self.assertIs(l.back, room)

    def test_t_junction_splits_long_edge(self):
        m = MapBuilder()
        big = m.rect(0, 0, 256, 128, 0, 128)
        m.rect(64, 128, 128, 192, 0, 128)
        lines = m.build()
        top = [l for l in lines if l.v1[1] == 128 and l.v2[1] == 128]
        self.assertEqual(len(top), 3)
        self.assertEqual(sum(1 for l in top if l.back is not None), 1)
        self.assertTrue(all(big in (l.front, l.back) for l in top))

    def test_overlapping_edges_in_same_direction_raise(self):
        m = MapBuilder()
        m.rect(0, 0, 128, 128, 0, 128)
        m.rect(0, 0, 128, 64, 0, 128)
        with self.assertRaises(MapError):
            m.build()


class MarkTests(unittest.TestCase):
    def test_mark_sets_special_tag_flags(self):
        m = MapBuilder()
        a = m.rect(0, 0, 128, 128, 0, 128, tag=5)
        m.rect(128, 0, 256, 128, 0, 128)
        m.mark((128, 0), (128, 128), special=73, tag=5, flags=ML_BLOCKING)
        l = [l for l in m.build() if l.back is not None][0]
        self.assertEqual((l.special, l.tag), (73, 5))
        self.assertTrue(l.flags & ML_BLOCKING)
        self.assertTrue(l.flags & ML_TWOSIDED)

    def test_mark_front_flips_line(self):
        m = MapBuilder()
        a = m.rect(0, 0, 128, 128, 0, 128)
        b = m.rect(128, 0, 256, 128, 0, 128)
        m.mark((128, 0), (128, 128), front=b)
        l = [l for l in m.build() if l.back is not None][0]
        self.assertIs(l.front, b)
        self.assertIs(l.back, a)
        self.assertTrue(point_in_poly(right_of(l), b.poly))

    def test_mark_covering_split_segments_hits_all(self):
        m = MapBuilder()
        m.rect(0, 0, 256, 128, 0, 128)
        m.rect(64, 128, 128, 192, 0, 128)
        m.mark((0, 128), (256, 128), flags=ML_BLOCKING)
        top = [l for l in m.build() if l.v1[1] == 128 and l.v2[1] == 128]
        self.assertTrue(all(l.flags & ML_BLOCKING for l in top))

    def test_mark_matching_nothing_raises(self):
        m = MapBuilder()
        m.rect(0, 0, 128, 128, 0, 128)
        m.mark((500, 500), (600, 500), special=1)
        with self.assertRaises(MapError):
            m.build()


class ValidateTests(unittest.TestCase):
    def test_valid_teleport_passes(self):
        m = MapBuilder()
        hub = m.rect(0, 0, 256, 256, 0, 128)
        m.rect(256, 96, 320, 160, 0, 128)
        m.rect(1000, 0, 1064, 64, 0, 128, tag=2)
        m.thing(1032, 32, 0, 14)
        m.mark((256, 96), (256, 160), special=97, tag=2, front=hub)
        m.build()
        m.validate()

    def test_teleport_without_destination_thing_fails(self):
        m = MapBuilder()
        hub = m.rect(0, 0, 256, 256, 0, 128)
        m.rect(256, 96, 320, 160, 0, 128)
        m.rect(1000, 0, 1064, 64, 0, 128, tag=2)
        m.mark((256, 96), (256, 160), special=97, tag=2, front=hub)
        m.build()
        with self.assertRaises(MapError):
            m.validate()

    def test_special_with_missing_tag_sector_fails(self):
        m = MapBuilder()
        m.rect(0, 0, 128, 128, 0, 128)
        m.rect(128, 0, 256, 128, 0, 128)
        m.mark((128, 0), (128, 128), special=73, tag=9)
        m.build()
        with self.assertRaises(MapError):
            m.validate()


class WadTests(unittest.TestCase):
    def test_wad_has_map_lumps_in_order_and_sizes(self):
        m = MapBuilder()
        m.rect(0, 0, 128, 128, 0, 128)
        m.thing(64, 64, 90, 1)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.wad")
            m.write_wad(path)
            with open(path, "rb") as f:
                self.assertEqual(f.read(4), b"PWAD")
            lumps = read_wad(path)
        names = [n for n, _ in lumps]
        self.assertEqual(names, ["MAP01", "THINGS", "LINEDEFS", "SIDEDEFS",
                                 "VERTEXES", "SEGS", "SSECTORS", "NODES",
                                 "SECTORS", "REJECT", "BLOCKMAP"])
        size = dict(lumps)
        self.assertEqual(len(size["THINGS"]), 10)
        self.assertEqual(len(size["LINEDEFS"]), 4 * 14)
        self.assertEqual(len(size["SIDEDEFS"]), 4 * 30)
        self.assertEqual(len(size["VERTEXES"]), 4 * 4)
        self.assertEqual(len(size["SECTORS"]), 26)
        v1, v2, flags, special, tag, front, back = struct.unpack(
            "<7H", size["LINEDEFS"][:14])
        self.assertEqual(back, 0xFFFF)


if __name__ == "__main__":
    unittest.main()
