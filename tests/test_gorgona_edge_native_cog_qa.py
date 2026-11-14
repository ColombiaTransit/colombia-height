"""Offline mathematical tests for real DEM recovery bounds without OSM re-download."""
import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from gorgona_edge_native_cog_qa import strict_native_recovery, cell_mask


class GorgonaNativeQA(unittest.TestCase):
    def samples(self,recovered=8):
        before=np.ones((256,256),bool)
        before.ravel()[:10]=False
        after=before.copy()
        after.ravel()[:recovered]=True
        bheight=np.full((256,256),100.,np.float32)
        aheight=bheight.copy()
        incell=np.zeros((256,256),bool)
        incell.ravel()[:10]=True
        return before,bheight,after,aheight,incell

    def test_proven_lower_upper_bounds_without_per_pixel_osm_polygon(self):
        out=strict_native_recovery(*self.samples(8),10,4)
        self.assertEqual(out["native_pixels_recovered"],8)
        self.assertEqual(out["recovered_OSM_land_pixels_lower_bound"],2)
        self.assertEqual(out["recovered_OSM_land_pixels_upper_bound"],4)
        self.assertTrue(out["OSM_land_recovery_bounds_not_direct_polygon_retest"])

    def test_all_missing_source_pixels_recovered_proves_exact_prior_osm_land_count(self):
        out=strict_native_recovery(*self.samples(10),10,4)
        self.assertEqual(out["recovered_OSM_land_pixels_lower_bound"],4)
        self.assertEqual(out["recovered_OSM_land_pixels_upper_bound"],4)

    def test_missing_land_pixel_can_remain_all_unrecovered(self):
        out=strict_native_recovery(*self.samples(0),10,4)
        self.assertEqual(out["recovered_OSM_land_pixels_lower_bound"],0)
        self.assertEqual(out["recovered_OSM_land_pixels_upper_bound"],0)

    def test_no_original_valid_height_may_change(self):
        arrays=list(self.samples())
        arrays[3]=np.array(arrays[3],copy=True)
        arrays[3][200,200]=102.
        with self.assertRaisesRegex(AssertionError,"elevation changed"):
            strict_native_recovery(*arrays,10,4)

    def test_loss_of_native_valid_pixel_fails_closed(self):
        arrays=list(self.samples())
        arrays[2]=np.array(arrays[2],copy=True)
        arrays[2][200,200]=False
        with self.assertRaisesRegex(AssertionError,"vanished"):
            strict_native_recovery(*arrays,10,4)

    def test_wrong_cell_count_does_not_claim_osm_recovery(self):
        with self.assertRaisesRegex(AssertionError,"differs"):
            strict_native_recovery(*self.samples(),9,4)

    def test_no_invalid_mask_geometry(self):
        with self.assertRaisesRegex(ValueError,"Unaligned"):
            arrays=list(self.samples())
            arrays[4]=arrays[4][:254]
            strict_native_recovery(*arrays,10,4)

    def test_geographic_cell_has_native_xyz_shape(self):
        import mercantile
        t=mercantile.tile(-78.9,3.3,13)
        mask=cell_mask((13,t.x,t.y))
        self.assertEqual(mask.shape,(256,256))
        self.assertTrue(mask.all())


if __name__=="__main__":
    unittest.main()
