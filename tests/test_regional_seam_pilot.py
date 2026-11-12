import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from regional_seam_pilot import (
    BATCH_BASE_X, BASE_Y, bounds_for_base, decode_png,
    seam_pairs, tile_list, check_seams,
)
from medellin_terrain import rgb_encode

class RegionalSeamTests(unittest.TestCase):
    def test_batches_have_unique_tile_ids_at_all_zoom_levels(self):
        for z in (11,12,13):
            west=set(tile_list(BATCH_BASE_X["west"],BASE_Y,z))
            east=set(tile_list(BATCH_BASE_X["east"],BASE_Y,z))
            self.assertFalse(west & east)
            self.assertEqual(len(west),4*(4**(z-11)))
            self.assertEqual(len(east),4*(4**(z-11)))
    def test_bounds_are_adjacent(self):
        west=bounds_for_base(BATCH_BASE_X["west"])
        east=bounds_for_base(BATCH_BASE_X["east"])
        self.assertAlmostEqual(west[2],east[0],places=10)
        self.assertEqual((west[1],west[3]),(east[1],east[3]))
    def test_seam_pair_count_and_owner(self):
        for z in (11,12,13):
            pairs=list(seam_pairs(z))
            self.assertEqual(len(pairs),2*(1<<(z-11)))
            for _,a,b in pairs:
                self.assertEqual(b[1],a[1]+1)
                self.assertEqual(b[2],a[2])
    def test_height_rgb_encoding_roundtrip(self):
        values=np.array([[-1.2,0.0,10.15],[2000.0,5.5,123.4]],dtype=np.float32)
        raw=rgb_encode(values)
        for row in range(values.shape[0]):
            for col in range(values.shape[1]):
                pix=raw[row,col]
                height=-10000.0+(int(pix[0])*65536+int(pix[1])*256+int(pix[2]))*.1
                self.assertLessEqual(abs(height-float(values[row,col])),0.051)

if __name__=="__main__":
    unittest.main()
