"""Only-new 140 Tumaco geographic reference screening; no reprocessing."""
import sys
import unittest
from pathlib import Path
from shapely.geometry import box

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from triage_only_new_tumaco140_geography import classify_whole_tile,build
from official_territory_screen import xyz_geometry


class OnlyNewTumaco140GeoTests(unittest.TestCase):
    def setUp(self):
        self.tile=(13,2275,4050)
        self.b=xyz_geometry(*self.tile).bounds

    def test_reference_full_country_is_not_legal_land_or_pixel_proof(self):
        b=self.b
        shapes={"COL":box(b[0]-.1,b[1]-.1,b[2]+.1,b[3]+.1)}
        item=classify_whole_tile(self.tile,shapes)
        self.assertEqual(item["whole_tile_ADM0_reference_ISO_codes"],["COL"])
        self.assertFalse(item["actual_pixel_land_membership_verified"])
        self.assertFalse(item["actual_pixel_country_membership_verified"])

    def test_partial_contact_not_counted_as_country_pixels(self):
        b=self.b
        mid=(b[0]+b[2])/2
        shapes={"ECU":box(b[0]-.1,b[1]-.1,mid,b[3]+.1)}
        item=classify_whole_tile(self.tile,shapes)
        self.assertEqual(item["status"],"partial_country_reference_NO_pixel_attribution")
        self.assertEqual(item["whole_tile_ADM0_reference_ISO_codes"],[])
        self.assertEqual(item["intersecting_ADM0_reference_ISO_codes"],["ECU"])

    def test_no_country_reference_is_not_ocean(self):
        item=classify_whole_tile(self.tile,{})
        self.assertEqual(item["status"],"no_adm0_contact_UNRESOLVED_NOT_verified_ocean")
        self.assertTrue(item["not_verified_ocean"])

    def test_conflicting_refs_are_not_certified_colombia(self):
        b=self.b
        g=box(b[0]-.1,b[1]-.1,b[2]+.1,b[3]+.1)
        item=classify_whole_tile(self.tile,{"COL":g,"ECU":g})
        self.assertEqual(item["status"],"overlapping_full_country_references_UNRESOLVED")
        self.assertFalse(item["actual_pixel_country_membership_verified"])

    def test_build_without_both_expected_ADM0_refs_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError,"Both independent"):
            build({}, {}, {"COL":box(*self.b)}, {}, {"ECU":"offline"})


if __name__=="__main__":
    unittest.main()
