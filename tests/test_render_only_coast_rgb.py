"""Unit and SQLite integration tests: explicit visual-only OSM sea surface.

No native COGs or global OSM datasets are downloaded. These fixtures are NOT
valid Colombian elevation data and do not authorize national publication.
"""
import io
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mercantile
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from generate_osm_land_only_terrain import write_inland_mbtiles
from render_only_coast_rgb import (
    COAST_MODE, decode_mask_png, decode_terrain_rgb, encode_coast_render_only,
)


class RenderOnlyCoastTests(unittest.TestCase):
    def setUp(self):
        self.height = np.full((256,256), -9999.0, dtype=np.float32)
        self.land = np.zeros((256,256), dtype=bool)
        self.land[:, :128] = True
        self.physical = self.land.copy()
        self.height[self.land] = 30.1
        self.height[12, 20] = 0.0  # real native zero on actual OSM land
        self.height[18, 31] = -1.2 # negative valid shoreline land

    def test_true_land_preserved_and_sea_is_flat_visual_only(self):
        rgb, mask_png, qa = encode_coast_render_only(
            self.height, self.land, self.physical)
        self.assertEqual(qa["original_valid_colombian_land_pixels"], 32768)
        self.assertEqual(qa["render_only_OSM_sea_surface_pixels"], 32768)
        self.assertEqual(qa["foreign_land_pixels_encoded_as_sea"], 0)
        self.assertTrue(qa["sea_surface_height_is_not_bathymetry"])
        self.assertEqual(qa["policy"], COAST_MODE)
        with Image.open(io.BytesIO(rgb)) as im:
            self.assertEqual(im.mode, "RGB")
        decoded = decode_terrain_rgb(rgb)
        np.testing.assert_allclose(decoded[self.land], self.height[self.land], atol=0.051)
        self.assertTrue((decoded[~self.land] == 0).all())
        np.testing.assert_array_equal(decode_mask_png(mask_png), self.land)
        self.assertEqual(decoded[12, 20], 0.0)
        self.assertAlmostEqual(decoded[18, 31], -1.2)

    def test_nodata_on_real_land_blocked(self):
        bad = self.height.copy()
        bad[1,1] = -9999.0
        with self.assertRaisesRegex(ValueError, "missing true native"):
            encode_coast_render_only(bad, self.land, self.physical)

    def test_offland_source_can_be_missing_or_negative_without_bathymetry(self):
        self.height[:,128:] = -250.0  # ignored; not retained as bathymetry
        rgb, mask, qa = encode_coast_render_only(
            self.height, self.land, self.physical)
        self.assertTrue((decode_terrain_rgb(rgb)[:,128:] == 0).all())

    def test_any_non_colombian_physical_land_blocks_sea_placeholder(self):
        physical = self.physical.copy()
        physical[2,200] = True
        with self.assertRaisesRegex(ValueError, "foreign/out-of-country"):
            encode_coast_render_only(self.height, self.land, physical)

    def test_explicit_foreign_outscope_is_flat_not_sea_and_land_stays_native(self):
        from render_only_coast_rgb import COUNTRY_CLIP_MODE
        foreign=self.physical.copy()
        foreign[8,200]=True
        rgb,mask,qa=encode_coast_render_only(
            self.height,self.land,foreign,allow_offscope_flat=True)
        self.assertEqual(qa["policy"],COUNTRY_CLIP_MODE)
        self.assertEqual(qa["foreign_land_pixels_encoded_as_sea"],0)
        self.assertEqual(qa["render_only_offscope_foreign_land_pixels"],1)
        self.assertEqual(qa["render_only_OSM_sea_surface_pixels"],32767)
        self.assertEqual(qa["render_only_total_background_pixels"],32768)
        np.testing.assert_array_equal(decode_mask_png(mask),self.land)
        pixels=decode_terrain_rgb(rgb)
        np.testing.assert_allclose(pixels[self.land],self.height[self.land],atol=0.051)
        self.assertEqual(pixels[8,200],0.0)
        self.assertTrue((pixels[~self.land]==0).all())

    def test_refuse_zero_land_and_bad_mask_or_overflow(self):
        with self.assertRaisesRegex(ValueError, "zero-only sea"):
            encode_coast_render_only(
                self.height, np.zeros_like(self.land), np.zeros_like(self.physical))
        with self.assertRaises(TypeError):
            encode_coast_render_only(self.height, self.land.astype("int8"), self.physical)
        with self.assertRaisesRegex(ValueError, "range"):
            too_high = self.height.copy()
            too_high[8,8] = 1667722.0
            encode_coast_render_only(too_high, self.land, self.physical)

    def test_original_writer_new_opt_in_mode_writes_mask_in_same_sqlite(self):
        tile = mercantile.tile(-75.55, 10.4, 12)
        rows=[{"tile":(tile.z,tile.x,tile.y),"status":"mixed_coastal_OSM_Colombia_land_and_offland",
               "land_pixels":int(self.land.sum()),
               "mask":self.land, "physical_mask":self.physical}]
        fake_source = [{"longitude":"-76","latitude":"10","status":"ok"}]
        with tempfile.TemporaryDirectory() as temp:
            mbtiles = Path(temp) / "mixed.mbtiles"
            with patch("generate_osm_land_only_terrain.intersecting_source_indices",
                       return_value=[0]), patch(
                           "generate_osm_land_only_terrain.local_cogs",
                           return_value=["cached-source"]), patch(
                           "generate_osm_land_only_terrain.warp_sources",
                           return_value=(self.height, np.ones_like(self.height,dtype=np.uint8),0,0)):
                stats = write_inland_mbtiles(
                    mbtiles,rows,fake_source,Path(temp),[-76,10,-75,11],(12,12),
                    coast_render_surface=True)
            self.assertEqual(stats["mixed_coast_tiles_written"],1)
            self.assertEqual(stats["full_land_tiles_written"],0)
            self.assertEqual(stats["render_only_OSM_sea_surface_pixels"],32768)
            with sqlite3.connect(mbtiles) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                meta=dict(db.execute("SELECT name,value FROM metadata"))
                self.assertEqual(meta["coast_render_mode"],COAST_MODE)
                self.assertEqual(meta["sea_surface_is_bathymetry"],"false")
                t=db.execute("SELECT zoom_level,tile_column,tile_row,tile_data FROM tiles").fetchone()
                mask_t=db.execute("SELECT zoom_level,tile_column,tile_row,mask_png FROM osm_land_mask").fetchone()
                self.assertEqual(t[:3],mask_t[:3])
                np.testing.assert_array_equal(decode_mask_png(mask_t[3]),self.land)
                np.testing.assert_allclose(
                    decode_terrain_rgb(t[3])[self.land],
                    self.height[self.land],atol=0.051)

    def test_original_strict_writer_still_refuses_coastal_native_download(self):
        tile = mercantile.tile(-75.55, 10.4, 12)
        rows=[{"tile":tile,"status":"mixed_coastal_OSM_Colombia_land_and_offland",
               "land_pixels":32768,"mask":self.land}]
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "not-created.mbtiles"
            with patch("generate_osm_land_only_terrain.local_cogs") as loader:
                with self.assertRaisesRegex(AssertionError,"Coast tiles require explicit"):
                    write_inland_mbtiles(dest,rows,[],Path(temp),[-76,10,-75,11],(12,12))
                loader.assert_not_called()
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
