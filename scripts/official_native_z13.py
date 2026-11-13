#!/usr/bin/env python3
"""Compare native z13 pixel recovery for Tumaco and Malpelo using official IGAC.

No arbitrary heights, release, or modifications to the selected source CSV.
Requires a complete 32-shard prior land register. Official department polygons
are a geometric reference, NOT a complete certified coastline/island mask.
"""
import argparse
import json
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from shapely import contains_xy
from shapely.geometry import box
from shapely.ops import unary_union
from shapely.strtree import STRtree

from national_dem_coverage import local_cogs
from national_land_coverage import load_references
from national_tile_plan import parse_manifest
from official_territory_screen import (
    IGAC_SERVICE, get_igac_features, load_incomplete_rows, xyz_geometry,
)
from source_scope_comparison import (
    TARGET_COGS, compare_arrays, plan_candidates, render_valid,
)
from coastal_audit import index_sources

SITES = {"tumaco": "Copernicus_DSM_COG_10_N01_00_W080_00_DEM",
         "malpelo": "Copernicus_DSM_COG_10_N03_00_W082_00_DEM"}


def igac_tile_mask(geom_tree, polygon_shapes, tile, lon, lat):
    t = xyz_geometry(*tile)
    hits = [polygon_shapes[int(i)] for i in geom_tree.query(t)
            if polygon_shapes[int(i)].intersects(t)]
    if not hits:
        return np.zeros((256, 256), dtype=bool)
    local = unary_union([shape.intersection(t) for shape in hits])
    if local.is_empty:
        return np.zeros((256, 256), dtype=bool)
    return np.asarray(contains_xy(local, lon, lat), dtype=bool).reshape((256, 256))


def relevant_tiles(incomplete):
    """Only z13 incomplete XYZ whose current missing pixels hint at the COG."""
    matched = {}
    all_seen = set()
    for site, cog_name in SITES.items():
        tiles = sorted({
            (r["z"], r["x"], r["y"])
            for r in incomplete if r["z"] == 13
            and cog_name in r["unselected_public_cogs_at_missing_pixels"]
        })
        if not tiles:
            raise AssertionError(f"No z13 incomplete study cells for {site}")
        for tile in tiles:
            if tile in all_seen:
                raise AssertionError(f"Ambiguous source ownership for tile {tile}")
            all_seen.add(tile)
        matched[site] = tiles
    return matched


def scan(manifest, national, output):
    selected = parse_manifest(manifest)
    catalog = index_sources()
    augmented = plan_candidates(selected, catalog)
    rows, _, _, _ = load_incomplete_rows(national)
    grouped = relevant_tiles(rows)
    igac_shapes, _, igac_url, igac_class, failures = get_igac_features()
    if not igac_class.startswith("official_IGAC"):
        raise RuntimeError("Native z13 decision probe requires direct official IGAC source, not an unverified mirror")
    igac_tree = STRtree(igac_shapes)
    refs = load_references()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cache = output / "source-cache"
    cache.mkdir(exist_ok=True)
    opened = {}
    detail = []
    site_summary = {}
    try:
        for site, tiles in grouped.items():
            totals = Counter()
            for tile in tiles:
                before, original_heights = render_valid(selected, opened, cache, tile)
                after, augmented_heights = render_valid(augmented, opened, cache, tile)
                _, ne_mask, lon, lat = refs.masks(tile)
                igac_mask = igac_tile_mask(igac_tree, igac_shapes, tile, lon, lat)
                row = compare_arrays(before, original_heights, after, augmented_heights, igac_mask, ne_mask)
                recovered = row["recovered_pixel_reference_categories"]
                official_recovered = recovered["missing_both_land_references"] + recovered["missing_geoboundaries_only"]
                ne_only_recovered = recovered["missing_natural_earth_only"]
                row.update({
                    "site": site, "xyz": list(tile),
                    "tms_y": (1 << tile[0]) - 1 - tile[2],
                    "tested_unselected_COG": SITES[site],
                    "recovered_inside_IGAC_department_polygon": official_recovered,
                    "recovered_Natural_Earth_only": ne_only_recovered,
                    "original_missing_IGAC_department_pixels": int(np.count_nonzero(~before & igac_mask)),
                    "remaining_missing_IGAC_department_pixels": int(np.count_nonzero(~after & igac_mask)),
                    "IGAC_department_polygon_pixels": int(np.count_nonzero(igac_mask)),
                    "selected_source_count": 137,
                })
                for k in (
                    "before_missing_dem_pixels", "after_missing_dem_pixels",
                    "recovered_dem_pixels", "recovered_inside_IGAC_department_polygon",
                    "recovered_Natural_Earth_only",
                    "original_missing_IGAC_department_pixels",
                    "remaining_missing_IGAC_department_pixels",
                    "recovered_outside_both_references_unknown",
                ):
                    totals[k] += row[k]
                totals["tiles_tested"] += 1
                totals["tiles_with_recovery"] += int(row["recovered_dem_pixels"] > 0)
                detail.append(row)
                print(f"{site} {tile}: recovered {row['recovered_dem_pixels']}, "
                      f"inside_IGAC {official_recovered}, ne_only {ne_only_recovered}, "
                      f"still_missing_IGAC {row['remaining_missing_IGAC_department_pixels']}", flush=True)
            site_summary[site] = dict(totals)
    finally:
        for src in opened.values():
            src.close()
    if len(detail) != sum(len(v) for v in grouped.values()):
        raise AssertionError("Lost study XYZ during source comparison")
    if any(item["max_original_valid_height_difference_m"] > 0.001 for item in detail):
        raise AssertionError("Original DEM heights changed")
    report = {
        "status": "official_igac_z13_native_recovery_diagnostic",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "original_source_count": 137,
        "candidate_sources_tested_without_manifest_change": SITES,
        "source_land_reconciliation_run": 43490555676,
        "official_IGAC_geometry_url": igac_url,
        "official_IGAC_source_class": igac_class,
        "igac_service": IGAC_SERVICE,
        "z13_tile_count": len(detail),
        "site_summaries": site_summary,
        "per_tile_results": detail,
        "source_manifest_modified": False,
        "synthetic_height_values_inserted": 0,
        "national_publication_allowed": False,
        "limitations": [
            "IGAC departments are authoritative administrative regions but not verified high-precision coastal water/land polygons",
            "Natural Earth small islands may be absent from the IGAC departmental layer",
            "These are only z13 tiles with an existing incomplete-coverage catalog hint for either candidate",
            "The two extra original COGs were never added to the frozen 137-source manifest",
            "No residual NoData pixels were filled with artificial sea level or bathymetry",
            "DIMAR shoreline/island datasets must still be reviewed before full national source inclusion",
        ],
    }
    (output / "igac-native-z13-recovery.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "per_tile_results"},indent=2),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    parser.add_argument("--national",type=Path,default=Path("output/national-land"))
    parser.add_argument("--output",type=Path,default=Path("output/official-native-z13"))
    a=parser.parse_args()
    scan(a.manifest,a.national,a.output)


if __name__=="__main__":
    main()
