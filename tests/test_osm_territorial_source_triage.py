"""No-network regression tests for advisory territorial source triage."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

from shapely.geometry import Point,box
import requests

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from osm_territorial_source_triage import (
    GEOBOUNDARIES, MAX_ISLAND_PROXIMITY_DEG, approximate_island_neighbors,
    classify_tile, foreign_cell_context, get_border_geometries, rank_source,
)


def candidate(name, osm, igac, total):
    return {
        "name": name,
        "osm_land_missing_pixel_cell_hits": osm,
        "osm_land_and_igac_missing_pixel_cell_hits": igac,
        "native_missing_pixel_cell_hits": total,
        "z13_tiles_with_missing_pixel_in_this_cog_degree_cell": 7,
    }


def prior():
    return {"native_z13_pixel_recovery":{
        "tumaco":{"source":"Copernicus_DSM_COG_10_N01_00_W080_00_DEM",
                  "real_native_dem_pixels_recovered":460333,
                  "recovered_inside_igac_departments":6602},
        "malpelo":{"source":"Copernicus_DSM_COG_10_N03_00_W082_00_DEM",
                   "real_native_dem_pixels_recovered":145625,
                   "recovered_inside_igac_departments":0}}}


class OSMTerritorialTriageTests(unittest.TestCase):
    def test_tumaco_native_and_igac_positive_but_not_source_approval(self):
        c=candidate("Copernicus_DSM_COG_10_N01_00_W080_00_DEM",
                    130336,5865,460333)
        result=rank_source(c,prior(),[],{"ECU":box(-81,-1,-79,1)})
        self.assertTrue(result["review_tier"].startswith("1_"))
        self.assertEqual(result["prior_native_recovery"]["native_z13_recovered_pixels"],460333)
        self.assertFalse(result["source_approved_for_manifest"])
        self.assertFalse(result["territorial_land_authorized"])

    def test_malpelo_source_south_of_island_is_still_found_nearby(self):
        c=candidate("Copernicus_DSM_COG_10_N03_00_W082_00_DEM",354,0,145650)
        probes=[{"id":"malpelo","lon":-81.606,"lat":4.005}]
        result=rank_source(c,prior(),probes,{})
        self.assertTrue(result["review_tier"].startswith("2_"))
        self.assertEqual(result["island_probe_ids_within_0p06_degrees_context_only"],["malpelo"])
        self.assertEqual(result["prior_native_recovery"]["native_z13_recovered_pixels"],145625)
        self.assertFalse(result["source_approved_for_manifest"])

    def test_foreign_dominant_cell_remains_review_not_automatic_exclusion(self):
        c=candidate("Copernicus_DSM_COG_10_N07_00_W070_00_DEM",1000,0,1000)
        region=box(-70,7,-69,8)
        r=rank_source(c,prior(),[],{"VEN":region})
        self.assertTrue(r["review_tier"].startswith("5_"))
        self.assertAlmostEqual(r["foreign_ADM0_degree_cell_overlap_CONTEXT_NOT_pixel_allocation"]["VEN"],1)
        self.assertFalse(r["source_approved_for_manifest"])
        self.assertTrue(r["foreign_reference_contact_is_not_proof_of_foreign_pixel"])

    def test_no_igac_is_not_transformed_to_zero(self):
        c=candidate("Copernicus_DSM_COG_10_N07_00_W070_00_DEM",1000,None,1000)
        with self.assertRaisesRegex(AssertionError,"IGAC"):
            rank_source(c,prior(),[],{})

    def test_island_point_proximity_is_not_cog_land_ownership(self):
        cell=box(-82,3,-81,4)
        probes=[{"id":"malpelo","lon":-81.606,"lat":4.005},
                {"id":"quitasueno","lon":-81.1,"lat":13.7}]
        self.assertEqual(approximate_island_neighbors(cell,probes),["malpelo"])
        self.assertEqual(approximate_island_neighbors(cell,probes,.001),[])

    def test_tile_unknown_remains_unknown_and_no_country_allocation(self):
        tile={"z":13,"x":2280,"y":4000,"missing_inside_osm_land":0,
              "missing_osm_land_and_igac_department":0,"native_missing_dem_pixels":65536,
              "per_candidate_omitted_cog":{}}
        out=classify_tile(tile,[],{})
        self.assertEqual(out["tier"],"6_no_OSM_missing_land_pixels_other_NoData_unknown")
        self.assertFalse(out["automatic_country_attribution"])

    def test_foreign_outline_unavailable_is_not_empty_geographical_truth(self):
        class Session:
            def get(self,url,**kwargs):
                raise requests.ConnectionError("unavailable")
        foreign,meta,errors=get_border_geometries(Session(),("ECU",))
        # request.ConnectionError expected as requests exception, not builtin.
        self.assertEqual(foreign,{})
        self.assertEqual(meta,{})
        self.assertIn("ECU",errors)

    def test_foreign_degree_area_only_not_pixel_count(self):
        c=box(-80,1,-79,2)
        r=foreign_cell_context(c,{"ECU":box(-79.7,1,-79,2)})
        self.assertAlmostEqual(r["ECU"],.7)


if __name__=="__main__":
    unittest.main()
