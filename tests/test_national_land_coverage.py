"""No-network regression checks for conservative national land-reference audit."""
import gzip
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import mercantile
import numpy as np
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from national_land_coverage import (
    CATEGORIES, SITES, References, catalog_candidates,
    missing_categories, reconcile, scan, site_tiles,
)


class NationalLandCoverageTests(unittest.TestCase):
    def test_exact_four_pilot_neighborhoods_and_known_tumaco_gap(self):
        cases = site_tiles()
        self.assertEqual(len(cases), 36)
        self.assertEqual(Counter(s for s, _ in cases), Counter({s: 9 for s in SITES}))
        self.assertIn(("tumaco", (11, 574, 1012)), cases)
        self.assertEqual(len(set(t for _, t in cases)), 36)
        with self.assertRaises(ValueError):
            site_tiles(10)

    def test_missing_pixels_four_disjoint_non_water_categories(self):
        valid = np.ones((256, 256), dtype=bool)
        valid[0, :4] = False
        gb = np.zeros_like(valid)
        ne = np.zeros_like(valid)
        gb[0, 0:2] = True
        ne[0, 0] = True
        ne[0, 2] = True
        c = missing_categories(valid, gb, ne)
        self.assertEqual([c[k] for k in CATEGORIES], [1, 1, 1, 1])
        self.assertEqual(sum(c[k] for k in CATEGORIES), 4)
        self.assertNotIn("ocean", c)
        with self.assertRaises(ValueError):
            missing_categories(valid, gb[:-1], ne)

    def test_no_missing_pixels_does_not_invent_water(self):
        valid = np.ones((256, 256), bool)
        gb = np.ones_like(valid)
        ne = np.zeros_like(valid)
        c = missing_categories(valid, gb, ne)
        self.assertEqual(sum(c[k] for k in CATEGORIES), 0)
        self.assertEqual(c["reference_geoboundaries_land_pixels"], 65536)

    def test_native_pixel_center_land_reference_masks(self):
        z = 11
        t = mercantile.tile(-78.76, 1.81, z)
        b = mercantile.bounds(t)
        left = box(b.west, b.south, (b.west + b.east) / 2, b.north)
        right = box((b.west + b.east) / 2, b.south, b.east, b.north)
        refs = References(left, [right], "https://example.test/boundary", "test")
        gb, ne, lon, lat = refs.masks((z, t.x, t.y))
        self.assertEqual(gb.shape, (256, 256))
        self.assertTrue(np.any(gb))
        self.assertTrue(np.any(ne))
        self.assertEqual(int((gb & ne).sum()), 0)
        self.assertEqual(lon.shape, lat.shape)

    def test_low_zoom_study_scope_excludes_unrelated_world_land(self):
        # A global z0 tile should not count e.g. European land as a
        # suspected missing Colombian height: the NE layer is clipped.
        colombia = box(-80.0, 0.0, -79.0, 1.0)
        europe = box(-1.0, 50.0, 1.0, 52.0)
        refs = References(colombia, [europe, colombia], "test", "test")
        self.assertEqual(len(refs.ne), 1)
        self.assertTrue(refs.ne[0].covers(colombia.representative_point()))

    def test_unselected_cog_detection_does_not_expand_manifest(self):
        missing = np.zeros((256, 256), bool)
        missing[0, 0] = True
        lon = np.full((256, 256), -79.2)
        lat = np.full((256, 256), 1.5)
        name = "Copernicus_DSM_COG_10_N01_00_W080_00_DEM"
        catalog = {(1, -80): {"name": name}}
        self.assertEqual(catalog_candidates(missing, lon, lat, catalog, set(), 11), [name])
        self.assertEqual(catalog_candidates(missing, lon, lat, catalog, {(1, -80)}, 11), [])
        self.assertEqual(catalog_candidates(missing, lon, lat, catalog, set(), 8), [])
        self.assertEqual(catalog_candidates(np.zeros_like(missing), lon, lat, catalog, set(), 11), [])

    def test_unmapped_missing_dem_pixels_still_require_review(self):
        # Missing DEM outside BOTH references is an unresolved policy case,
        # never silently accepted as ocean or an approved output tile.
        from unittest.mock import MagicMock
        from national_land_coverage import inspect
        valid = np.zeros((256, 256), dtype=bool)
        refs = MagicMock()
        refs.masks.return_value = (
            valid, valid, np.full(valid.shape, -79.2), np.full(valid.shape, 1.5))
        fake_result = {"coverage": "no_dem_coverage",
                       "valid_pixels": 0, "missing_pixels": 65536}
        with patch("national_land_coverage.assess_tile", return_value=(fake_result, [], 0)), \
             patch("national_land_coverage.intersecting_source_indices", return_value=[]):
            row, status = inspect([], {}, Path("."), refs, {}, set(), (11, 0, 0))
        self.assertEqual(status, "no_dem_coverage")
        self.assertTrue(row["requires_review"])
        self.assertTrue(row["outside_both_reference_status_unknown"])
        self.assertFalse(row["possible_missing_reference_land"])

    def test_reconcile_rejects_missing_shards(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(AssertionError, "32"):
                reconcile(d, Path(d) / "result.json")

    def test_pilot_report_is_never_publishable(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            manifest = root / "source.csv"
            manifest.write_text(
                "name,latitude,longitude,status,url\n" +
                "".join(f"cog_{i},1,-80,ok,https://example.test/{i}\n"
                        for i in range(137)), encoding="utf-8"
            )
            def fake_inspect(*args, **kwargs):
                tile = args[6]
                site = kwargs.get("site")
                return ({
                    "z": tile[0], "x": tile[1], "y": tile[2],
                    "tms_y": (1 << tile[0]) - 1 - tile[2],
                    "site": site, "dem_coverage": "full_dem_coverage",
                    "valid_dem_pixels": 65536, "missing_dem_pixels": 0,
                    "selected_source_cogs": [],
                    "reference_geoboundaries_land_pixels": 1,
                    "reference_natural_earth_land_pixels": 1,
                    "reference_land_agreement_pixels": 1,
                    "unselected_public_cogs_at_missing_pixels": [],
                    "requires_review": False,
                    "possible_missing_reference_land": False,
                    "outside_both_reference_status_unknown": False,
                    **{k: 0 for k in CATEGORIES},
                }, "full_dem_coverage")
            with patch("national_land_coverage.load_references") as refs, \
                 patch("national_land_coverage.index_sources", return_value={}), \
                 patch("national_land_coverage.inspect", side_effect=fake_inspect):
                refs.return_value.url = "https://example.test/boundary"
                refs.return_value.license = "test"
                result = scan(manifest, root / "output", "pilot")
            self.assertEqual(result["tiles_checked"], 36)
            self.assertEqual(result["dem_coverage_counts"]["full_dem_coverage"], 36)
            self.assertFalse(result["national_publication_allowed"])
            self.assertFalse(result["all_missing_pixels_classified_as_water"])
            with gzip.open(root / "output" / "land-pilot-tiles.ndjson.gz", "rt") as stream:
                self.assertEqual(sum(1 for _ in stream), 36)


if __name__ == "__main__":
    unittest.main()
