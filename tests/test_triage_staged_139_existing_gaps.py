"""Tiny offline tests: never rerun national DEM/OSM for residual country triage."""
import sys
import unittest
from pathlib import Path
from shapely.geometry import box

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from triage_staged_139_existing_gaps import categorize_whole_tile


class Staged139NoRerunCountryTests(unittest.TestCase):
    def test_full_foreign_tile_only_a_reference(self):
        from official_territory_screen import xyz_geometry
        tile=(13,2503,3913)
        b=xyz_geometry(*tile)
        foreign={"BRA":box(b.bounds[0]-.1,b.bounds[1]-.1,b.bounds[2]+.1,b.bounds[3]+.1)}
        r=categorize_whole_tile(tile,foreign,None)
        self.assertEqual(r["full_tile_reference_ISO_codes"],["BRA"])
        self.assertFalse(r["proof_of_legal_colombian_land"])

    def test_partial_foreign_intersection_cannot_assign_pixels(self):
        from official_territory_screen import xyz_geometry
        tile=(13,2503,3913)
        b=xyz_geometry(*tile)
        mid=(b.bounds[0]+b.bounds[2])/2
        foreign={"BRA":box(b.bounds[0]-.1,b.bounds[1]-.1,mid,b.bounds[3]+.1)}
        r=categorize_whole_tile(tile,foreign,None)
        self.assertEqual(r["reference_group"],"partial_country_or_border_reference_NO_pixel_country_assignment")
        self.assertEqual(r["full_tile_reference_ISO_codes"],[])
        self.assertEqual(r["country_contact_codes"],["BRA"])

    def test_no_geoBoundaries_is_unknown_not_sea(self):
        r=categorize_whole_tile((13,2230,4005),{},None)
        self.assertEqual(r["reference_group"],"no_country_ADM0_land_reference_contact_UNRESOLVED")
        self.assertFalse(r["proof_of_legal_colombian_land"])

    def test_full_colombia_only_provisional_reference(self):
        from official_territory_screen import xyz_geometry
        tile=(13,2503,3913)
        bounds=xyz_geometry(*tile).bounds
        col=box(bounds[0]-.1,bounds[1]-.1,bounds[2]+.1,bounds[3]+.1)
        r=categorize_whole_tile(tile,{},col)
        self.assertEqual(r["full_tile_reference_ISO_codes"],["COL"])
        self.assertFalse(r["proof_of_legal_colombian_land"])

    def test_conflicting_full_country_masks_not_authoritative(self):
        from official_territory_screen import xyz_geometry
        tile=(13,2503,3913)
        bounds=xyz_geometry(*tile).bounds
        shared=box(bounds[0]-.1,bounds[1]-.1,bounds[2]+.1,bounds[3]+.1)
        r=categorize_whole_tile(tile,{"BRA":shared},shared)
        self.assertEqual(r["reference_group"],"conflicting_full_tile_country_geometries_UNRESOLVED")
        self.assertFalse(r["proof_of_legal_colombian_land"])


if __name__=="__main__":
    unittest.main()
