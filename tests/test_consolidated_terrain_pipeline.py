"""Offline integration gates for the consolidated native/OSM pipeline.

Existing original generator's native warp/RGB tests remain authoritative.
This suite proves the orchestration never downloads for plan/block/skip,
preserves unique plan ownership, and will not merge incomplete coast work.
"""
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from consolidated_terrain_pipeline import (
    create_plan, load_chunk, load_plan, merge_verified_chunks, render_chunk,
)
from generate_osm_land_only_terrain import EXPECTED_STAGING_TAIL


class ConsolidatedTerrainTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.manifest = self.root / "staged140.csv"
        import csv
        originals = [{"name": f"original-{i:03d}", "latitude": "6",
                      "longitude": "-76", "status": "ok"} for i in range(137)]
        additions = [
            {"name": "Copernicus_DSM_COG_10_N03_00_W079_00_DEM",
             "latitude": "3", "longitude": "-79", "status": "ok"},
            {"name": "Copernicus_DSM_COG_10_N03_00_W082_00_DEM",
             "latitude": "3", "longitude": "-82", "status": "ok"},
            {"name": "Copernicus_DSM_COG_10_N01_00_W080_00_DEM",
             "latitude": "1", "longitude": "-80", "status": "ok"},
        ]
        self.assertEqual({x["name"] for x in additions}, EXPECTED_STAGING_TAIL)
        with self.manifest.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["name", "latitude",
                                                        "longitude", "status"])
            writer.writeheader()
            writer.writerows(originals + additions)
        self.plan_dir = self.root / "plan"
        self.results = self.root / "results"
        self.cached = self.root / "cache"

    def make_plan(self):
        return create_plan(self.manifest, self.plan_dir, minzoom=9,
                           maxzoom=9, shards=4, chunk_tiles=2)

    def _render(self, chunk_id):
        return render_chunk(
            self.plan_dir, chunk_id, self.manifest,
            self.root / "land.wkb.gz", self.root / "land.json",
            self.root / "colombia.json", self.results, self.cached)

    @staticmethod
    def fake_write(dest, rows, sources, cache, bounds, zooms):
        dest.parent.mkdir(parents=True, exist_ok=True)
        png = io.BytesIO()
        Image.fromarray(np.full((256, 256, 3), 128, dtype=np.uint8)).save(
            png, format="PNG")
        full = [r["tile"] for r in rows if r["status"] == "fully_OSM_Colombia_land"]
        skipped = len(rows) - len(full)
        with sqlite3.connect(dest) as db:
            db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY, value TEXT)")
            db.execute("INSERT INTO metadata VALUES('format', 'png')")
            db.execute("CREATE TABLE tiles(zoom_level INT, tile_column INT, "
                       "tile_row INT, tile_data BLOB, PRIMARY KEY(zoom_level,tile_column,tile_row))")
            for z, x, y in full:
                db.execute("INSERT INTO tiles VALUES(?,?,?,?)",
                           (z, x, (1 << z) - y - 1, png.getvalue()))
        return {"full_land_tiles_written": len(full),
                "skipped_all_offland": skipped,
                "max_Terrain_RGB_roundtrip_elevation_error_m": 0.0}

    def geometry_mocks(self):
        return (patch("consolidated_terrain_pipeline.load_osm_coastline_land",
                      return_value=(object(), {"reference_wkb_sha256": "examplehash"})),
                patch("consolidated_terrain_pipeline.load_osm_country",
                      return_value=object()))

    def test_plan_reuses_unique_shard_owner_and_chunks_no_native_reads(self):
        plan = self.make_plan()
        self.assertGreater(plan["candidate_tiles"], 2)
        self.assertGreater(len(plan["chunks"]), 1)
        self.assertEqual(plan["source_COGs"], 140)
        seen = set()
        for info in plan["chunks"]:
            returned, checked, tiles = load_chunk(self.plan_dir, info["id"])
            self.assertEqual(len(tiles), info["tiles"])
            self.assertEqual(returned["source_manifest_sha256"],
                             plan["source_manifest_sha256"])
            self.assertEqual(checked["id"], info["id"])
            for tile in tiles:
                self.assertNotIn(tile, seen)
                seen.add(tile)
        self.assertEqual(len(seen), plan["candidate_tiles"])
        with self.assertRaises(FileExistsError):
            self.make_plan()
        low = create_plan(self.manifest, self.root / "lowzoom",
                          minzoom=0, maxzoom=13, shards=4, chunk_tiles=250)
        self.assertEqual(low["zoom_range"], [0, 13])
        self.assertEqual(low["candidate_tiles_by_zoom"]["0"], 1)
        self.assertGreater(low["candidate_tiles_by_zoom"]["13"], 0)
        self.assertGreater(low["candidate_tiles"], plan["candidate_tiles"])
        low_0 = [
            tile for info in low["chunks"]
            for tile in load_chunk(self.root / "lowzoom", info["id"])[2]
            if tile[0] == 0
        ]
        self.assertEqual(low_0, [(0, 0, 0)])
        self.assertTrue(any(info["shard"] == 0 for info in low["chunks"]))
        with self.assertRaises(ValueError):
            create_plan(self.manifest, self.root / "invalidzoom", minzoom=0, maxzoom=14)

    def test_manifest_and_chunk_integrity_hard_gates(self):
        plan = self.make_plan()
        c = plan["chunks"][0]
        path = self.plan_dir / c["filename"]
        with path.open("a") as file:
            file.write('{"z":9,"x":1,"y":2,"tms_y":509}\n')
        with self.assertRaisesRegex(ValueError, "tampered"):
            load_chunk(self.plan_dir, c["id"])
        self.assertEqual(load_plan(self.plan_dir / "plan.json")["source_COGs"], 140)

    def test_mixed_coast_blocked_without_native_download_or_mbtiles(self):
        plan = self.make_plan()
        first = plan["chunks"][0]["id"]
        land = np.zeros((256,256), bool)
        land[1,1] = True
        def masks(tiles, osm, country):
            return ({"mixed_coastal_OSM_Colombia_land_and_offland":len(tiles)},
                    [{"tile":t,"mask":land,"land_pixels":1,
                      "status":"mixed_coastal_OSM_Colombia_land_and_offland"} for t in tiles])
        m1,m2 = self.geometry_mocks()
        with m1,m2,patch("consolidated_terrain_pipeline.prepare_plan",
                         side_effect=masks),patch(
                             "consolidated_terrain_pipeline.write_inland_mbtiles") as writer:
            with self.assertRaisesRegex(RuntimeError, "mixed coast"):
                self._render(first)
            writer.assert_not_called()
        report = json.loads((self.results / f"chunk-{first}.report.json").read_text())
        self.assertEqual(report["status"], "BLOCKED_mixed_coast")
        self.assertFalse((self.results / f"chunk-{first}.mbtiles").exists())
        with self.assertRaisesRegex(ValueError, "Invalid or blocked"):
            merge_verified_chunks(self.plan_dir, self.results, self.root / "no.mbtiles")

    def test_skip_only_real_offland_without_downloading_native(self):
        first = self.make_plan()["chunks"][0]["id"]
        def masks(tiles, osm, country):
            return ({"skip_no_physical_OSM_Colombia_land":len(tiles)},
                    [{"tile":t,"mask":np.zeros((256,256),bool),
                      "land_pixels":0,
                      "status":"skip_no_physical_OSM_Colombia_land"} for t in tiles])
        m1,m2 = self.geometry_mocks()
        with m1,m2,patch("consolidated_terrain_pipeline.prepare_plan",
                         side_effect=masks),patch(
                             "consolidated_terrain_pipeline.write_inland_mbtiles") as writer:
            report = self._render(first)
            writer.assert_not_called()
        self.assertEqual(report["status"], "SKIPPED_no_Colombian_OSM_land")
        self.assertEqual(report["skipped_all_offland"], report["planned_tiles"])

    def test_consolidated_inland_render_and_existing_merge(self):
        plan = self.make_plan()
        full = np.ones((256,256), bool)
        def masks(tiles, osm, country):
            return ({"fully_OSM_Colombia_land":len(tiles)},
                    [{"tile":t,"mask":full,"land_pixels":65536,
                      "status":"fully_OSM_Colombia_land"} for t in tiles])
        m1,m2 = self.geometry_mocks()
        with m1,m2,patch("consolidated_terrain_pipeline.prepare_plan",
                         side_effect=masks),patch(
                             "consolidated_terrain_pipeline.write_inland_mbtiles",
                             side_effect=self.fake_write):
            for chunk in plan["chunks"]:
                self.assertEqual(self._render(chunk["id"])["status"],
                                 "SUCCESS_inland_only")
        merged = merge_verified_chunks(
            self.plan_dir,self.results,self.root / "merged.mbtiles")
        self.assertEqual(merged["tiles"],plan["candidate_tiles"])
        self.assertEqual(merged["chunks_checked"],len(plan["chunks"]))
        self.assertFalse(merged["national_release_authorized"])
        self.assertTrue((self.root / "merged.mbtiles").exists())
        with self.assertRaises(FileExistsError):
            self._render(plan["chunks"][0]["id"])

    def test_merge_fails_for_corrupted_report_or_missing_chunk(self):
        plan = self.make_plan()
        self.results.mkdir()
        c = plan["chunks"][0]
        path = self.results / f"chunk-{c['id']}.report.json"
        path.write_text(json.dumps({
            "schema": "colombia-osm-land-only-chunk-v1",
            "chunk_id": c["id"],
            "chunk_sha256": c["sha256"],
            "source_manifest_sha256": plan["source_manifest_sha256"],
            "national_release_authorized": False,
            "planned_tiles": c["tiles"],
            "full_land_tiles_written": 0,
            "skipped_all_offland": c["tiles"] - 1,
            "status": "SKIPPED_no_Colombian_OSM_land",
            "blocked_coastal_tiles": [],
        }))
        with self.assertRaisesRegex(ValueError, "Missing/silent skipped"):
            merge_verified_chunks(self.plan_dir,self.results,self.root / "merged.mbtiles")


    def test_opt_in_real_writer_terrain_mask_and_atomic_merged_masks(self):
        """Real in-process native writer, synthetic COG fixture, no network."""
        from render_only_coast_rgb import COAST_MODE, decode_mask_png, decode_terrain_rgb
        from consolidated_terrain_pipeline import sha256_file
        plan=self.make_plan()
        land=np.zeros((256,256),bool)
        land[:,:128]=True
        heights=np.full((256,256),-9999,dtype=np.float32)
        heights[land]=45.4
        heights[15,25]=0.0
        def classify(tiles,osm,country,include_physical=False):
            self.assertTrue(include_physical)
            return ({"mixed_coastal_OSM_Colombia_land_and_offland":len(tiles)},
                    [{"tile":t,"mask":land,"physical_mask":land.copy(),
                      "land_pixels":int(land.sum()),
                      "status":"mixed_coastal_OSM_Colombia_land_and_offland"} for t in tiles])
        m1,m2=self.geometry_mocks()
        with m1,m2,patch("consolidated_terrain_pipeline.prepare_plan",
                          side_effect=classify),patch(
                              "generate_osm_land_only_terrain.intersecting_source_indices",
                              return_value=[0]),patch(
                              "generate_osm_land_only_terrain.local_cogs",
                              return_value=["cached-original"]),patch(
                              "generate_osm_land_only_terrain.warp_sources",
                              return_value=(heights,np.ones_like(heights,dtype=np.uint8),0,0)):
            for chunk in plan["chunks"]:
                report=render_chunk(
                    self.plan_dir,chunk["id"],self.manifest,
                    self.root/"unused-osm-clip",self.root/"unused-land-meta",
                    self.root/"unused-country",self.results,self.cached,
                    coast_render_surface=True)
                self.assertEqual(report["status"],"SUCCESS_render_only_coast")
                self.assertEqual(report["coast_render_mode"],COAST_MODE)
                self.assertEqual(report["mixed_coast_tiles_written"],chunk["tiles"])
                self.assertEqual(report["full_land_tiles_written"],0)
        out=self.root/"combined-coast.mbtiles"
        merged=merge_verified_chunks(self.plan_dir,self.results,out)
        self.assertEqual(merged["status"],"MERGED_RENDER_ONLY_NOT_NATIONAL_RELEASE")
        self.assertEqual(merged["tiles"],plan["candidate_tiles"])
        self.assertFalse(merged["national_release_authorized"])
        with sqlite3.connect(out) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0],"ok")
            meta=dict(db.execute("SELECT name,value FROM metadata"))
            self.assertEqual(meta["coast_render_mode"],COAST_MODE)
            self.assertEqual(meta["sea_surface_is_bathymetry"],"false")
            count=db.execute("SELECT count(*) FROM osm_land_mask").fetchone()[0]
            self.assertEqual(count,plan["candidate_tiles"])
            t=db.execute("""SELECT t.tile_data,m.mask_png FROM tiles t
                            JOIN osm_land_mask m USING(zoom_level,tile_column,tile_row)
                            LIMIT 1""").fetchone()
            np.testing.assert_array_equal(decode_mask_png(t[1]),land)
            decoded=decode_terrain_rgb(t[0])
            np.testing.assert_allclose(decoded[land],heights[land],atol=0.051)
            self.assertTrue((decoded[~land]==0).all())

    def test_bad_mask_file_cannot_leave_publishable_merged_mbtiles(self):
        from consolidated_terrain_pipeline import sha256_file
        plan=self.make_plan()
        png=io.BytesIO()
        Image.fromarray(np.full((256,256,3),127,dtype=np.uint8)).save(png,format="PNG")
        mask_png=io.BytesIO()
        Image.fromarray(np.full((256,256),255,dtype=np.uint8),mode="L").save(mask_png,format="PNG")
        self.results.mkdir()
        for index,chunk in enumerate(plan["chunks"]):
            path=self.results/f"chunk-{chunk['id']}.mbtiles"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY, value TEXT)")
                db.execute("INSERT INTO metadata VALUES('format','png')")
                db.execute("INSERT INTO metadata VALUES('coast_render_mode',?)",
                           ("surface_zero_visual_only_osm_landmask_v1",))
                db.execute("""CREATE TABLE tiles(
                    zoom_level INTEGER,tile_column INTEGER,tile_row INTEGER,tile_data BLOB,
                    PRIMARY KEY(zoom_level,tile_column,tile_row))""")
                db.execute("""CREATE TABLE osm_land_mask(
                    zoom_level INTEGER,tile_column INTEGER,tile_row INTEGER,mask_png BLOB,
                    PRIMARY KEY(zoom_level,tile_column,tile_row))""")
                for line in (self.plan_dir/chunk["filename"]).read_text().splitlines():
                    tile=json.loads(line)
                    z,x,y=tile["z"],tile["x"],tile["tms_y"]
                    db.execute("INSERT INTO tiles VALUES(?,?,?,?)",(z,x,y,png.getvalue()))
                    db.execute("INSERT INTO osm_land_mask VALUES(?,?,?,?)",
                               (z,x,y,b"NOT_PNG" if index==0 else mask_png.getvalue()))
            report={
                "schema":"colombia-osm-land-only-chunk-v1",
                "chunk_id":chunk["id"],"chunk_sha256":chunk["sha256"],
                "source_manifest_sha256":plan["source_manifest_sha256"],
                "national_release_authorized":False,"blocked_coastal_tiles":[],
                "status":"SUCCESS_render_only_coast",
                "coast_render_mode":"surface_zero_visual_only_osm_landmask_v1",
                "full_land_tiles_written":0,
                "mixed_coast_tiles_written":chunk["tiles"],
                "skipped_all_offland":0,
                "mbtiles_file":path.name,"mbtiles_sha256":sha256_file(path)}
            (self.results/f"chunk-{chunk['id']}.report.json").write_text(json.dumps(report))
        out=self.root/"must-not-exist.mbtiles"
        with self.assertRaises((AssertionError,ValueError,OSError)):
            merge_verified_chunks(self.plan_dir,self.results,out)
        self.assertFalse(out.exists())
        self.assertFalse(out.with_name(out.name+".incomplete").exists())


if __name__ == "__main__":
    unittest.main()
