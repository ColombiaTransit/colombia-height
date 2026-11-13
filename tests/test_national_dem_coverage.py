import csv
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from national_dem_coverage import (
    PIXELS, classify_mask, geographical_owner,
    intersecting_source_indices, scan, reconcile,
)

class NationalDemCoverageTests(unittest.TestCase):
    def test_mask_statuses(self):
        full=classify_mask(np.ones((256,256),bool))
        self.assertEqual(full["coverage"],"full_dem_coverage")
        self.assertEqual(full["missing_pixels"],0)
        empty=classify_mask(np.zeros((256,256),bool))
        self.assertEqual(empty["coverage"],"no_dem_coverage")
        self.assertEqual(empty["missing_pixels"],PIXELS)
        partial=np.zeros((256,256),bool)
        partial[:16,:]=1
        self.assertEqual(classify_mask(partial)["valid_pixels"],4096)
        self.assertEqual(classify_mask(partial)["coverage"],"partial_dem_coverage")
    def test_owner_is_unique_and_stable(self):
        for z,x,y in [(0,0,0),(8,90,124),(9,143,251),(11,574,1012),(13,2361,3974)]:
            key=geographical_owner(z,x,y)
            self.assertGreaterEqual(key,0)
            self.assertLess(key,32)
            self.assertEqual(key,geographical_owner(z,x,y))
        self.assertEqual(geographical_owner(0,0,0),0)
    def test_candidate_source_degree_intersections(self):
        src=[{"longitude":"-76","latitude":"6"},{"longitude":"-75","latitude":"6"}]
        # Inside cell at -75.5, 6.3: W076 only.
        import mercantile
        t=mercantile.tile(-75.5,6.3,13)
        self.assertEqual(intersecting_source_indices(src,t.z,t.x,t.y),[0])
    def test_a_single_local_tile_can_be_classified_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            manifest=root/"input.csv"
            with manifest.open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=["name","latitude","longitude","status","url"])
                w.writeheader()
                w.writerow({"name":"a","latitude":"6","longitude":"-76","status":"ok","url":"https://example.test/a.tif"})
            with patch("national_dem_coverage.assess_tile") as fake:
                fake.return_value=({"coverage":"partial_dem_coverage",
                    "valid_pixels":40000,"missing_pixels":25536},["a"],1)
                result=scan(manifest,root/"out",shard=0,minzoom=0,maxzoom=0,limit=1)
                self.assertEqual(result["tested_tiles"],1)
                self.assertFalse(result["complete"])
                with gzip.open(root/"out"/"dem-coverage-shard-00.ndjson.gz","rt") as f:
                    items=[json.loads(s) for s in f]
                self.assertEqual(items[0]["coverage"],"partial_dem_coverage")
                self.assertEqual(items[0]["missing_pixels"],25536)
                self.assertFalse(result["publication_allowed"])
    def test_reconcile_cannot_accept_sample_artifacts(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError,"32 shards"):
                reconcile(Path(d),Path(d)/"report.json")

if __name__=="__main__":unittest.main()
