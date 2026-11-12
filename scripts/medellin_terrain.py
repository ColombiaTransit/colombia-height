#!/usr/bin/env python3
"""Small, repeatable Mapbox Terrain-RGB MBTiles pilot for Medellín.

No source DEMs are stored in git. Fetches intersecting Copernicus GLO-30 COGs
and resamples them to Web Mercator PNG tiles, retaining 0.1 m RGB precision.
"""
import argparse
import io
import json
import math
import sqlite3
import time
from pathlib import Path

import mercantile
import numpy as np
import requests
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.transform import from_bounds
from rasterio.warp import reproject

from inventory import BUCKET, TILES_URL, parse_tile

# Bounding box deliberately wholly within one latitude degree; two longitude cells.
BBOX = (-75.85, 6.05, -75.25, 6.55)  # west,south,east,north
MED = (-75.5636, 6.2518)  # lon,lat
NODATA = -9999.0
TILE_SIZE = 256

def download(url, dest):
    """Stream source data to disk with retry; never load a COG into RAM."""
    if dest.exists() and dest.stat().st_size > 0:
        return
    for attempt in range(3):
        tmp = dest.with_suffix(".partial")
        try:
            with requests.get(url, stream=True, timeout=(30, 120)) as response:
                response.raise_for_status()
                expected = int(response.headers.get("Content-Length", "0"))
                with tmp.open("wb") as output:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            output.write(chunk)
                if expected and tmp.stat().st_size != expected:
                    raise IOError("Incomplete download " + dest.name)
            tmp.replace(dest)
            return
        except (requests.RequestException, OSError):
            tmp.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))

def source_tiles(bbox):
    r = requests.get(TILES_URL, timeout=90)
    r.raise_for_status()
    index = {}
    for line in r.text.splitlines():
        entry = parse_tile(line)
        if entry:
            index[entry["name"]] = entry
    west, south, east, north = bbox
    return sorted(
        (t for t in index.values()
         if t["longitude"] < east and t["longitude"] + 1 > west
         and t["latitude"] < north and t["latitude"] + 1 > south),
        key=lambda t: t["name"],
    )

def rgb_encode(height):
    """Mapbox Terrain-RGB: h = -10000 + (R*65536+G*256+B)*0.1."""
    values = np.rint((height.astype(np.float64) + 10000.0) * 10).astype(np.int64)
    np.clip(values, 0, 16777215, out=values)
    rgb = np.empty((*values.shape, 3), dtype=np.uint8)
    rgb[..., 0] = (values >> 16) & 255
    rgb[..., 1] = (values >> 8) & 255
    rgb[..., 2] = values & 255
    return rgb

def rgb_decode(rgb):
    return -10000.0 + (int(rgb[0]) * 65536 + int(rgb[1]) * 256 + int(rgb[2])) * 0.1

def create_mbtiles(path, data, transform, zoom_min, zoom_max, bbox):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
    conn.execute("CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)")
    conn.execute("CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)")
    west, south, east, north = bbox
    metadata = {
        "name": "Copernicus GLO-30 Medellin Terrain RGB Pilot",
        "type": "baselayer", "version": "1.0", "format": "png",
        "bounds": ",".join(str(x) for x in bbox),
        "center": f"{MED[0]},{MED[1]},{zoom_max}",
        "minzoom": str(zoom_min), "maxzoom": str(zoom_max),
        "attribution": "Contains modified Copernicus DEM data (2026)",
        "description": "Mapbox Terrain-RGB encoding; source Copernicus DEM GLO-30",
    }
    conn.executemany("INSERT INTO metadata VALUES (?,?)", metadata.items())
    counter = 0
    tiles_per_zoom = {}
    for zoom in range(zoom_min, zoom_max + 1):
        count = 0
        for tile in mercantile.tiles(west, south, east, north, zooms=[zoom]):
            bounds = mercantile.xy_bounds(tile)
            out = np.full((TILE_SIZE, TILE_SIZE), NODATA, dtype=np.float32)
            reproject(
                source=data,
                destination=out,
                src_transform=transform,
                src_crs="EPSG:4326",
                src_nodata=NODATA,
                dst_transform=from_bounds(bounds.left, bounds.bottom, bounds.right, bounds.top, TILE_SIZE, TILE_SIZE),
                dst_crs="EPSG:3857",
                dst_nodata=NODATA,
                resampling=Resampling.bilinear,
                num_threads=2,
            )
            good = np.isfinite(out) & (out != NODATA)
            if not np.any(good):
                continue
            rgb = rgb_encode(np.where(good, out, -10000.0))
            im = Image.fromarray(rgb, mode="RGB")
            buffer = io.BytesIO()
            im.save(buffer, format="PNG", optimize=True)
            conn.execute("INSERT INTO tiles VALUES (?,?,?,?)",
                         (zoom, tile.x, (1 << zoom) - tile.y - 1, buffer.getvalue()))
            count += 1
        conn.commit()
        tiles_per_zoom[str(zoom)] = count
        counter += count
    conn.close()
    return counter, tiles_per_zoom

def check_mbtiles(path, data, transform, maxzoom):
    with sqlite3.connect(path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
        if count <= 0:
            raise RuntimeError("MBTiles has no tiles")
        t = mercantile.tile(*MED, maxzoom)
        record = conn.execute(
            "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (t.z, t.x, (1 << t.z) - t.y - 1),
        ).fetchone()
        if record is None:
            raise RuntimeError("Medellin sample point has no terrain tile")
        rgb = Image.open(io.BytesIO(record[0])).convert("RGB")
        lnglat_bounds = mercantile.xy_bounds(t)
        x_merc, y_merc = mercantile.xy(*MED)
        px = max(0, min(255, int((x_merc - lnglat_bounds.left) / (lnglat_bounds.right - lnglat_bounds.left) * TILE_SIZE)))
        py = max(0, min(255, int((lnglat_bounds.top - y_merc) / (lnglat_bounds.top - lnglat_bounds.bottom) * TILE_SIZE)))
        actual = rgb_decode(rgb.getpixel((px, py)))
        row, col = rasterio.transform.rowcol(transform, *MED)
        expected = float(data[row, col])
        if not math.isfinite(actual) or expected == NODATA or abs(expected - actual) > 250:
            raise RuntimeError(f"Elevation sample mismatch DEM={expected:.1f} RGB={actual:.1f}")
        return {"tile_count": count, "sample_lon": MED[0], "sample_lat": MED[1],
                "sample_dem_m": round(expected, 1), "sample_rgb_m": round(actual, 1),
                "sample_difference_m": round(actual - expected, 1)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("output/medellin"))
    parser.add_argument("--min-zoom", type=int, default=9)
    parser.add_argument("--max-zoom", type=int, default=12)
    args = parser.parse_args()
    if not (0 <= args.min_zoom <= args.max_zoom <= 13):
        parser.error("zoom range must be between 0 and 13")
    args.output.mkdir(parents=True, exist_ok=True)
    cache = args.output / "sources"
    cache.mkdir(exist_ok=True)
    tiles = source_tiles(BBOX)
    if not tiles:
        raise RuntimeError("Copernicus GLO-30 index lacks Medellin source tiles")
    paths = []
    for tile in tiles:
        target = cache / (tile["name"] + ".tif")
        print(f"Downloading/using {target.name}", flush=True)
        download(tile["url"], target)
        paths.append(target)
    sources = [rasterio.open(p) for p in paths]
    try:
        data, transform = merge(sources, bounds=BBOX, res=(1/3600,1/3600),
                                nodata=NODATA, masked=False, resampling=Resampling.bilinear)
    finally:
        for source in sources:
            source.close()
    if data.shape[0] != 1:
        raise RuntimeError("Expected one DEM band")
    raster = data[0].astype(np.float32, copy=False)
    path = args.output / "medellin-terrain-rgb.mbtiles"
    path.unlink(missing_ok=True)
    count, per_zoom = create_mbtiles(path, raster, transform, args.min_zoom, args.max_zoom, BBOX)
    validation = check_mbtiles(path, raster, transform, args.max_zoom)
    summary = {
        "source": "Copernicus DEM GLO-30 Public",
        "bbox": BBOX,
        "source_tiles": [tile["name"] for tile in tiles],
        "download_bytes": sum(p.stat().st_size for p in paths),
        "zoom_min": args.min_zoom, "zoom_max": args.max_zoom,
        "tiles_created": count, "tiles_per_zoom": per_zoom,
        "mbtiles_bytes": path.stat().st_size,
        "validation": validation,
    }
    (args.output / "medellin-terrain-report.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2), flush=True)

if __name__ == "__main__":
    main()
