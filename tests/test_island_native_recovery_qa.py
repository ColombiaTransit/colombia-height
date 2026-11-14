"""Offline tests of exact island DEM recovery and non-authoritative nearby geometry."""
import sys
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from island_native_recovery_qa import (
    compare_exact_island_pixels, shortlist_unresolved_polygon_leads, xyz_centers,
)


class IslandNativeRecoveryTests(unittest.TestCase):
    def masks(self):
        before = np.ones((256, 256), dtype=bool)
        before[:2, :2] = False
        after = before.copy()
        after[0, :2] = True
        heights_before = np.full((256, 256), 20., dtype=np.float32)
        heights_after = heights_before.copy()
        heights_after[0, :2] = [10., 11.]
        island = np.zeros((256, 256), dtype=bool)
        island[:2, :2] = True
        return before, heights_before, after, heights_after, island

    def test_native_recovery_uses_exact_island_pixel_centers_only(self):
        args = self.masks()
        r = compare_exact_island_pixels(*args, expected_missing=4)
        self.assertEqual(r["OSM_island_native_missing_before"], 4)
        self.assertEqual(r["OSM_island_native_recovered_with_real_COG"], 2)
        self.assertEqual(r["OSM_island_native_still_missing_after"], 2)
        self.assertEqual(r["real_recovered_height_min_m"], 10.)
        self.assertEqual(r["real_recovered_height_max_m"], 11.)
        self.assertEqual(r["native_heights_unchanged_max_abs_m"], 0.)

    def test_original_elevation_immutability_enforced(self):
        before, hb, after, ha, island = self.masks()
        ha[20, 20] = 100.
        with self.assertRaisesRegex(AssertionError, "Original valid heights changed"):
            compare_exact_island_pixels(before, hb, after, ha, island, 4)

    def test_valid_dem_cannot_disappear(self):
        before, hb, after, ha, island = self.masks()
        after[20, 20] = False
        with self.assertRaisesRegex(AssertionError, "were lost"):
            compare_exact_island_pixels(before, hb, after, ha, island, 4)

    def test_original_island_gap_baseline_is_frozen(self):
        args = self.masks()
        with self.assertRaisesRegex(AssertionError, "baseline mismatch"):
            compare_exact_island_pixels(*args, expected_missing=97)

    def test_nodata_is_not_a_recovered_height(self):
        before, hb, after, ha, island = self.masks()
        ha[0, 0] = -9999.
        with self.assertRaisesRegex(AssertionError, "NoData"):
            compare_exact_island_pixels(before, hb, after, ha, island, 4)

    def test_nearest_polygon_leads_not_island_assignments(self):
        near = box(-81.373, 13.379, -81.371, 13.381)
        known = box(-81.395, 13.325, -81.365, 13.375)
        secondary = box(-78.187, 2.929, -78.185, 2.931)
        probes = [
            {"id":"santa_catalina","lon":-81.375,"lat":13.38},
            {"id":"gorgonilla","lon":-78.19,"lat":2.93},
            {"id":"providencia","lon":-81.37,"lat":13.35},
            {"id":"gorgona","lon":-78.18,"lat":2.97},
        ]
        ranked = shortlist_unresolved_polygon_leads([near, known, secondary], probes, {})
        self.assertTrue(ranked["santa_catalina"]["nearby_polygon_leads"])
        self.assertTrue(ranked["santa_catalina"]["no_polygon_or_probe_automatically_accepted"])
        self.assertTrue(ranked["gorgonilla"]["nearby_polygon_leads"])
        self.assertTrue(all(x["identity_unverified"] for x in ranked["gorgonilla"]["nearby_polygon_leads"]))
        self.assertNotIn(list(known.bounds), [x["geometry_bounds"] for x in ranked["santa_catalina"]["nearby_polygon_leads"]])

    def test_xyz_pixel_centers_wgs84_shapes(self):
        import mercantile
        t = mercantile.tile(-81.606, 4.005, 13)
        lon, lat = xyz_centers((13, t.x, t.y))
        self.assertEqual(lon.shape, (256, 256))
        self.assertEqual(lat.shape, (256, 256))
        self.assertLess(float(lon[0, 0]), float(lon[0, -1]))
        self.assertGreater(float(lat[0, 0]), float(lat[-1, 0]))


if __name__ == "__main__":
    unittest.main()
