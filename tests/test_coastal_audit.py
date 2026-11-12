import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from coastal_audit import bbox, classify, intersect_cells, grid_land_mask, REGIONS
from rasterio.transform import from_origin
from shapely.geometry import box

class CoastAuditTests(unittest.TestCase):
    def test_cross_degree_boundaries(self):
        cells=intersect_cells((-76.1,5.9,-75.9,6.1))
        self.assertEqual(set(cells),{(5,-77),(5,-76),(6,-77),(6,-76)})

    def test_masks_keep_missing_land_separate_from_outside(self):
        valid=np.array([[True,False],[False,True]])
        land=np.array([[True,True],[False,False]])
        c=classify(valid,land)
        self.assertEqual(c["valid_inside_boundary"],1)
        self.assertEqual(c["missing_inside_boundary"],1)
        self.assertEqual(c["valid_outside_boundary"],1)
        self.assertEqual(c["missing_outside_boundary"],1)

    def test_islands_are_explicit(self):
        names={r["id"] for r in REGIONS}
        self.assertTrue({"san_andres","providencia","malpelo"}<=names)
        self.assertEqual(len(names),7)

    def test_grid_mask_shape_matches_dem(self):
        transform=from_origin(-76.0,11.0,0.01,0.01)
        rows,cols=28,34
        # Regression: rasterio.xy flattens index arrays, but output mask must
        # remain two-dimensional to match a sampled DEM window.
        mask=grid_land_mask(transform,rows,cols,box(-75.9,10.8,-75.7,10.95))
        self.assertEqual(mask.shape,(rows,cols))
        self.assertEqual(mask.dtype,np.dtype(bool))
        self.assertTrue(mask.any())
        self.assertFalse(mask.all())

    def test_bbox_is_not_a_land_mask(self):
        r=next(r for r in REGIONS if r["id"]=="malpelo")
        west,south,east,north=bbox(r)
        self.assertLess(west,r["lon"])
        self.assertGreater(north,r["lat"])

if __name__=="__main__":
    unittest.main()
