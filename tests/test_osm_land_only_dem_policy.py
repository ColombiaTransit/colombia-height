"""Strict physical OSM land mask, no bathymetry or invented marine elevations."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from osm_land_only_dem_policy import (
    verify_osm_land_only_native_dem, require_renderer_for_mixed_coast_tile,
)


class OSMLandOnlyDEMPolicyTests(unittest.TestCase):
    def baseline(self):
        return (np.full((256,256),-9999.,dtype=np.float32),
                np.zeros((256,256),dtype=bool),
                np.zeros((256,256),dtype=bool))

    def test_unknown_ocean_not_required_no_zero_heights_fabricated(self):
        heights,land,col=self.baseline()
        report,required=verify_osm_land_only_native_dem(heights,land,col)
        self.assertEqual(report["land_only_gate"],"skip_tile_no_OSM_Colombia_physical_land")
        self.assertEqual(report["OSM_Colombia_land_pixels_missing_real_native_elevation"],0)
        self.assertFalse(report["emit_entirely_ocean_tile"])
        self.assertEqual(int(required.sum()),0)
        self.assertTrue(np.all(heights==-9999.))

    def test_osm_country_area_without_coastline_land_requires_no_dem(self):
        heights,land,col=self.baseline()
        col[:100,:]=True # a sovereign/marine country polygon is NOT land
        report,_=verify_osm_land_only_native_dem(heights,land,col)
        self.assertEqual(report["OSM_Colombia_physical_land_pixel_centers"],0)

    def test_real_native_0_metre_on_osm_land_is_valid_not_synthetic(self):
        heights,land,col=self.baseline()
        land[1,2]=col[1,2]=True
        heights[1,2]=0.
        report,_=verify_osm_land_only_native_dem(heights,land,col)
        self.assertEqual(report["OSM_Colombia_land_pixels_missing_real_native_elevation"],0)
        self.assertEqual(report["native_valid_pixel_centers_on_required_OSM_land"],1)

    def test_missing_true_colombian_land_always_blocks(self):
        heights,land,col=self.baseline()
        land[1,2]=col[1,2]=True
        with self.assertRaisesRegex(ValueError,"Refuse to export"):
            verify_osm_land_only_native_dem(heights,land,col)

    def test_OSM_foreign_land_does_not_require_colombian_dem(self):
        heights,land,col=self.baseline()
        land[10,20]=True
        r,_=verify_osm_land_only_native_dem(heights,land,col)
        self.assertEqual(r["OSM_Colombia_physical_land_pixel_centers"],0)

    def test_partial_coast_tile_fails_before_renderer_alpha_verified(self):
        heights,land,col=self.baseline()
        land[10,20]=col[10,20]=True
        heights[10,20]=17.
        r,_=verify_osm_land_only_native_dem(heights,land,col)
        self.assertTrue(r["mixed_coast_tile_renderer_alpha_semantics_still_need_validation"])
        with self.assertRaisesRegex(RuntimeError,"alpha"):
            require_renderer_for_mixed_coast_tile(r,False)
        self.assertTrue(require_renderer_for_mixed_coast_tile(r,True))

    def test_all_covered_colombian_land_permits_normal_RGB_potentially(self):
        heights=np.full((256,256),50.,np.float32)
        land=np.ones((256,256),bool)
        colombia=land.copy()
        r,_=verify_osm_land_only_native_dem(heights,land,colombia)
        self.assertFalse(r["mixed_coast_tile_renderer_alpha_semantics_still_need_validation"])
        self.assertTrue(require_renderer_for_mixed_coast_tile(r,False))

    def test_unknown_masks_must_not_be_coerced_to_land(self):
        heights,land,col=self.baseline()
        with self.assertRaises(TypeError):
            verify_osm_land_only_native_dem(heights,land.astype(int),col)

    def test_wrong_pixel_grid_fails_closed(self):
        heights,land,col=self.baseline()
        with self.assertRaises(ValueError):
            verify_osm_land_only_native_dem(heights[:2],land,col)


if __name__=="__main__":
    unittest.main()
