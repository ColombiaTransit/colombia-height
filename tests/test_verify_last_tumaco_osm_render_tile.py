"""Target OSM physical-land negative check must reject non-ocean map pixels."""
import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from verify_last_tumaco_osm_render_tile import (
    TARGET,REFERENCE,check_against_existing_osm_coast_evidence,
)


class LastOffshoreOSMRenderTests(unittest.TestCase):
    def original(self):
        return {
            "country_relation":{"osm_relation":120027},
            "national_release_approved":False,
            "new_140_only_68_tiles":[
                {"zxy":list(TARGET),"old_140_native_missing_pixels":31232,
                 "OSM_COL_country_relation_tile_context":"partial_OSM_Colombia_relation_tile",
                 "OSM_direct_coastline_way_ids_in_tile":[],
                 "OSM_closed_CCW_coastline_land_poly_hits":0,
                 "OSM_named_island_area_hint_hits":0}
            ] + [{"zxy":[13,i,4050]} for i in range(67)]
        }

    def map_result(self,colour=(170,211,223)):
        return {
            "all_pixels_identical":True,
            "ocean_candidate_colour_RGB":list(colour),
            "pixel_rgb":np.tile(np.array(colour,dtype=np.uint8),(256,256,1))
        }

    def test_uniform_ocean_map_with_zero_shoreline_hits_is_only_render_level_evidence(self):
        report=check_against_existing_osm_coast_evidence(
            self.original(),self.map_result(),self.map_result())
        self.assertEqual(report["OSM_standard_target_pixels_matching_offshore_reference_colour"],65536)
        self.assertTrue(report["render_level_offshore_exception_resolved"])
        self.assertTrue(report["OSM_standard_render_is_not_certified_vector_pixel_land_mask"])
        self.assertEqual(report["native_DEM_values_recomputed"],0)

    def test_non_ocean_pixel_prevents_automatic_closure(self):
        target=self.map_result()
        target["pixel_rgb"][100,100]=(1,2,3)
        r=check_against_existing_osm_coast_evidence(
            self.original(),target,self.map_result())
        self.assertEqual(r["OSM_standard_target_pixels_not_matching_offshore_reference_colour"],1)
        self.assertFalse(r["render_level_offshore_exception_resolved"])

    def test_no_coastline_evidence_alone_is_insufficient_if_reference_is_not_ocean(self):
        ocean=self.map_result()
        ocean["all_pixels_identical"]=False
        with self.assertRaisesRegex(AssertionError,"Offshore control"):
            check_against_existing_osm_coast_evidence(
                self.original(),self.map_result(),ocean)

    def test_missing_original_source_metadata_fails_closed(self):
        original=self.original()
        original["new_140_only_68_tiles"][0]["OSM_closed_CCW_coastline_land_poly_hits"]=1
        with self.assertRaisesRegex(AssertionError,"inconsistent"):
            check_against_existing_osm_coast_evidence(
                original,self.map_result(),self.map_result())


if __name__=="__main__":
    unittest.main()
