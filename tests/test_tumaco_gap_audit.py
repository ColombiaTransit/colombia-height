import sys,unittest
from pathlib import Path
import numpy as np
from rasterio.coords import BoundingBox
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from tumaco_gap_audit import extent_of_mask,classify_missing_pixel_samples

class TumacoGapAuditTests(unittest.TestCase):
    def test_empty_mask(self):
        self.assertIsNone(extent_of_mask(np.zeros((256,256),bool),BoundingBox(-1,-1,1,1)))
    def test_bounds_are_finite(self):
        mask=np.zeros((256,256),bool)
        mask[100:120,25:45]=True
        bounds=BoundingBox(-1000,-1000,1000,1000)
        bb=extent_of_mask(mask,bounds)
        self.assertEqual(len(bb),4)
        self.assertLess(bb[0],bb[2])
        self.assertLess(bb[1],bb[3])
    def test_no_missing_samples(self):
        mask=np.zeros((256,256),bool)
        self.assertEqual(classify_missing_pixel_samples([],mask,BoundingBox(0,0,1,1))["sample_count"],0)

if __name__=="__main__":unittest.main()
