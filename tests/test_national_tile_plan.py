import csv
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from national_tile_plan import candidate_tiles, owner, run

class ShardPlanTests(unittest.TestCase):
    def test_global_low_zoom_owned_by_one_shard(self):
        for z in range(7):
            self.assertEqual(owner(z,0,0,32),0)
    def test_child_of_z7_keeps_shard(self):
        for z in (7,8,9,13):
            x,y=22<<(z-7),55<<(z-7)
            self.assertEqual(owner(z,x,y,32),owner(7,22,55,32))
    def test_overlapping_sources_deduplicate_and_output_unique(self):
        sources=[{"latitude":"6","longitude":"-76"},{"latitude":"6","longitude":"-76"}]
        self.assertEqual(candidate_tiles(sources,10),candidate_tiles(sources[:1],10))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            manifest=root/"manifest.csv"
            with manifest.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["name","latitude","longitude","status"])
                w.writeheader()
                w.writerow({"name":"a","latitude":"6","longitude":"-76","status":"ok"})
                w.writerow({"name":"b","latitude":"6","longitude":"-75","status":"ok"})
            result=run(manifest,root/"out",0,8,8)
            observed=set()
            for file in (root/"out").glob("candidate-shard-*.ndjson"):
                import json
                shard=int(file.stem.split("-")[-1])
                for row in file.read_text().splitlines():
                    t=json.loads(row)
                    key=(t["z"],t["x"],t["y"])
                    self.assertNotIn(key,observed)
                    observed.add(key)
                    self.assertEqual(shard,owner(*key,8))
            self.assertEqual(len(observed),result["candidate_tile_count"])

if __name__=="__main__":
    unittest.main()
