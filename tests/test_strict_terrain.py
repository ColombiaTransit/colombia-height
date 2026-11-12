import sys
import unittest
from pathlib import Path

import mercantile
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from strict_terrain import aligned_bounds, encode_tile, REGIONS
from medellin_terrain import rgb_decode

class TileSafetyTests(unittest.TestCase):
    def test_aligned_bounds_cover_original_request(self):
        requested = REGIONS["antioquia"]
        aligned = aligned_bounds(requested, 11)
        self.assertLessEqual(aligned[0], requested[0])
        self.assertLessEqual(aligned[1], requested[1])
        self.assertGreaterEqual(aligned[2], requested[2])
        self.assertGreaterEqual(aligned[3], requested[3])
        self.assertEqual(aligned, aligned_bounds(aligned,11))

    def test_no_data_is_rejected(self):
        arr=np.full((256,256),1500.0,dtype="float32")
        arr[0,0]=-9999.0
        with self.assertRaises(ValueError):
            encode_tile(arr)
        png,count=encode_tile(arr,strict=False)
        self.assertIsNone(png)
        self.assertEqual(count,1)

    def test_valid_rgb_no_fabricated_trench(self):
        arr=np.full((256,256),1491.8,dtype="float32")
        png,count=encode_tile(arr)
        self.assertEqual(count,0)
        from PIL import Image
        from io import BytesIO
        rgb=Image.open(BytesIO(png)).convert("RGB").getpixel((0,0))
        self.assertAlmostEqual(rgb_decode(rgb),1491.8,places=1)

if __name__ == "__main__":
    unittest.main()
