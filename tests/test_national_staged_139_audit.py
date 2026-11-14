"""Incremental national source coverage must count every tile without invented land."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from national_staged_139_audit import (
    PIXLEN, accumulate_land, compare_native_pixel_arrays,
    stage_coverage_counts, validate_stage_selection, tile_bounds_overlap_new,
)
from stage_island_sources import ALLOWLIST


class NationalStaged139Tests(unittest.TestCase):
    def test_original_unaffected_allzoom_tiles_retained_and_new_scope_added(self):
        original={(13,10,11):PIXLEN,(13,10,12):PIXLEN-5,(12,5,6):1}
        staged=set(original)|{(13,11,11)}
        affect={(13,10,12):{"staged_valid_pixels":PIXLEN,"new_scope":False},
                (13,11,11):{"staged_valid_pixels":5,"new_scope":True}}
        allcounts,byzoom,missing=stage_coverage_counts(original,staged,affect)
        self.assertEqual(allcounts["full_dem_coverage"],2)
        self.assertEqual(allcounts["partial_dem_coverage"],2)
        self.assertEqual(sum(allcounts.values()),4)
        self.assertEqual(missing["13"],PIXLEN-5)

    def test_source_new_samples_never_delete_original_dem_or_change_height(self):
        valid=np.ones((256,256),bool)
        valid[0,0]=False
        after=valid.copy();after[0,0]=True
        prev=np.full((256,256),3.,dtype=np.float32)
        new=prev.copy();new[0,0]=4.
        s=compare_native_pixel_arrays(valid,prev,after,new)
        self.assertEqual(s["newly_valid_pixels"],1)
        self.assertEqual(s["max_original_height_change_m"],0.)
        with self.assertRaisesRegex(AssertionError,"overwrote"):
            other=new.copy();other[2,2]=16.
            compare_native_pixel_arrays(valid,prev,after,other)
        with self.assertRaisesRegex(AssertionError,"removed"):
            other=after.copy();other[4,4]=False
            compare_native_pixel_arrays(valid,prev,other,new)

    def test_stage_order_must_preserve_original_priority(self):
        original=[{"name":f"original_{i}"} for i in range(137)]
        extra=[{"name":name} for name in ALLOWLIST]
        from json import loads
        from pathlib import Path
        decision=loads((Path(__file__).resolve().parents[1]/
                        "data/staged-island-source-selection-2026-11-14.json").read_text())
        self.assertEqual(len(validate_stage_selection(original,original+extra,decision)),2)
        with self.assertRaisesRegex(AssertionError,"priorities"):
            validate_stage_selection(original,original[1:]+original[:1]+extra,decision)

    def test_new_added_extent_may_include_other_countries_and_sea(self):
        target={"longitude":"-82","latitude":"3"}
        self.assertTrue(tile_bounds_overlap_new(target,(0,0,0)))
        self.assertFalse(tile_bounds_overlap_new(target,(13,2450,4000)))

    def test_igac_unavailable_must_not_become_zero(self):
        from collections import Counter
        c=Counter()
        row={"native_missing_dem_pixels":15,
             "missing_inside_osm_land":6,
             "missing_outside_osm_land_UNKNOWN_not_confirmed_ocean":9,
             "missing_osm_land_and_igac_department":None}
        accumulate_land(c,row,igac_enabled=False)
        self.assertNotIn("missing_osm_land_and_igac_department",c)
        self.assertEqual(c["missing_inside_osm_land"],6)


if __name__=="__main__":
    unittest.main()
