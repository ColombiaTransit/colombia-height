#!/usr/bin/env python3
"""Inventory GLO-30 tiles overlapping geoBoundaries Colombia ADM0, without downloading DEMs."""
import argparse
import concurrent.futures
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from shapely.geometry import box, shape
from shapely.ops import unary_union

BUCKET = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com"
TILES_URL = BUCKET + "/tileList.txt"
BOUNDARY_URL = "https://www.geoboundaries.org/api/current/gbOpen/COL/ADM0/"
TILE_RE = re.compile(r"Copernicus_DSM_COG_10_([NS])(\d{2})_00_([EW])(\d{3})_00_DEM")

def get_json(url):
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    return r.json()

def parse_tile(line):
    m = TILE_RE.search(line)
    if not m:
        return None
    ns, latitude, ew, longitude = m.groups()
    latitude = int(latitude) * (1 if ns == "N" else -1)
    longitude = int(longitude) * (1 if ew == "E" else -1)
    name = m.group(0)
    return {
        "name": name, "latitude": latitude, "longitude": longitude,
        "url": f"{BUCKET}/{name}/{name}.tif"
    }

def inspect_size(item):
    item = dict(item)
    try:
        response = requests.head(item["url"], timeout=45, allow_redirects=True)
        response.raise_for_status()
        n = response.headers.get("Content-Length")
        item["size_bytes"] = int(n) if n else ""
        item["status"] = "ok" if n else "missing-content-length"
    except requests.RequestException as error:
        item["size_bytes"] = ""
        item["status"] = "head-error:" + type(error).__name__
    return item

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output"))
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 16:
        parser.error("--workers must be between 1 and 16")
    args.output.mkdir(parents=True, exist_ok=True)

    response = requests.get(TILES_URL, timeout=90)
    response.raise_for_status()
    indexed = {}
    for line in response.text.splitlines():
        tile = parse_tile(line)
        if tile:
            indexed[tile["name"]] = tile
    if not indexed:
        raise RuntimeError("No valid tiles in the public GLO-30 tileList.txt")

    metadata = get_json(BOUNDARY_URL)
    geometry_url = metadata["gjDownloadURL"]
    geojson = get_json(geometry_url)
    features = geojson.get("features", [])
    if not features:
        raise RuntimeError("Boundary GeoJSON does not contain features")
    boundary = unary_union([shape(feature["geometry"]) for feature in features])
    if boundary.is_empty:
        raise RuntimeError("Empty country boundary")

    # One-degree tile bounds are approximate for intersection only. Border and
    # islands need validation against native DEM coverage in a later stage.
    selected = [
        item for item in indexed.values()
        if boundary.intersects(box(item["longitude"], item["latitude"],
                                   item["longitude"] + 1, item["latitude"] + 1))
    ]
    selected.sort(key=lambda x: (x["latitude"], x["longitude"]))

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        inspected = list(pool.map(inspect_size, selected))

    csv_file = args.output / "colombia_dem_manifest.csv"
    with csv_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "name", "latitude", "longitude", "size_bytes", "status", "url"
        ])
        writer.writeheader()
        writer.writerows(inspected)

    unresolved = [item["name"] for item in inspected if item["status"] != "ok"]
    size_bytes = sum(int(item["size_bytes"]) for item in inspected if item["size_bytes"] != "")
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": TILES_URL,
        "boundary_metadata_url": BOUNDARY_URL,
        "boundary_geometry_url": geometry_url,
        "boundary_license": metadata.get("boundaryLicense"),
        "global_indexed_tiles": len(indexed),
        "colombia_tiles": len(inspected),
        "known_download_bytes": size_bytes,
        "known_download_gib": round(size_bytes / 1024**3, 3),
        "unverified_size_tiles": unresolved,
        "all_sizes_confirmed": len(unresolved) == 0,
        "warning": "Geometry-derived selection; island coverage and tile edges need manual validation."
    }
    (args.output / "colombia_dem_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
