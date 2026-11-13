import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import from_origin
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from regional_seam_pilot import (
    BATCH_BASE_X, BASE_Y, bounds_for_base, decode_png,
    seam_pairs, tile_list, check_seams, load_native_cog, warp_tile,
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
    def test_native_source_grid_reused_without_crop_resampling(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"synthetic-copernicus.tif"
            yy,xx=np.indices((256,256))
            values=(250 + xx*.22 + yy*.12).astype(np.float32)
            affine=from_origin(-76,7,1/256,1/256)
            with rasterio.open(path,"w",driver="GTiff",height=256,width=256,
                               count=1,dtype="float32",transform=affine,
                               crs="EPSG:4326",nodata=-32767.0) as dst:
                dst.write(values,1)
            a,transform,nodata=load_native_cog([path])
            b,transform2,nodata2=load_native_cog([path])
            self.assertEqual(transform,affine)
            self.assertEqual(transform2,affine)
            self.assertEqual(nodata,-32767.0)
            self.assertEqual(nodata2,nodata)
            sample_a=warp_tile(a,transform,(11,595,987),src_nodata=nodata)
            sample_b=warp_tile(b,transform2,(11,595,987),src_nodata=nodata2)
            self.assertTrue(np.all(np.isfinite(sample_a)))
            self.assertTrue(np.all(sample_a!=-9999))
            self.assertTrue(np.array_equal(sample_a,sample_b))
    def test_native_loader_rejects_multiple_cogs_in_pilot(self):
        with self.assertRaisesRegex(RuntimeError,"exactly one"):
            load_native_cog([Path("a.tif"),Path("b.tif")])
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
