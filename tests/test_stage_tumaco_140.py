"""Previous 139 native COGs are immutable; only Tumaco may be appended."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from stage_tumaco_140 import (
    ISLANDS,TUMACO,STAGING_RUN_139,review_decision,validate_staged_baseline,append_reviewed_COG,
)


class StageOnlyTumaco140Tests(unittest.TestCase):
    def reviewed(self):
        import json
        return json.loads((Path(__file__).resolve().parents[1]/
                           "data/staged-tumaco-third-source-2026-11-14.json").read_text())

    def baseline(self):
        a=[{"name":f"native_original_{i}","status":"ok","latitude":"1","longitude":"-79"}
           for i in range(137)]
        a.extend({"name":name,"status":"ok","latitude":"3","longitude":"-79"}
                 for name in sorted(ISLANDS))
        return a

    def test_real_approved_IGAC_and_79W_tumaco_evidence(self):
        review_decision(self.reviewed())

    def test_mutated_79W_native_seam_is_rejected(self):
        data=self.reviewed()
        data["candidate"]["native_30m_79W_border_disproportionate_flag_count"]=1
        with self.assertRaisesRegex(AssertionError,"evidence"):
            review_decision(data)

    def test_publication_is_always_rejected(self):
        data=self.reviewed()
        data["national_Terrain_RGB_publication_allowed"]=True
        with self.assertRaisesRegex(AssertionError,"safety"):
            review_decision(data)

    def test_append_only_retains_exact_original_139_COG_order(self):
        old=self.baseline()
        self.assertEqual(len(validate_staged_baseline(old)),139)
        new={"name":TUMACO,"status":"ok","latitude":"1","longitude":"-80",
             "size_bytes":34512,"url":"https://example.org/"+TUMACO+".tif"}
        staged=append_reviewed_COG(old,new)
        self.assertEqual(len(staged),140)
        self.assertEqual([x["name"] for x in staged[:139]],
                         [x["name"] for x in old])
        self.assertEqual(staged[139]["name"],TUMACO)
        self.assertEqual(len(old),139)

    def test_duplicate_source_fails_closed(self):
        old=self.baseline()
        old[5]["name"]=TUMACO
        with self.assertRaisesRegex(AssertionError,"already selected"):
            validate_staged_baseline(old)

    def test_new_source_must_be_original_valid_native_COG(self):
        invalid={"name":TUMACO,"status":"ok","latitude":"1","longitude":"-80",
                 "size_bytes":0,"url":"https://example.org/"+TUMACO+".tif"}
        with self.assertRaisesRegex(AssertionError,"metadata invalid"):
            append_reviewed_COG(self.baseline(),invalid)


if __name__=="__main__":
    unittest.main()
