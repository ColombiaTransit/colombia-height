import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from dem_quality_gates import gradients

class DemQualityGateTests(unittest.TestCase):
    def test_cross_source_gradient_is_not_conflated_with_interior_slope(self):
        height=np.array([[0.,200.,210.],[2.,202.,212.]],dtype=np.float32)
        source=np.array([[1,2,2],[1,2,2]],dtype=np.uint8)
        result=gradients(height,source)
        self.assertEqual(result["horizontal"]["cross_source_pairs"],2)
        self.assertEqual(result["horizontal"]["high_gradient_cross_pairs_over_100m"],2)
        self.assertEqual(result["vertical"]["cross_source_pairs"],0)
        self.assertEqual(result["horizontal"]["same_source_pairs"],2)
        self.assertEqual(result["horizontal"]["same_source_p99_m"],10.0)
    def test_nodata_excluded_by_provenance(self):
        h=np.array([[0.,-9999.,1.]],dtype=np.float32)
        p=np.array([[1,0,2]],dtype=np.uint8)
        m=gradients(h,p)
        self.assertEqual(m["horizontal"]["cross_source_pairs"],0)

if __name__=="__main__":
    unittest.main()
