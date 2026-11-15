"""Offline contract of national real-product QA decoders; no source downloads."""
import io
import json
import unittest

import numpy as np
from PIL import Image

from qa_national_terrain_mbtiles import unpack_png, json_numpy_scalar
from medellin_terrain import rgb_encode

class NationalQADecodeTests(unittest.TestCase):
    def make_pngs(self,land,mask=None):
        heights=np.where(land,2150.1,0.0)
        with io.BytesIO() as buf:
            Image.fromarray(rgb_encode(heights),mode="RGB").save(buf,format="PNG")
            terrain=buf.getvalue()
        with io.BytesIO() as buf:
            Image.fromarray(mask if mask is not None else
                            np.where(land,255,0).astype(np.uint8),mode="L").save(buf,format="PNG")
            mask_data=buf.getvalue()
        return terrain,mask_data

    def test_exact_rgb_height_and_OSM_mask(self):
        land=np.zeros((256,256),bool)
        land[:,0:130]=True
        terrain,mask=self.make_pngs(land)
        packed,stored_land=unpack_png(terrain,mask)
        np.testing.assert_array_equal(stored_land,land)
        self.assertTrue(np.all(packed[~land]==100000))
        self.assertTrue(np.all(packed[land]==121501))

    def test_invalid_factual_mask_pixels_fail(self):
        land=np.zeros((256,256),bool)
        land[30:150,:]=True
        mask=np.where(land,255,0).astype(np.uint8)
        mask[0,0]=42
        with self.assertRaisesRegex(AssertionError,"only 255 true"):
            unpack_png(*self.make_pngs(land,mask))

    def test_actual_numpy_integer_metrics_are_serializable(self):
        report={"single_height_land_tiles":np.int64(21),
                "is_complete":np.bool_(True),
                "max_elevation_m":np.float32(5400.1)}
        parsed=json.loads(json.dumps(report,default=json_numpy_scalar))
        self.assertEqual(parsed["single_height_land_tiles"],21)
        self.assertIs(parsed["is_complete"],True)
        self.assertAlmostEqual(parsed["max_elevation_m"],5400.1,places=2)
        with self.assertRaises(TypeError):
            json.dumps({"invalid":object()},default=json_numpy_scalar)

    def test_rgb_png_must_be_native_256(self):
        land=np.ones((256,256),bool)
        terrain,mask=self.make_pngs(land)
        with io.BytesIO() as buf:
            Image.fromarray(np.zeros((128,128,3),dtype=np.uint8),"RGB").save(buf,format="PNG")
            short=buf.getvalue()
        with self.assertRaisesRegex(AssertionError,"256x256"):
            unpack_png(short,mask)

if __name__=="__main__":
    unittest.main()
