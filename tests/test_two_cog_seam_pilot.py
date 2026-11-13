import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from two_cog_seam_pilot import (
    BASE_Z,BASE_Y,BATCH_BASE_X,base_bounds,tiles_for,
    boundary_pairs,warp_sources,source_boundary_stats
)

class TwoCogSeamTests(unittest.TestCase):
    def test_unique_tile_ownership(self):
        for z in (11,12,13):
            w=set(tiles_for(BATCH_BASE_X["west"],BASE_Y,z))
            e=set(tiles_for(BATCH_BASE_X["east"],BASE_Y,z))
            self.assertFalse(w&e)
            self.assertEqual(len(w|e),8*(4**(z-11)))
            self.assertEqual(len(list(boundary_pairs(z))),2*(1<<(z-11)))
    def test_country_degree_boundary_inside_sample(self):
        all_x=tuple(x for xs in BATCH_BASE_X.values() for x in xs)
        bbox=base_bounds(all_x)
        self.assertLess(bbox[0],-75)
        self.assertGreater(bbox[2],-75)
    def test_combining_adjacent_native_cogs_preserves_zero_and_nodata(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p=[]
            for j,lon in enumerate((-76,-75)):
                path=root/f"part{j}.tif"
                values=np.full((32,32),100.+j*10,dtype=np.float32)
                if j==0:
                    values[:,:]=0.0 # A genuine zero-valued source is valid.
                with rasterio.open(path,"w",driver="GTiff",
                     height=32,width=32,count=1,dtype="float32",
                     crs="EPSG:4326",transform=from_origin(lon,7,1/32,1/32),
                     nodata=-32767.0) as ds:
                    ds.write(values,1)
                p.append(path)
            with rasterio.open(p[0]) as west,rasterio.open(p[1]) as east:
                # Use z8 tile which spans both degree cells (not guaranteed
                # to be wholly covered by sources); inspect only valid pts.
                found=False
                for x in range(72,76):
                    tile=(8,x,123)
                    val,owners,_,_=warp_sources([west,east],tile)
                    if np.any(owners==1) and np.any(owners==2):
                        found=True
                        self.assertTrue(np.all(np.isfinite(val[owners>0])))
                        self.assertTrue(np.any(val[owners==1]==0))
                        self.assertTrue(np.all(val[owners==2]>=100))
                self.assertTrue(found,"Synthetic test must straddle both native COGs")
    def test_source_boundary_gradient_is_descriptive(self):
        a=np.array([[0,100,110],[0,100,110]],dtype=np.float32)
        owner=np.array([[1,2,2],[1,2,2]],dtype=np.uint8)
        m=source_boundary_stats(a,owner)
        self.assertEqual(m["cross_source_adjacent_pixel_pairs"],2)
        self.assertEqual(m["max_adjacent_height_difference_m"],100.)

if __name__=="__main__":
    unittest.main()
