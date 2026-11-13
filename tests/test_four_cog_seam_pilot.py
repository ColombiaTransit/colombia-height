import sys
import unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from four_cog_seam_pilot import BATCHES, BASE_Z, X_RANGE,Y_RANGE,JUNCTION, owner,tiles_for,adjacent_pairs,base_bbox,source_stats

class FourCogTests(unittest.TestCase):
    def test_unique_quad_ownership(self):
        for z in (10,11,12):
            tiles=[t for xs,ys in BATCHES.values() for t in tiles_for(xs,ys,z)]
            self.assertEqual(len(tiles),20*(4**(z-10)))
            self.assertEqual(len(tiles),len(set(tiles)))
            self.assertTrue(all(owner(*t) in BATCHES for t in tiles))
    def test_junction_inside_region(self):
        b=base_bbox(X_RANGE,Y_RANGE)
        self.assertTrue(b[0]<JUNCTION[0]<b[2])
        self.assertTrue(b[1]<JUNCTION[1]<b[3])
    def test_two_orthogonal_batch_seams(self):
        for z in (10,11):
            checks=list(adjacent_pairs(z))
            directions={v[0] for v in checks}
            self.assertEqual(directions,{"west_east","north_south"})
            self.assertEqual(len(checks),9*(1<<(z-10)))
    def test_both_source_gradient_directions(self):
        raster=np.array([[0.,50.,60.],[80.,130.,140.]],dtype=np.float32)
        owner_mask=np.array([[1,2,2],[3,4,4]],dtype=np.uint8)
        stat=source_stats(raster,owner_mask)
        self.assertEqual(stat["east_west_source_pixel_pairs"],2)
        self.assertEqual(stat["north_south_source_pixel_pairs"],3)
        self.assertEqual(stat["max_north_south_source_gradient_m"],80.0)

if __name__=="__main__":
    unittest.main()
