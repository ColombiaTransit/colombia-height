"""Offline tests for evidence-only IGAC departmental screening of DEM gaps."""
import math
import sys
import tempfile
import unittest
from pathlib import Path

from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from official_territory_screen import (
    BASELINE_Z13_NATURAL_EARTH_LAND_GAP, cell_geometry, load_incomplete_rows,
    positive_polygon_overlap, screen, xyz_geometry,
)


def z13_tile(lon, lat):
    n = 2**13
    x = math.floor((lon + 180) / 360 * n)
    y = math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return (13, x, y)


def mockrow(tile, cog, natural_earth_land_gap=8):
    z, x, y = tile
    return {"z":z,"x":x,"y":y,
            "unselected_public_cogs_at_missing_pixels":[cog],
            "missing_natural_earth_only":natural_earth_land_gap}


class OfficialScopeTests(unittest.TestCase):
    def test_source_names_are_exact_one_degree_cells(self):
        self.assertEqual(cell_geometry("Copernicus_DSM_COG_10_N01_00_W080_00_DEM").bounds, (-80,1,-79,2))
        self.assertEqual(cell_geometry("Copernicus_DSM_COG_10_N03_00_W082_00_DEM").bounds, (-82,3,-81,4))
        self.assertEqual(cell_geometry("Copernicus_DSM_COG_10_S04_00_W072_00_DEM").bounds, (-72,-4,-71,-3))
        with self.assertRaises(ValueError):
            cell_geometry("invalid_source")

    def test_xyz_bounds_and_study_coverage(self):
        tile = z13_tile(-74.1,4.7)
        self.assertTrue(xyz_geometry(*tile).covers(box(-74.1,4.7,-74.1,4.7)))
        with self.assertRaises(ValueError):
            xyz_geometry(13,-1,5)

    def test_touching_border_is_not_area_overlap(self):
        a=box(-75,4,-74,5)
        b=box(-74,4,-73,5)
        self.assertTrue(a.touches(b))
        self.assertFalse(positive_polygon_overlap(a,b))
        self.assertTrue(positive_polygon_overlap(a,box(-74.5,4.2,-73.9,4.8)))

    def test_candidate_tiers_not_source_approval(self):
        a = "Copernicus_DSM_COG_10_N04_00_W075_00_DEM"
        outside = "Copernicus_DSM_COG_10_N01_00_W080_00_DEM"
        tile_inside=z13_tile(-74.12,4.71)
        tile_outside=z13_tile(-79.5,1.5)
        z13=[mockrow(tile_inside,a,14),mockrow(tile_outside,outside,9)]
        polygons=[box(-74.3,4.5,-74.0,5.0)]
        ranks, counts=screen(z13,z13,[a,outside],polygons,["Bogota region synthetic"])
        self.assertEqual(ranks[a]["screening_tier"],"A_IGAC_land_and_candidate_cell_overlap_needs_native_DEM_QA")
        self.assertEqual(ranks[a]["z13_tiles_with_igac_and_candidate_cell_contact"],1)
        self.assertEqual(ranks[outside]["screening_tier"],"C_no_IGAC_department_polygon_overlap_islands_or_neighbors_need_review")
        self.assertEqual(counts["suspect_z13_tiles_without_igac_polygon_contact"],1)
        self.assertTrue(ranks[a]["approval_status"].startswith("NOT_APPROVED"))

    def test_no_missing_artifacts_may_be_counted_as_empty_dataset(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(AssertionError, "32 prior land study artifacts"):
                load_incomplete_rows(Path(d))


if __name__ == "__main__":
    unittest.main()
