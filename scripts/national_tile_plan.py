#!/usr/bin/env python3
"""Plan unique z/x/y ownership over the extended GLO-30 source-cell inventory.

This is a dry-run PLANNER, not a land mask or an elevation generator.
All overlapping 1° candidates get deduplicated before sharding; coarse
map tiles are assigned a single owner. Ocean/nodata decisions are pending.
"""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

import mercantile

def owner(z, x, y, shards):
    """Stable region-independent owner; low zooms have one global shard."""
    if z < 7:
        return 0
    px, py = x >> (z-7), y >> (z-7)
    # Multiplicative mixing avoids Python's randomized hash.
    return ((px * 2654435761) ^ (py * 2246822519)) % shards

def parse_manifest(path):
    with open(path, newline="", encoding="utf-8") as stream:
        sources=list(csv.DictReader(stream))
    if not sources:
        raise ValueError("Empty inventory")
    names=[s["name"] for s in sources]
    if len(names)!=len(set(names)):
        raise ValueError("Duplicate source names")
    if any(s["status"]!="ok" for s in sources):
        raise ValueError("Unverified COG sizes")
    return sources

def candidate_tiles(sources, z):
    """Conservative set from source bounding degree cells, not land polygons."""
    unique=set()
    for source in sources:
        lat=int(source["latitude"]);lon=int(source["longitude"])
        # epsilon avoids adding adjacent tiles for exact grid-edge coincidence.
        unique.update((t.x,t.y) for t in mercantile.tiles(
            lon+1e-10,lat+1e-10,lon+1-1e-10,lat+1-1e-10,
            zooms=[z]))
    return unique

def run(manifest, output, minzoom, maxzoom, shards):
    if not 0<=minzoom<=maxzoom<=13:
        raise ValueError("Requires 0 <= minzoom <= maxzoom <= 13")
    if not 1<=shards<=128:
        raise ValueError("Requires 1 <= shards <= 128")
    sources=parse_manifest(manifest)
    output.mkdir(parents=True,exist_ok=True)
    handles={}
    sha=hashlib.sha256()
    zoom_stats={}
    shard_counts=Counter()
    seen_total=0
    try:
        for z in range(minzoom,maxzoom+1):
            tiles=candidate_tiles(sources,z)
            zoom_stats[str(z)]=len(tiles)
            for x,y in sorted(tiles):
                k=owner(z,x,y,shards)
                if k not in handles:
                    handles[k]=(output/f"candidate-shard-{k:03d}.ndjson").open("w",encoding="utf-8")
                line=json.dumps({"z":z,"x":x,"y":y,"tms_y":(1<<z)-1-y},separators=(",",":"))
                handles[k].write(line+"\n")
                sha.update(line.encode("utf-8")+b"\n")
                shard_counts[str(k)]+=1
                seen_total+=1
    finally:
        for h in handles.values():
            h.close()
    if seen_total!=sum(shard_counts.values()):
        raise AssertionError("Tile owner counting mismatch")
    report={
        "status":"planning_only_not_authorized_for_publication",
        "source_cog_count":len(sources),
        "candidate_tile_count":seen_total,
        "tile_count_by_zoom":zoom_stats,
        "shard_count_requested":shards,
        "shard_count_used":len(handles),
        "tiles_by_shard":dict(sorted(shard_counts.items(),key=lambda a:int(a[0]))),
        "candidate_tile_sha256":sha.hexdigest(),
        "all_candidates_have_one_owner":True,
        "selection_method":"union of 1 degree source cells; not DEM land/validity mask",
        "low_zoom_owner":"shard 0 for zooms 0 through 6",
        "publication_blockers":[
            "Source degree squares include ocean; actual DEM masks not verified nationally",
            "Overwater policy and coastal blending not implemented",
            "Islands and official jurisdiction remain under review",
            "This list must not be converted blindly with the strict inland generator",
            "MBTiles shards are not generated or uploaded by this workflow"
        ],
    }
    (output/"national-tile-plan.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)
    return report

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    ap.add_argument("--output",type=Path,default=Path("output/national-plan"))
    ap.add_argument("--minzoom",type=int,default=0)
    ap.add_argument("--maxzoom",type=int,default=13)
    ap.add_argument("--shards",type=int,default=32)
    a=ap.parse_args()
    run(a.manifest,a.output,a.minzoom,a.maxzoom,a.shards)

if __name__=="__main__":
    main()
