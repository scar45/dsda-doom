import unittest

from doommap import MapBuilder
from sightcheck import sight_clear


def ledge_map(depth):
    """576-square room (floor 0, ceil 768) with a north ledge at +256."""
    m = MapBuilder()
    m.rect(0, 0, 576, 576, 0, 768)
    m.rect(256, 576, 320, 576 + depth, 256, 384)
    return m.build()


class SightTests(unittest.TestCase):
    def test_imp_at_lip_of_high_ledge_sees_player(self):
        lines = ledge_map(64)
        ok, why = sight_clear(lines, (288, 608, 256 + 42), (288, 288, 56))
        self.assertTrue(ok, why)

    def test_imp_set_back_on_deep_ledge_is_blocked(self):
        lines = ledge_map(128)
        ok, why = sight_clear(lines, (288, 640, 256 + 42), (288, 288, 56))
        self.assertFalse(ok)
        self.assertIn("outside opening", why)

    def test_one_sided_wall_blocks(self):
        m = MapBuilder()
        m.rect(0, 0, 128, 128, 0, 128)
        m.rect(256, 0, 384, 128, 0, 128)
        ok, why = sight_clear(m.build(), (64, 64, 41), (320, 64, 41))
        self.assertFalse(ok)
        self.assertIn("one-sided", why)

    def test_open_room_is_clear(self):
        m = MapBuilder()
        m.rect(0, 0, 512, 512, 0, 128)
        ok, why = sight_clear(m.build(), (64, 64, 41), (448, 448, 56))
        self.assertTrue(ok, why)


if __name__ == "__main__":
    unittest.main()
