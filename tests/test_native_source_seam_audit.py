import sys,unittest
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from native_source_seam_audit import seam_metrics,stats

class NativeSeamAuditTests(unittest.TestCase):
    def test_normal_gradient_not_flagged(self):
        south=np.array([[40,100],[38,98],[36,96],[34,94],[32,92],[30,90]],float)
        north=np.array([[42,102],[44,104],[46,106],[48,108],[50,110],[52,112]],float)
        r=seam_metrics(south,north)
        self.assertEqual(r["native_cross_border"]["maximum_m"],2)
        self.assertEqual(r["border_gt_40m_and_gt_3x_immediate_local_gradient"],0)
    def test_true_discontinuity_flagged(self):
        south=np.zeros((6,2))
        north=np.full((6,2),100.)
        r=seam_metrics(south,north)
        self.assertEqual(r["border_gt_40m_and_gt_3x_immediate_local_gradient"],2)
        self.assertEqual(r["border_over_100m"],0)
    def test_nodata_ignored(self):
        v=stats([10,float("nan"),20])
        self.assertEqual(v["count"],2)

if __name__=="__main__":unittest.main()
