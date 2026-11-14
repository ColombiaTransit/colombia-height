"""Strict no-repeat native source increment: accurate bounds, unchanged heights."""
import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_tumaco_140_delta import (
    P, compare_masks, rigorous_land_bounds, safe_sources,
    classify, source_influenced, frozen_land_before,
)
from stage_tumaco_140 import ISLANDS,TUMACO


class Tumaco140DeltaTests(unittest.TestCase):
    def test_139_COGs_in_exact_same_order_and_single_new_original(self):
        old=[{"name":f"o{i}","status":"ok"} for i in range(137)]
        old += [{"name":s,"status":"ok"} for s in sorted(ISLANDS)]
        safe_sources(old,old+[{"name":TUMACO,"status":"ok"}])
        moved=old[1:]+old[:1]+[{"name":TUMACO,"status":"ok"}]
        with self.assertRaisesRegex(AssertionError,"Existing 139 source order"):
            safe_sources(old,moved)

    def test_native_added_only_at_missing_pixel(self):
        a=np.ones((256,256),bool);a[10,14]=False
        b=a.copy();b[10,14]=True
        h=np.full((256,256),20.,dtype=np.float32)
        k=h.copy();k[10,14]=11.
        self.assertEqual(compare_masks(a,h,b,k),1)
        self.assertEqual(classify(P),"full_dem_coverage")
        self.assertEqual(classify(P-1),"partial_dem_coverage")
        self.assertEqual(classify(0),"no_dem_coverage")

    def test_old_valid_height_never_changed(self):
        a=np.ones((256,256),bool)
        h=np.zeros((256,256),np.float32)
        new=h.copy();new[12,23]=.1
        with self.assertRaisesRegex(AssertionError,"changed"):
            compare_masks(a,h,a,new)

    def test_no_original_valid_height_can_disappear(self):
        a=np.ones((256,256),bool)
        b=a.copy();b[1,1]=False
        h=np.ones((256,256),np.float32)
        with self.assertRaisesRegex(AssertionError,"disappeared"):
            compare_masks(a,h,b,h)

    def test_OSM_recovery_bounds_not_invented(self):
        self.assertEqual(rigorous_land_bounds(100,20,30),(0,20))
        self.assertEqual(rigorous_land_bounds(100,20,100),(20,20))
        self.assertEqual(rigorous_land_bounds(100,80,75),(55,75))
        with self.assertRaises(ValueError):
            rigorous_land_bounds(100,120,1)

    def test_baseline_without_139_changes_uses_exact_137_report(self):
        zxy=(13,2298,4058)
        base={zxy:{
            "native_missing_dem_pixels":12000,
            "missing_inside_osm_land":6816,
            "missing_osm_land_and_igac_department":5686,
        }}
        self.assertEqual(frozen_land_before(zxy,12000,base,{},{}),(6816,5686))
        with self.assertRaisesRegex(AssertionError,"native mask differ"):
            frozen_land_before(zxy,11999,base,{},{})


if __name__=="__main__":
    unittest.main()
