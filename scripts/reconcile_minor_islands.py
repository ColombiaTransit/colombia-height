#!/usr/bin/env python3
"""Reconcile the eight previously discovered minor-island candidates.

No jurisdiction claims: tests only whether nominated source cells are already
present and whether a source COG is indexed. DEM pixel validity is separate.
"""
import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

def reconcile(manifest_path, review_path, output_path):
    with open(manifest_path,newline="",encoding="utf-8") as fh:
        manifest={r["name"] for r in csv.DictReader(fh)}
    review=json.loads(Path(review_path).read_text())
    candidates=review["candidates"]
    if len(candidates)!=8:
        raise ValueError("Expected eight baseline Natural Earth review candidates")
    resolved=[]
    for row in candidates:
        covered=row["expected_cog"] in manifest
        resolved.append({**row,
            "included_in_current_source_manifest":covered,
            "requires_additional_source_tile":not covered,
            "review_status":"source_cell_in_manifest" if covered else "source_cell_missing",
            "territory_status":"unverified",
            "native_dem_pixel_status":"unverified",
        })
    result={
        "candidate_count":len(resolved),
        "already_covered_count":sum(r["included_in_current_source_manifest"] for r in resolved),
        "additional_source_tile_names":sorted(set(r["expected_cog"] for r in resolved if not r["included_in_current_source_manifest"])),
        "groups":dict(Counter(r["near_registry_id"] for r in resolved)),
        "candidates":resolved,
        "interpretation":"Source cell included is NOT proof of terrain-height validity or national jurisdiction."
    }
    output_path.parent.mkdir(parents=True,exist_ok=True)
    output_path.write_text(json.dumps(result,indent=2)+"\n")
    if result["additional_source_tile_names"]:
        raise RuntimeError("Named minor-island DEM source tiles missing from current manifest")
    print(json.dumps({k:v for k,v in result.items() if k!="candidates"},indent=2))
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    p.add_argument("--review",type=Path,default=Path("data/minor-island-review.json"))
    p.add_argument("--output",type=Path,default=Path("output/minor-island-reconciliation.json"))
    args=p.parse_args()
    reconcile(args.manifest,args.review,args.output)

if __name__=="__main__":
    main()
