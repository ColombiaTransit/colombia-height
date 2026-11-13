#!/usr/bin/env python3
"""Exact native-COG pixel coverage register for countrywide terrain candidates.

Coverage != land: valid offshore DEM values are not a water policy, and
source degree-cell intersections alone do not prove complete pixel coverage.
Each z/x/y candidate is evaluated once at 256x256 pixels, without encoding
RGB and without making any permanent MBTiles/release.
"""
import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter,defaultdict
from contextlib import ExitStack
from datetime import datetime,timezone
from pathlib import Path

import mercantile
import numpy as np
import rasterio

from medellin_terrain import download
from national_tile_plan import candidate_tiles,parse_manifest
from two_cog_seam_pilot import warp_sources

PIXELS=256*256
# Geographic assignment keeps high-zoom work regional and native COG
# downloads in the same runner cache. Low zoom needs broader coverage.
LON_MIN,LON_MAX=-84.,-66.
LAT_MIN,LAT_MAX=-5.,17.

def geographical_owner(z,x,y,shards=32):
    """Stable, deterministic geographic owner for one XYZ tile."""
    if shards!=32:
        raise ValueError("This register uses 8 longitude by 4 latitude regions (32 shards)")
    if z<9:
        return 0
    b=mercantile.bounds(x,y,z)
    lon=(b.west+b.east)/2
    lat=(b.south+b.north)/2
    col=min(7,max(0,math.floor((lon-LON_MIN)/(LON_MAX-LON_MIN)*8)))
    row=min(3,max(0,math.floor((lat-LAT_MIN)/(LAT_MAX-LAT_MIN)*4)))
    return int(row*8+col)

def intersecting_source_indices(sources,z,x,y):
    b=mercantile.bounds(x,y,z)
    # Allow a native-pixel margin for bilinear reprojection at degree edges;
    # actual dataset nodata/provenance remains the source of truth.
    eps=2./3600
    return [i for i,s in enumerate(sources)
            if float(s["longitude"])<b.east+eps
            and float(s["longitude"])+1>b.west-eps
            and float(s["latitude"])<b.north+eps
            and float(s["latitude"])+1>b.south-eps]

def classify_mask(mask):
    valid=int(np.count_nonzero(mask))
    if valid==PIXELS:
        status="full_dem_coverage"
    elif valid:
        status="partial_dem_coverage"
    else:
        status="no_dem_coverage"
    return {"coverage":status,"valid_pixels":valid,
            "missing_pixels":PIXELS-valid}

def local_cogs(sources,indices,cache,opened):
    selected=[]
    for i in indices:
        item=sources[i]
        if i not in opened:
            path=cache/(item["name"]+".tif")
            download(item["url"],path)
            opened[i]=rasterio.open(path)
        selected.append(opened[i])
    return selected

def assess_tile(sources,opened,cache,tile):
    z,x,y=tile
    indices=intersecting_source_indices(sources,z,x,y)
    if not indices:
        result=classify_mask(np.zeros((256,256),dtype=bool))
        return result,[],0
    opened_sources=local_cogs(sources,indices,cache,opened)
    height,provenance,overlaps,overlap_delta=warp_sources(opened_sources,tile)
    valid=(provenance>0)&np.isfinite(height)&(height!=-9999.0)
    result=classify_mask(valid)
    result["source_overlap_pixels"]=int(overlaps)
    result["max_source_overlap_delta_m"]=round(float(overlap_delta),3)
    result["source_cogs_used"]=len(set(int(a) for a in np.unique(provenance) if a))
    return result,[sources[i]["name"] for i in indices],len(indices)

def scan(manifest,out_dir,shard=0,shards=32,minzoom=0,maxzoom=13,
         limit=None):
    if not 0<=minzoom<=maxzoom<=13:
        raise ValueError("Invalid zoom range 0–13")
    if not 0<=shard<shards or shards!=32:
        raise ValueError("Expected shard in 0–31")
    sources=parse_manifest(manifest)
    root=Path(out_dir)
    root.mkdir(parents=True,exist_ok=True)
    cache=root/"source-cache"
    cache.mkdir(exist_ok=True)
    rows=root/f"dem-coverage-shard-{shard:02d}.ndjson.gz"
    summary_path=root/f"dem-coverage-summary-{shard:02d}.json"
    stats=Counter()
    zoom_stats=defaultdict(Counter)
    checked=0
    input_candidates=0
    sha=hashlib.sha256()
    opened={}
    try:
        with gzip.open(rows,"wt",encoding="utf-8",compresslevel=6) as stream:
            for z in range(minzoom,maxzoom+1):
                for x,y in sorted(candidate_tiles(sources,z)):
                    input_candidates+=1
                    if geographical_owner(z,x,y,shards)!=shard:
                        continue
                    if limit is not None and checked>=limit:
                        break
                    result,names,source_count=assess_tile(sources,opened,cache,(z,x,y))
                    row={"z":z,"x":x,"y":y,"tms_y":(1<<z)-1-y,
                         "shard":shard,**result,
                         "source_cells_intersected":source_count}
                    line=json.dumps(row,separators=(",",":"),sort_keys=True)
                    stream.write(line+"\n")
                    sha.update(line.encode()+b"\n")
                    stats[result["coverage"]]+=1
                    zoom_stats[str(z)][result["coverage"]]+=1
                    checked+=1
                if limit is not None and checked>=limit:
                    break
                print(f"shard {shard:02d} scanned through z{z}: {checked} tiles",flush=True)
    finally:
        for src in opened.values():
            src.close()
    summary={
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "source_manifest":str(manifest),"source_cog_count":len(sources),
        "shard":shard,"shards":shards,"minzoom":minzoom,"maxzoom":maxzoom,
        "candidate_tiles_seen_pre_shard":input_candidates if limit is None else None,
        "tested_tiles":checked,
        "coverage_counts":dict(stats),
        "zoom_coverage_counts":{k:dict(v) for k,v in sorted(zoom_stats.items(),key=lambda p:int(p[0]))},
        "registered_source_files_downloaded":len(opened),
        "sha256_uncompressed_ndjson":sha.hexdigest(),
        "complete":limit is None,
        "publication_allowed":False,
        "unresolved_policy":[
            "Full DEM pixels do not establish Colombian land or island jurisdiction",
            "Partially covered tiles need strict skip or separate water-aware encoding policy",
            "Coverage only checks Copernicus DEM, not ground truth or official coastline",
            "A national register requires all 32 shard summaries and unique XYZ reconciliation",
        ]}
    summary_path.write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary,indent=2),flush=True)
    return summary

def reconcile(root,out):
    files=sorted(Path(root).glob("dem-coverage-shard-*.ndjson.gz"))
    summaries=sorted(Path(root).glob("dem-coverage-summary-*.json"))
    if len(files)!=32 or len(summaries)!=32:
        raise RuntimeError(f"National reconciliation requires exactly 32 shards; got {len(files)} records and {len(summaries)} summaries")
    seen=set()
    counts=Counter()
    zoom=defaultdict(Counter)
    sample={}
    for file in files:
        shard=int(file.stem.split("-")[-1].split(".")[0])
        with gzip.open(file,"rt",encoding="utf-8") as f:
            for line in f:
                record=json.loads(line)
                key=(record["z"],record["x"],record["y"])
                if key in seen:
                    raise AssertionError(f"Duplicate national XYZ {key}")
                if geographical_owner(*key)!=shard or record["shard"]!=shard:
                    raise AssertionError(f"Wrong geographical ownership {key} in shard {shard}")
                seen.add(key)
                counts[record["coverage"]]+=1
                zoom[str(record["z"])][record["coverage"]]+=1
                if record["coverage"]!="full_dem_coverage" and len(sample)<50:
                    sample[str(key)]={
                        "missing_pixels":record["missing_pixels"],
                        "status":record["coverage"]}
    summaries_json=[json.loads(f.read_text()) for f in summaries]
    if any(not s["complete"] for s in summaries_json):
        raise AssertionError("Incomplete sample shard cannot be national register")
    if sum(s["tested_tiles"] for s in summaries_json)!=len(seen):
        raise AssertionError("Candidate/shard count mismatch")
    # Calculate expected candidate count independently from the same manifest,
    # so a systematically omitted shard cannot look like a clean success.
    manifest=Path(summaries_json[0]["source_manifest"])
    # The workflow places the source manifest in the same relative path
    # for all shards, and in the reconciliation job.
    sources=parse_manifest(manifest)
    expected=sum(len(candidate_tiles(sources,z)) for z in range(14))
    if len(seen)!=expected:
        raise AssertionError(f"Missing national candidates: {len(seen)} vs {expected}")
    out=Path(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    report={
        "status":"national_source_dem_coverage_inventoried",
        "source_cog_count":len(sources),
        "candidate_tile_count":expected,
        "classified_tile_count":len(seen),
        "coverage_counts":dict(counts),
        "zoom_coverage_counts":dict(zoom),
        "non_full_examples":sample,
        "all_candidate_xyz_unique":True,
        "all_32_shards_present":True,
        "national_publication_allowed":False,
        "interpretation":"This is actual 256x256 sampled DEM-pixel coverage, not a sovereign land mask, ocean mask, or release authorization."}
    out.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return report

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    a.add_argument("--output",type=Path,default=Path("output/national-coverage"))
    a.add_argument("--shard",type=int,default=0)
    a.add_argument("--shards",type=int,default=32)
    a.add_argument("--minzoom",type=int,default=0)
    a.add_argument("--maxzoom",type=int,default=13)
    a.add_argument("--limit",type=int)
    a.add_argument("--reconcile",action="store_true")
    args=a.parse_args()
    if args.reconcile:
        reconcile(args.output,args.output/"national-dem-coverage-summary.json")
    else:
        scan(args.manifest,args.output,args.shard,args.shards,args.minzoom,args.maxzoom,args.limit)

if __name__=="__main__":
    main()
