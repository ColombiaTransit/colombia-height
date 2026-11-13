"""No-network checks for target z13 IGAC native recovery diagnostic."""
import sys
import unittest
from pathlib import Path
import numpy as np
from shapely.geometry import box
from shapely.strtree import STRtree

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from official_native_z13 import SITES, relevant_tiles, igac_tile_mask
from official_territory_screen import xyz_geometry


class NativeZ13OfficialTests(unittest.TestCase):
    def test_known_sites_are_both_kept_even_if_official_igac_omits_island(self):
        self.assertIn("malpelo",SITES)
        self.assertIn("tumaco",SITES)

    def test_exact_catalog_hints_and_distinct_ownership(self):
        records=[
            {"z":13,"x":1,"y":2,"unselected_public_cogs_at_missing_pixels":[SITES["tumaco"]]},
            {"z":13,"x":3,"y":4,"unselected_public_cogs_at_missing_pixels":[SITES["malpelo"]]},
            {"z":11,"x":3,"y":4,"unselected_public_cogs_at_missing_pixels":[SITES["malpelo"]]},
        ]
        result=relevant_tiles(records)
        self.assertEqual(result,{"tumaco":[(13,1,2)],"malpelo":[(13,3,4)]})
        records.append({"z":13,"x":1,"y":2,"unselected_public_cogs_at_missing_pixels":[SITES["malpelo"]]})
        with self.assertRaisesRegex(AssertionError,"Ambiguous source ownership"):
            relevant_tiles(records)

    def test_pixel_inside_igac_only_when_departments_cover_it(self):
        tile=(13,2341,3969)
        t=xyz_geometry(*tile)
        west,south,east,north=t.bounds
        lon=np.full((256,256),(west+east)/2)
        lat=np.full((256,256),(south+north)/2)
        g=box(west,south,east,north)
        result=igac_tile_mask(STRtree([g]),[g],tile,lon,lat)
        self.assertEqual(result.shape,(256,256))
        self.assertTrue(result.all())
        away=box(west+10,south,east+10,north)
        missed=igac_tile_mask(STRtree([away]),[away],tile,lon,lat)
        self.assertFalse(missed.any())


if __name__=="__main__":
    unittest.main()
