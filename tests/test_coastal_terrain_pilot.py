import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from coastal_terrain_pilot import classify_validity, data_validity, REGIONS
from strict_terrain import encode_tile
from medellin_terrain import NODATA

class CoastalTerrainPilotTests(unittest.TestCase):
    def test_classification_is_not_ocean_guess(self):
        valid=np.array([[True,False],[True,False]])
        reference_land=np.array([[True,True],[False,False]])
        r=classify_validity(valid,reference_land)
        self.assertEqual(r["valid_reference_land"],1)
        self.assertEqual(r["missing_reference_land"],1)
        self.assertEqual(r["valid_outside_reference_land"],1)
        self.assertEqual(r["missing_outside_reference_land"],1)
    def test_missing_pixels_never_terrain_rgb(self):
        raster=np.zeros((256,256),dtype=np.float32)
        raster[0,5]=NODATA
        raw,missing=encode_tile(raster,strict=False)
        self.assertIsNone(raw)
        self.assertEqual(missing,1)
    def test_valid_zero_is_valid_height(self):
        raster=np.zeros((256,256),dtype=np.float32)
        raw,missing=encode_tile(raster,strict=False)
        self.assertIsNotNone(raw)
        self.assertEqual(missing,0)
        self.assertTrue(np.all(data_validity(raster)))
    def test_three_regions(self):
        self.assertEqual(set(REGIONS),{"cartagena","buenaventura","san_andres"})

if __name__=="__main__":
    unittest.main()
