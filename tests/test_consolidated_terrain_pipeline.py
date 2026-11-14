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
        with self.assertRaises(ValueError):
            create_plan(self.manifest, self.root / "lowzoom", minzoom=0)

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
        with self.assertRaises(RuntimeError):
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


if __name__ == "__main__":
    unittest.main()
