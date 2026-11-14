"""Offline fail-closed OSM land reference tests."""
import sys
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import box

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from osm_land_validation import partition, mask_osm, CATS


class OSMLandValidationTests(unittest.TestCase):
    def test_disjoint_missing_native_pixel_categories(self):
        valid=np.ones((256,256),bool)
        valid[10,10:14]=False
        osm=np.zeros_like(valid)
        gb=np.zeros_like(valid)
        osm[10,10:12]=True
        gb[10,10]=True
        gb[10,12]=True
        result=partition(valid,osm,gb)
        self.assertEqual([result[k] for k in CATS],[1,1,1,1])
        self.assertEqual(sum(result.values()),4)

    def test_unknown_not_equivalent_to_ocean(self):
        valid=np.zeros((256,256),bool)
        land=np.zeros_like(valid)
        gb=np.zeros_like(valid)
        result=partition(valid,land,gb)
        self.assertEqual(result[CATS[3]],65536)
        self.assertEqual(result[CATS[0]],0)

    def test_osm_geometry_rasterizes_as_pixel_centers(self):
        # Web Mercator zoom 11 tile at Tumaco; bbox of tile itself is land
        # in this synthetic test; geometry is NOT assumed Colombian.
        import mercantile
        t=mercantile.tile(-78.76,1.81,11)
        b=mercantile.bounds(t)
        full=mask_osm([box(b.west-.01,b.south-.01,b.east+.01,b.north+.01)],
                      (11,t.x,t.y))
        self.assertTrue(full.all())
        empty=mask_osm([], (11,t.x,t.y))
        self.assertFalse(empty.any())

    def test_wrong_shapes_fail_closed(self):
        with self.assertRaises(ValueError):
            partition(np.zeros((255,256),bool),
                      np.zeros((256,256),bool),np.zeros((256,256),bool))


if __name__=="__main__":
    unittest.main()
