"""No-publication, exact native GLO-30 source and small-island QA tests."""
import sys
import unittest
from pathlib import Path
import numpy as np
import mercantile
from shapely.geometry import Point, box
from shapely.strtree import STRtree

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from island_source_readiness import (
    SITES, tiles_for_checks, check_added_source_preserves_original,
    transition_metrics, minor_reference_polygon, sample_one_native_height,
)


class NativeIslandSourceReadinessTests(unittest.TestCase):
    def test_z11_z12_z13_coverage_including_3_or_4_degree_source_border(self):
        for place,info in SITES.items():
            tiles=tiles_for_checks(info)
            self.assertTrue({z for z,_,_ in tiles}=={11,12,13})
            self.assertLessEqual(len(tiles),54)
            for z in (11,12,13):
                probe=mercantile.tile(*info["probe"],z)
                border=mercantile.tile(*info["degree_border"],z)
                self.assertIn((z,probe.x,probe.y),tiles)
                self.assertIn((z,border.x,border.y),tiles)

    def test_source_addition_cannot_modify_existing_height(self):
        a=np.ones((256,256),bool)
        before=np.full((256,256),50.,dtype=np.float32)
        after=before.copy()
        after[10,11]=51.
        with self.assertRaisesRegex(AssertionError,"Existing native"):
            check_added_source_preserves_original(before,a,after,a)

    def test_source_addition_cannot_remove_valid_pixel(self):
        a=np.ones((256,256),bool)
        b=a.copy()
        b[10,10]=False
        h=np.ones((256,256),dtype=np.float32)
        with self.assertRaisesRegex(AssertionError,"lost"):
            check_added_source_preserves_original(h,a,h,b)

    def test_real_extra_source_only_fills_missing_valid_mask(self):
        a=np.ones((256,256),bool)
        a[10,11]=False
        b=a.copy()
        b[10,11]=True
        old=np.ones((256,256),dtype=np.float32)
        old[10,11]=-9999.
        new=old.copy()
        new[10,11]=43.
        r=check_added_source_preserves_original(old,a,new,b)
        self.assertEqual(r["recovered_genuine_native_pixels"],1)
        self.assertEqual(r["after_missing_pixels"],0)
        self.assertEqual(r["max_original_height_delta_m"],0.)

    def test_provenance_only_counts_cog_origin_joins_with_real_valids(self):
        dem=np.full((256,256),10.,dtype=np.float32)
        valid=np.ones((256,256),bool)
        owners=np.ones((256,256),dtype=np.uint8)
        owners[:,128:]=2
        dem[:,128:]=20.
        r=transition_metrics(dem,valid,owners,["original","candidate"],"candidate")
        self.assertEqual(r["candidate_original_transition_pairs"],256)
        self.assertEqual(r["max_transition_gradient_m"],10.)
        self.assertEqual(r["flags_grad_gt40m"],0)
        self.assertTrue(r["gradient_flag_is_not_an_automatic_source_failure"])

    def test_seam_gradient_risk_flag_never_confused_with_nodata(self):
        dem=np.full((256,256),10.,dtype=np.float32)
        valid=np.ones((256,256),bool)
        owners=np.ones((256,256),dtype=np.uint8)
        owners[:,128:]=2
        dem[:,128:]=100.
        valid[50,127]=False
        r=transition_metrics(dem,valid,owners,["old","extra"],"extra")
        self.assertEqual(r["flags_grad_gt40m"],255)
        self.assertEqual(r["candidate_original_transition_pairs"],255)
        self.assertGreaterEqual(r["transition_incomplete_adjacent_pixels"],1)

    def test_minor_island_reference_only_accepted_on_polygon(self):
        shapes=[box(-80,14,-79.99,14.01),box(-79.8,14.2,-79.7,14.3)]
        tree=STRtree(shapes)
        r=minor_reference_polygon(Point(-79.995,14.005),shapes,tree)
        self.assertIsNotNone(r)
        self.assertIsNone(minor_reference_polygon(Point(-79.9,14.1),shapes,tree))

    def test_masked_native_sample_not_converted_to_elevation_zero(self):
        class Raster:
            bounds=type("Bounds",(),{"left":-80.,"right":-79.,"bottom":14.,"top":15.})()
            nodata=-9999.
            def sample(self,coords,masked):
                yield np.ma.array([-9999.],mask=[True])
        r=sample_one_native_height(Raster(),-79.6,14.6)
        self.assertEqual(r["status"],"native_COG_NoData")
        self.assertIsNone(r["height_m"])


if __name__=="__main__":
    unittest.main()
