#!/usr/bin/env python3
"""Multi-source Antioquia Terrain-RGB pilot plus quantitative edge diagnostics."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from io import BytesIO

import medellin_terrain as build

REGIONS = {
    # Crosses latitude 6°/7° and longitude -76°. A useful multi-source stress test.
    "antioquia": (-76.15, 5.85, -75.0, 7.10),
    "medellin": (-75.85, 6.05, -75.25, 6.55),
}
NODATA_RGB = (0, 0, 0)  # decoded -10000m from our current encoder

def analyze_edges(mbtiles: Path, min_zoom: int, max_zoom: int):
    """Measure adjacent-tile boundary differences and unfilled pixels.

    Differences are diagnostics only: true steep terrain can create high adjacent
    gradients. This is *not* proof of absence of seams or missing DEM coverage.
    """
    stats = {}
    with sqlite3.connect(mbtiles) as conn:
        for z in range(min_zoom, max_zoom + 1):
            rows = conn.execute(
                "SELECT tile_column,tile_row,tile_data FROM tiles WHERE zoom_level=?", (z,)
            ).fetchall()
            tiles = {}
            missing_pixels = 0
            total_pixels = 0
            for x, y, blob in rows:
                arr = np.asarray(Image.open(BytesIO(blob)).convert("RGB"))
                missing_pixels += int(np.all(arr == NODATA_RGB, axis=2).sum())
                total_pixels += arr.shape[0] * arr.shape[1]
                tiles[(x, y)] = arr

            compared_pixels = 0
            possible_edges_over_500m = 0
            worst_delta_m = 0.0
            for (x, y), arr in tiles.items():
                # MBTiles Y increases northward. y same -> eastern neighbor.
                for neighbor, first, last in [
                    ((x + 1, y), arr[:, -1, :], "west"),
                    ((x, y + 1), arr[0, :, :], "south"),
                ]:
                    other = tiles.get(neighbor)
                    if other is None:
                        continue
                    second = other[:, 0, :] if last == "west" else other[-1, :, :]
                    valid = np.any(first != 0, axis=1) & np.any(second != 0, axis=1)
                    if not np.any(valid):
                        continue
                    def decode(v):
                        return v[:, 0].astype(np.int64) * 65536 + v[:, 1].astype(np.int64) * 256 + v[:, 2].astype(np.int64)
                    # Delta in RGB integer units (0.1m), no float subtraction.
                    d = np.abs(decode(first[valid]) - decode(second[valid])) * 0.1
                    compared_pixels += int(d.size)
                    worst_delta_m = max(worst_delta_m, float(d.max()))
                    possible_edges_over_500m += int((d > 500).sum())

            stats[str(z)] = {
                "tiles": len(tiles),
                "tile_boundary_pixels_compared": compared_pixels,
                "max_adjacent_edge_difference_m": round(worst_delta_m, 1),
                "edge_differences_over_500m": possible_edges_over_500m,
                "encoded_no_data_pixels": missing_pixels,
                "no_data_percent": round(missing_pixels / total_pixels * 100, 2) if total_pixels else None,
            }
    return stats

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", choices=REGIONS, default="antioquia")
    parser.add_argument("--min-zoom", type=int, default=11)
    parser.add_argument("--max-zoom", type=int, default=13)
    parser.add_argument("--output", type=Path, default=Path("output/antioquia"))
    args = parser.parse_args()
    if not 9 <= args.min_zoom <= args.max_zoom <= 13:
        parser.error("Require 9 <= min-zoom <= max-zoom <= 13")

    # Existing pilot engine uses module-level BBOX/MED; retain Medellín control point
    # which falls inside both test regions. Avoid editing existing working pipeline.
    build.BBOX = REGIONS[args.region]
    sys.argv = [
        "medellin_terrain.py",
        "--output", str(args.output),
        "--min-zoom", str(args.min_zoom),
        "--max-zoom", str(args.max_zoom),
    ]
    build.main()
    output_mbtiles = args.output / "medellin-terrain-rgb.mbtiles"
    original_report = args.output / "medellin-terrain-report.json"
    report = json.loads(original_report.read_text())
    report["region"] = args.region
    report["edge_diagnostics"] = analyze_edges(output_mbtiles, args.min_zoom, args.max_zoom)
    (args.output / "antioquia-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print("EDGE DIAGNOSTICS", json.dumps(report["edge_diagnostics"], indent=2), flush=True)

if __name__ == "__main__":
    main()
