import os
import tempfile
import unittest

from doommap import read_wad
from gen_hrtftest import build_map, design_checks


class GenTests(unittest.TestCase):
    def test_map_validates_and_passes_design_checks(self):
        m, refs = build_map()
        m.validate()
        self.assertEqual(design_checks(m, refs), [])

    def test_things(self):
        m, refs = build_map()
        types = [t[3] for t in m.things]
        self.assertEqual(types.count(1), 1)      # player 1 start
        self.assertEqual(types.count(14), 4)     # hub + 3 landings
        self.assertEqual(types.count(3001), 4)   # TOWER imps

    def test_design_checks_catch_a_blind_ledge_imp(self):
        m, refs = build_map()
        x, y, z = refs["tower"]["imp_eyes"]["N"]
        refs["tower"]["imp_eyes"]["N"] = (x, y, z - 40)
        self.assertTrue(any("imp N sight" in f for f in design_checks(m, refs)))

    def test_writes_wad(self):
        m, _ = build_map()
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "raw.wad")
            m.write_wad(path)
            self.assertEqual(read_wad(path)[0][0], "MAP01")


if __name__ == "__main__":
    unittest.main()
