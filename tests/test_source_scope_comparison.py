"""No-network tests for comparing omitted native Copernicus sources."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from source_scope_comparison import (
    TARGET_COGS, SIZE, compare_arrays, plan_candidates,
)


class SourceScopeComparisonTests(unittest.TestCase):
    def test_catalog_candidates_are_ephemeral_not_in_selected_manifest(self):
        original = [{"name": f"selected_{i}"} for i in range(137)]
        catalog = {(i, i): {"name": n, "longitude": -80 + i,
                             "latitude": i + 1, "url": f"https://example.test/{i}"}
                   for i, n in enumerate(TARGET_COGS.values())}
        expanded = plan_candidates(original, catalog)
        self.assertEqual(len(original), 137)
        self.assertEqual(len(expanded), 139)
        self.assertEqual([x["name"] for x in original[:2]], ["selected_0", "selected_1"])
        self.assertEqual([x["name"] for x in expanded[137:]], list(TARGET_COGS.values()))
        self.assertTrue(all("investigation_only" in x["status"] for x in expanded[137:]))
        with self.assertRaisesRegex(AssertionError, "Already selected"):
            plan_candidates(original[:-1] + [{"name": list(TARGET_COGS.values())[0]}], catalog)

    def test_missing_land_and_unknown_recovery_are_separate(self):
        before = np.zeros(SIZE, bool)
        before[5, 5] = True
        after = before.copy()
        after[10, 10:14] = True
        old_heights = np.full(SIZE, -9999., np.float32)
        old_heights[5, 5] = 19.5
        new_heights = old_heights.copy()
        new_heights[10, 10:14] = [4, 8, 12, 16]
        gb = np.zeros(SIZE, bool)
        ne = np.zeros(SIZE, bool)
        gb[10, 10:12] = True
        ne[10, 10] = True
        ne[10, 12] = True
        report = compare_arrays(before, old_heights, after, new_heights, gb, ne)
        self.assertEqual(report["recovered_dem_pixels"], 4)
        self.assertEqual(report["recovered_reference_land_pixels"], 3)
        self.assertEqual(report["recovered_outside_both_references_unknown"], 1)
        self.assertEqual(report["recovered_pixel_reference_categories"], {
            "missing_both_land_references": 1,
            "missing_geoboundaries_only": 1,
            "missing_natural_earth_only": 1,
            "missing_outside_both_references": 1,
        })
        self.assertEqual(report["max_original_valid_height_difference_m"], 0)
        self.assertTrue(report["no_artificial_dem_pixels"])

    def test_adding_source_must_preserve_all_original_valid_dem_values(self):
        before = np.zeros(SIZE, bool)
        before[1, 2] = True
        height = np.full(SIZE, -9999., np.float32)
        height[1, 2] = 51.
        gb = np.zeros(SIZE, bool)
        ne = np.zeros(SIZE, bool)
        changed = height.copy()
        changed[1, 2] = 52.1
        with self.assertRaisesRegex(AssertionError, "changed"):
            compare_arrays(before, height, before.copy(), changed, gb, ne)
        lost = before.copy()
        lost[1, 2] = False
        with self.assertRaisesRegex(AssertionError, "removed earlier valid"):
            compare_arrays(before, height, lost, height, gb, ne)

    def test_same_validity_no_artificial_sea(self):
        before = np.zeros(SIZE, bool)
        gb = np.zeros(SIZE, bool)
        ne = np.zeros(SIZE, bool)
        heights = np.full(SIZE, -9999., np.float32)
        report = compare_arrays(before, heights, before.copy(), heights.copy(), gb, ne)
        self.assertEqual(report["recovered_dem_pixels"], 0)
        self.assertEqual(report["remaining_missing_outside_both_references_unknown"], 65536)
        self.assertFalse(report["recovered_reference_land_pixels"])


if __name__ == "__main__":
    unittest.main()
