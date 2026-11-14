"""Exact native GLO-30 edge flags must not be mistaken for fabricated water."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from island_native_source_border_review import marked_source_transitions, BORDERS


class IslandNativeSourceBorderTests(unittest.TestCase):
    def test_all_sources_adjacent_are_strict_native_neighbors(self):
        self.assertEqual(BORDERS["gorgona"]["latitude"],3.)
        self.assertEqual(BORDERS["malpelo"]["latitude"],4.)
        self.assertTrue(BORDERS["gorgona"]["south"].endswith("N02_00_W079_00_DEM"))
        self.assertTrue(BORDERS["malpelo"]["north"].endswith("N04_00_W082_00_DEM"))

    def test_exact_flag_only_where_both_sources_valid(self):
        h=np.full((256,256),20.,dtype=np.float32)
        valid=np.ones((256,256),bool)
        prov=np.ones((256,256),dtype=np.uint8)
        prov[128:,:]=2
        h[128:,:]=83.
        valid[127,0]=False
        flags=marked_source_transitions(h,valid,prov,["old","candidate"],"candidate")
        self.assertEqual(len(flags),255)
        self.assertEqual(flags[0]["cross_source_adjacent_delta_m"],63.)
        self.assertTrue(flags[0]["height_gradient_not_alone_evidence_of_bad_source"])
        self.assertTrue(all(x["orientation"]=="north_south_neighbor" for x in flags))

    def test_reproducible_strict_shape_rejected(self):
        h=np.zeros((255,256))
        valid=np.ones((256,256),bool)
        prov=np.ones((256,256),dtype=np.uint8)
        with self.assertRaisesRegex(ValueError,"Unaligned"):
            marked_source_transitions(h,valid,prov,["old","candidate"],"candidate")

    def test_less_than_40m_not_a_flag(self):
        h=np.zeros((256,256),dtype=np.float32)
        valid=np.ones((256,256),bool)
        prov=np.ones((256,256),dtype=np.uint8)
        prov[128:,:]=2
        h[128:,:]=40.
        self.assertFalse(marked_source_transitions(
            h,valid,prov,["old","candidate"],"candidate"))


if __name__=="__main__":
    unittest.main()
