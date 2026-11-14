"""Immutable native gap totals and conservative OSM Colombia country attribution."""
import sys
import unittest
from pathlib import Path

from shapely.geometry import box

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from osm_only_remaining_997 import recover_old_140_case_register
from osm_only_colombia_land_finish import tile_osm_context
from official_territory_screen import xyz_geometry


class OSMColombia997Tests(unittest.TestCase):
    def test_country_relation_disjoint_is_out_of_scope_without_ocean_label(self):
        tile=(13,2465,3844)
        b=xyz_geometry(*tile).bounds
        elsewhere=box(b[0]+1,b[1]+1,b[2]+2,b[3]+2)
        d=tile_osm_context(tile,elsewhere,[],[],[])
        self.assertEqual(d["OSM_COL_country_relation_tile_context"],"disjoint_OSM_Colombia_relation")
        self.assertTrue(d["no_coastline_or_named_island_in_tile_does_NOT_certify_ocean"])

    def test_missing_original_1005_140_evidence_never_silently_succeeds(self):
        with self.assertRaises(AssertionError):
            recover_old_140_case_register({"total":1005,"tiles":[]},
                                          {"new_staging_COG_count":140,
                                           "prior_139_national_coverage_run":43605294875,
                                           "national_Terrain_RGB_publication_allowed":False,
                                           "recomputed_z13_per_tile":[]})


if __name__=="__main__":
    unittest.main()
