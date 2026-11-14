"""No national rerun: Tumaco N01_W080 vs selected N01_W079 native COG seam."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from affine import Affine

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from tumaco_native_longitude_seam import sample_longitude_border, WEST, EAST, LONGITUDE_EDGE
from native_source_seam_audit import seam_metrics


class FakeRaster:
    crs=SimpleNamespace(to_epsg=lambda:4326)
    transform=Affine(1/3600,0,-80,0,-1/3600,2)
    nodata=-9999.
    def __init__(self,right=None,left=None,baseline=10.):
        self.bounds=SimpleNamespace(right=right,left=left)
        self.baseline=baseline
        self.last_lon_samples=[]
    def sample(self,coordinates,masked=True):
        for lon,lat in coordinates:
            self.last_lon_samples.append(lon)
            yield np.ma.array([self.baseline+float(lat)],mask=[False])


class TumacoLongitudeSourceTests(unittest.TestCase):
    def test_exact_reused_source_candidates(self):
        self.assertTrue(WEST.endswith("N01_00_W080_00_DEM"))
        self.assertTrue(EAST.endswith("N01_00_W079_00_DEM"))
        self.assertEqual(LONGITUDE_EDGE,-79.)

    def test_sample_exact_six_native_inward_columns(self):
        west=FakeRaster(right=-79.00013888888889,baseline=10.)
        east=FakeRaster(left=-79.00013888888889,baseline=11.)
        a,b,res=sample_longitude_border(west,east,np.linspace(1.1,1.9,350))
        self.assertEqual(a.shape,(6,350))
        self.assertEqual(b.shape,(6,350))
        self.assertAlmostEqual(res,1/3600)
        self.assertEqual(seam_metrics(a,b)["native_cross_border"]["count"],350)
        self.assertEqual(seam_metrics(a,b)["border_gt_40m_and_gt_3x_immediate_local_gradient"],0)
        self.assertTrue(all(lon<LONGITUDE_EDGE for lon in west.last_lon_samples))
        self.assertTrue(all(lon>LONGITUDE_EDGE-1/3600 for lon in east.last_lon_samples))

    def test_reject_native_edge_outside_79west(self):
        west=FakeRaster(right=-79.3,baseline=10.)
        east=FakeRaster(left=-79.0001,baseline=10.)
        with self.assertRaisesRegex(AssertionError,"far from"):
            sample_longitude_border(west,east,[1.5])


if __name__=="__main__":
    unittest.main()
