#!/usr/bin/env python3
"""One-off low-zoom OSM land-mask diagnostic using the already staged sources.

Only z0–z8 candidate XYZ masks are inspected. Reuses 140-source manifest and
OSM WKB / country relation; NO native raster downloads or new source audits.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from generate_osm_land_only_terrain import (
    load_osm_coastline_land, load_osm_country, prepare_plan,
    require_verified_staging,
)
from national_tile_plan import candidate_tiles, parse_manifest


def assess(manifest, osm_clip, osm_meta, country_file, output,
           minzoom=0, maxzoom=8):
    if not 0 <= minzoom <= maxzoom <= 8:
        raise ValueError("Only low zoom 0-8 diagnostic permitted")
    sources = parse_manifest(manifest)
    require_verified_staging(sources)
    physical, meta = load_osm_coastline_land(osm_clip, osm_meta)
    country = load_osm_country(country_file)
    overall = Counter()
    by_zoom = {}
    blockers = []
    for z in range(minzoom, maxzoom + 1):
        tiles = [(z, x, y) for x, y in sorted(candidate_tiles(sources, z))]
        statuses, rows = prepare_plan(
            tiles, physical, country, include_physical=True)
        by_zoom[str(z)] = {
            "candidate_tiles": len(tiles),
            "classifications": dict(statuses),
            "foreign_land_mixed_examples": [
                {"xyz": list(row["tile"]),
                 "colombian_land_pixels": row["land_pixels"],
                 "outside_country_physical_land_pixels":
                     int((row["physical_mask"] & ~row["mask"]).sum())}
                for row in rows
                if (row["physical_mask"] & ~row["mask"]).any()
            ][:12],
        }
        overall.update({
            key: n for key, n in statuses.items()
            if key != "mixed_foreign_physical_OSM_land_blocked"
        })
        for row in rows:
            if row["status"] != "skip_no_physical_OSM_Colombia_land":
                if (row["physical_mask"] & ~row["mask"]).any():
                    blockers.append({
                        "xyz": list(row["tile"]),
                        "foreign_physical_land_pixels":
                            int((row["physical_mask"] & ~row["mask"]).sum())})
        print(f"OSM zoom {z} candidate tiles {len(tiles)} mask classes {dict(statuses)}", flush=True)
    result = {
        "schema": "colombia-lowzoom-real-OSM-mask-diagnostic-v1",
        "sources": len(sources),
        "zoom_range": [minzoom, maxzoom],
        "physical_OSM_SHA256": meta["reference_wkb_sha256"],
        "OSM_colombia_relation": 120027,
        "candidate_counts": dict(overall),
        "by_zoom": by_zoom,
        "foreign_physical_land_overlap_tiles": len(blockers),
        "foreign_physical_land_overlap_examples": blockers[:30],
        "native_COG_downloaded": False,
        "national_release_authorized": False,
    }
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "lowzoom_status": "diagnostic_complete_not_native_MBtiles",
        "foreign_overlap_tiles": len(blockers),
        "source_count": len(sources),
        "zoom_totals": {z: v["candidate_tiles"] for z, v in by_zoom.items()},
    }, indent=2))
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--osm-land-clip", type=Path, required=True)
    p.add_argument("--osm-land-meta", type=Path, required=True)
    p.add_argument("--osm-country-geojson", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--maxzoom", type=int, default=8)
    args = p.parse_args()
    assess(args.manifest,args.osm_land_clip,args.osm_land_meta,
           args.osm_country_geojson,args.output,maxzoom=args.maxzoom)
