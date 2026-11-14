"""Island geometry must be real OSM polygons, never a probe radius."""
import sys
import unittest
from pathlib import Path
import numpy as np
from shapely.geometry import box
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from island_osm_native_scope import choose_island_polygons,count_island_pixel_gaps,ISLAND_IDS

class IslandScopeTests(unittest.TestCase):
    def test_probe_point_is_not_buffered_land(self):
        probes=[{"id":k,"lon":1.0,"lat":1.0} for k in ISLAND_IDS]
        found=choose_island_polygons([box(2,2,3,3)],probes)
        self.assertTrue(all(r["geometry"] is None for r in found.values()))
        self.assertTrue(all(r["status"]=="probe_not_in_osm_land_polygon" for r in found.values()))

    def test_mainland_polygon_rejected(self):
        probes=[{"id":k,"lon":1.0,"lat":1.0} for k in ISLAND_IDS]
        found=choose_island_polygons([box(0,0,2,2)],probes)
        self.assertTrue(all(r["geometry"] is None for r in found.values()))

    def test_exact_pixel_membership_and_cog_cell(self):
        lon=np.full((256,256),-78.5)
        lat=np.full((256,256),3.5)
        missing=np.zeros((256,256),dtype=bool)
        missing[:2,:3]=True
        cog="Copernicus_DSM_COG_10_N03_00_W079_00_DEM"
        count,gaps,by=count_island_pixel_gaps(missing,lon,lat,box(-79,3,-78,4),[cog])
        self.assertEqual(count,65536)
        self.assertEqual(gaps,6)
        self.assertEqual(by[cog],6)

    def test_empty_mask_is_not_invented_land(self):
        lon=np.full((256,256),-78.5)
        lat=np.full((256,256),3.5)
        count,gaps,_=count_island_pixel_gaps(np.ones((256,256),bool),lon,lat,box(-79,2,-78,3),[])
        self.assertEqual((count,gaps),(0,0))

if __name__=="__main__":
    unittest.main()
