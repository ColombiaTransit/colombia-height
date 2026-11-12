import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from reconcile_minor_islands import reconcile

class ReconciliationTests(unittest.TestCase):
    def test_all_eight_sources_present(self):
        root=Path(__file__).resolve().parents[1]
        review=json.loads((root/"data/minor-island-review.json").read_text())
        self.assertEqual(len(review["candidates"]),8)
        self.assertEqual(len({r["id"] for r in review["candidates"]}),8)
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/"in.csv"
            with f.open("w",newline="") as h:
                w=csv.DictWriter(h,fieldnames=["name"]);w.writeheader()
                for name in sorted({r["expected_cog"] for r in review["candidates"]}):
                    w.writerow({"name":name})
            report=reconcile(f,root/"data/minor-island-review.json",Path(d)/"result.json")
            self.assertEqual(report["already_covered_count"],8)
            self.assertEqual(report["additional_source_tile_names"],[])

if __name__=="__main__":
    unittest.main()
