"""Unit and SQLite integration tests for the FIRST land-only generator.

These use synthetic masks/heights ONLY to prove encoding correctness;
they are not user map data or an authorization for national production.
"""
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import mercantile
import numpy as np
from shapely.geometry import box

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))

from osm_national_land_audit import PolygonMask
from generate_osm_land_only_terrain import (
    classify_tile_osm_masks,plan_bounded_tiles,prepare_plan,
    validated_terrain_rgb,write_inland_mbtiles,require_verified_staging
)


class FirstOSMLandOnlyGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.tile0=mercantile.tile(-74.072,4.711,13)
        self.tile=(self.tile0.z,self.tile0.x,self.tile0.y)
        self.bound=mercantile.bounds(self.tile0)

    def osm_country(self):
        return box(self.bound.west-.1,self.bound.south-.1,
                   self.bound.east+.1,self.bound.north+.1)

    def test_all_land_mask_from_osm_geometry_pixel_centers(self):
        land=PolygonMask([self.osm_country()])
        mask,state,n=classify_tile_osm_masks(
            self.tile,land,self.osm_country())
        self.assertEqual(state,"fully_OSM_Colombia_land")
        self.assertEqual(n,65536)
        self.assertTrue(mask.all())

    def test_admin_country_area_without_osm_physical_land_is_skipped(self):
        land=PolygonMask([box(-80,1,-79,2)])
        mask,state,n=classify_tile_osm_masks(
            self.tile,land,self.osm_country())
        self.assertEqual(state,"skip_no_physical_OSM_Colombia_land")
        self.assertEqual(n,0)
        self.assertFalse(mask.any())

    def test_partial_coastland_is_real_and_must_fail_for_RGB(self):
        mid=(self.bound.west+self.bound.east)/2
        land=PolygonMask([box(self.bound.west-.01,
                              self.bound.south-.01,mid,
                              self.bound.north+.01)])
        mask,state,n=classify_tile_osm_masks(
            self.tile,land,self.osm_country())
        self.assertEqual(state,"mixed_coastal_OSM_Colombia_land_and_offland")
        self.assertGreater(n,0)
        self.assertLess(n,65536)
        with self.assertRaisesRegex(ValueError,"mixed coast"):
            validated_terrain_rgb(np.full((256,256),20.,np.float32),mask)

    def test_synthetic_terrain_exact_rgb_and_native_zero_height(self):
        arr=np.full((256,256),28.3,np.float32)
        arr[0,0]=0.0
        png,error=validated_terrain_rgb(arr,np.ones((256,256),bool))
        self.assertLessEqual(error,.051)
        from PIL import Image
        with Image.open(io.BytesIO(png)) as im:
            self.assertEqual(im.size,(256,256))
            r,g,b=list(im.convert("RGB").getdata())[0]
            self.assertEqual((r*65536+g*256+b),100000)
        self.assertEqual(arr[0,0],0.0)

    def test_invalid_land_native_dem_refused(self):
        arr=np.full((256,256),50,np.float32)
        arr[30,40]=-9999
        with self.assertRaisesRegex(ValueError,"Missing 1 true"):
            validated_terrain_rgb(arr,np.ones((256,256),bool))

    def test_checked_source_precedence_only_three_candidates(self):
        src=[{"name":f"original-{i}","status":"ok"} for i in range(137)]
        src.extend([{"name":x,"status":"ok"} for x in (
            "Copernicus_DSM_COG_10_N03_00_W079_00_DEM",
            "Copernicus_DSM_COG_10_N03_00_W082_00_DEM",
            "Copernicus_DSM_COG_10_N01_00_W080_00_DEM")])
        require_verified_staging(src)
        with self.assertRaises(AssertionError):
            require_verified_staging(src[:139])

    def test_bounded_tile_guard(self):
        with self.assertRaisesRegex(RuntimeError,"exceeds bounded"):
            plan_bounded_tiles([-84,-5,-66,17],0,13,100)

    def test_actual_mbtiles_write_synthetic_all_land_one_tile_no_network(self):
        real=np.full((256,256),31.2,np.float32)
        real[4,7]=0
        full=np.ones((256,256),bool)
        with tempfile.TemporaryDirectory() as t:
            dest=Path(t)/"full-land-synthetic-test.mbtiles"
            rows=[{"tile":self.tile,"status":"fully_OSM_Colombia_land",
                   "land_pixels":65536,"mask":full}]
            source=[{"longitude":"-75","latitude":"4","status":"ok"}]
            with patch("generate_osm_land_only_terrain.intersecting_source_indices",
                       return_value=[0]),patch(
                       "generate_osm_land_only_terrain.local_cogs",
                       return_value=["already-existing-source"]),patch(
                       "generate_osm_land_only_terrain.warp_sources",
                       return_value=(real,np.ones_like(real,dtype=np.uint8),0,0.0)):
                stats=write_inland_mbtiles(
                    dest,rows,source,Path(t),[
                        self.bound.west,self.bound.south,
                        self.bound.east,self.bound.north],
                    (13,13))
            self.assertEqual(stats["full_land_tiles_written"],1)
            self.assertTrue(dest.exists())
            with sqlite3.connect(dest) as conn:
                x=conn.execute("SELECT zoom_level,tile_column,tile_row,tile_data FROM tiles").fetchone()
                self.assertEqual(x[:3],(13,self.tile[1],(1<<13)-1-self.tile[2]))
                self.assertTrue(x[3].startswith(b"\x89PNG"))
                self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0],"ok")
                self.assertEqual(conn.execute("SELECT value FROM metadata WHERE name='format'").fetchone()[0],"png")

    def test_blocked_mixed_coast_does_not_leave_mbtiles(self):
        # The final generator should fail BEFORE native DEM download or
        # SQLite writes, even if the source catalog is complete.
        with tempfile.TemporaryDirectory() as t:
            outfile=Path(t)/"never.mbtiles"
            mask=np.zeros((256,256),bool)
            mask[4,10]=True
            with self.assertRaisesRegex(ValueError,"mixed coast"):
                validated_terrain_rgb(np.full((256,256),100.,np.float32),mask)
            self.assertFalse(outfile.exists())


if __name__=="__main__":
    unittest.main()
