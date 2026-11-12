#!/usr/bin/env python3
"""Tile-aligned, strict Terrain-RGB processing for bounded land test regions.

A production build must never encode missing DEM pixels as -10000m (which
becomes RGB 0,0,0 and produces false terrain trenches). In strict mode, a
partly uncovered tile fails the build rather than silently emitting bad data.
"""
import argparse
import io
import json
import math
import sqlite3
from pathlib import Path

import mercantile
import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.transform import from_bounds
from rasterio.warp import reproject
from rasterio.windows import from_bounds as window_from_bounds

from medellin_terrain import download, rgb_encode, source_tiles, MED, TILE_SIZE, NODATA

REGIONS = {
    "antioquia": (-76.15, 5.85, -75.0, 7.10),
    "medellin": (-75.85, 6.05, -75.25, 6.55),
}

def aligned_bounds(bbox, zoom):
    """Return exact geographic envelope of all slippy tiles meeting bbox."""
    ts = list(mercantile.tiles(*bbox, zooms=[zoom]))
    if not ts:
        raise ValueError("Empty tile set")
    west = min(mercantile.bounds(t).west for t in ts)
    east = max(mercantile.bounds(t).east for t in ts)
    south = min(mercantile.bounds(t).south for t in ts)
    north = max(mercantile.bounds(t).north for t in ts)
    return (west, south, east, north)

def prepare_sources(bbox, sources_dir):
    """Fetch all 1-degree COGs for aligned bounds plus DEM pixel buffer."""
    pad = 2 / 3600
    padded = (bbox[0]-pad, bbox[1]-pad, bbox[2]+pad, bbox[3]+pad)
    entries = source_tiles(padded)
    if not entries:
        raise RuntimeError("No Copernicus sources for tile-aligned area")
    paths = []
    sources_dir.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        target = sources_dir / (entry["name"] + ".tif")
        print(f"COG {entry['name']}", flush=True)
        download(entry["url"], target)
        paths.append(target)
    return entries, paths

def build_raster(paths, bbox):
    handles = [rasterio.open(path) for path in paths]
    try:
        raster, transform = merge(
            handles, bounds=bbox, res=(1/3600, 1/3600),
            nodata=NODATA, masked=False, resampling=Resampling.bilinear,
        )
    finally:
        for handle in handles:
            handle.close()
    return raster[0].astype("float32", copy=False), transform

def encode_tile(heights, strict=True):
    """Only accept finite, fully covered DEM tiles; avoid fabricated heights."""
    valid = np.isfinite(heights) & (heights != NODATA)
    missing = int(np.size(valid) - np.count_nonzero(valid))
    if missing and strict:
        raise ValueError(f"DEM coverage has {missing} missing pixels")
    if missing:
        return None, missing
    rgb = rgb_encode(heights)
    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), 0

def write_tiles(out_path, dem, transform, bounds, minzoom, maxzoom):
    out_path.unlink(missing_ok=True)
    db = sqlite3.connect(out_path)
    metadata = {
        "name": "Copernicus Colombia Strict Terrain RGB Antioquia Test",
        "format": "png", "type": "baselayer", "version": "1.0",
        "minzoom": str(minzoom), "maxzoom": str(maxzoom),
        "bounds": ",".join(map(str, bounds)),
        "attribution": "Contains modified Copernicus DEM data",
    }
    try:
        db.execute("CREATE TABLE metadata (name TEXT PRIMARY KEY, value TEXT)")
        db.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB, PRIMARY KEY (zoom_level,tile_column,tile_row))")
        db.executemany("INSERT INTO metadata VALUES (?,?)", metadata.items())
        counts = {}
        missing_by_zoom = {}
        sample_rgb = None
        for zoom in range(minzoom, maxzoom+1):
            count = 0
            missing_total = 0
            for t in mercantile.tiles(*bounds, zooms=[zoom]):
                b = mercantile.xy_bounds(t)
                dst = np.full((TILE_SIZE, TILE_SIZE), NODATA, dtype=np.float32)
                reproject(
                    source=dem, destination=dst,
                    src_transform=transform, src_crs="EPSG:4326", src_nodata=NODATA,
                    dst_transform=from_bounds(b.left,b.bottom,b.right,b.top,TILE_SIZE,TILE_SIZE),
                    dst_crs="EPSG:3857", dst_nodata=NODATA,
                    resampling=Resampling.bilinear, num_threads=2
                )
                data, missing = encode_tile(dst, strict=False)
                missing_total += missing
                if data is None:
                    # Keep incomplete tiles out of the published dataset entirely.
                    continue
                db.execute("INSERT INTO tiles VALUES (?,?,?,?)",
                           (zoom,t.x,(1<<zoom)-1-t.y,data))
                count+=1
            counts[str(zoom)] = count
            missing_by_zoom[str(zoom)] = missing_total
            db.commit()
        if sum(counts.values()) <= 0:
            raise RuntimeError("No complete terrain tiles produced")
        if any(missing_by_zoom.values()):
            raise RuntimeError(
                "Incomplete DEM tiles detected. No publishable MBTiles produced: "
                + json.dumps(missing_by_zoom)
            )
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("SQLite integrity check failed")
        return counts, missing_by_zoom
    finally:
        db.close()

def run(output, region, minzoom, maxzoom):
    desired = REGIONS[region]
    aligned = aligned_bounds(desired, minzoom)
    output.mkdir(parents=True, exist_ok=True)
    entries, paths = prepare_sources(aligned, output / "sources")
    # Full slippy tile envelope, even if its geographic bbox extends beyond desired.
    pad = 2/3600
    mosaic = (aligned[0]-pad, aligned[1]-pad, aligned[2]+pad, aligned[3]+pad)
    dem, transform = build_raster(paths, mosaic)
    outfile = output / "antioquia-terrain-strict.mbtiles"
    try:
        counts, missing = write_tiles(outfile, dem, transform, aligned, minzoom, maxzoom)
    except Exception:
        outfile.unlink(missing_ok=True)
        raise
    report = {
        "region": region,
        "requested_bbox": desired, "aligned_bbox": aligned,
        "source_tiles": [x["name"] for x in entries],
        "download_bytes": sum(p.stat().st_size for p in paths),
        "tile_counts": counts, "missing_pixels_by_zoom": missing,
        "mbtiles_bytes": outfile.stat().st_size,
        "strict_validation": all(v == 0 for v in missing.values()),
        "note": "A strict multi-source test; complete ocean/national coverage requires explicit nodata policy."
    }
    (output / "terrain-strict-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--region",choices=REGIONS,default="antioquia")
    parser.add_argument("--min-zoom",type=int,default=11)
    parser.add_argument("--max-zoom",type=int,default=13)
    parser.add_argument("--output",type=Path,default=Path("output/strict"))
    args=parser.parse_args()
    if not 9<=args.min_zoom<=args.max_zoom<=13:
        parser.error("Require 9 <= minzoom <= maxzoom <= 13")
    run(args.output,args.region,args.min_zoom,args.max_zoom)

if __name__=="__main__":
    main()
