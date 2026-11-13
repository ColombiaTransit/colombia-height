#!/usr/bin/env python3
"""Compare two *unselected* Copernicus COGs against the frozen 137-source baseline.

This is a controlled read-only diagnostic, NOT a manifest change, sea mask,
Terrain-RGB generator, or authorization for national release. Every pixel
uses the original native DEM and the same per-XYZ reprojection grid.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from coastal_audit import index_sources
from national_dem_coverage import intersecting_source_indices, local_cogs
from national_land_coverage import (
    CATEGORIES, References, load_references, missing_categories, site_tiles,
)
from national_tile_plan import parse_manifest
from two_cog_seam_pilot import warp_sources

TARGET_COGS = {
    "tumaco": "Copernicus_DSM_COG_10_N01_00_W080_00_DEM",
    "malpelo": "Copernicus_DSM_COG_10_N03_00_W082_00_DEM",
}
NODATA = -9999.0
SIZE = (256, 256)


def plan_candidates(selected, catalog):
    """Build an ephemeral augmented inventory; never modify input manifest."""
    if len(selected) != 137:
        raise AssertionError(f"Frozen study inventory should have 137 COGs, got {len(selected)}")
    by_name = {item["name"]: item for item in catalog.values()}
    chosen = set(s["name"] for s in selected)
    augmented = list(selected)
    for site, name in TARGET_COGS.items():
        if name in chosen:
            raise AssertionError(f"Already selected: {name}; adjust investigation first")
        if name not in by_name:
            raise AssertionError(f"Public Copernicus catalog no longer lists {name}")
        item = by_name[name]
        augmented.append({
            "name": item["name"], "latitude": str(item["latitude"]),
            "longitude": str(item["longitude"]), "url": item["url"],
            "status": "investigation_only_not_selected",
        })
    return augmented


def render_valid(sources, opened, cache, tile):
    """Return native-pixel validity and real height, no artificial water fill."""
    z, x, y = tile
    idx = intersecting_source_indices(sources, z, x, y)
    if not idx:
        return np.zeros(SIZE, dtype=bool), np.full(SIZE, NODATA, dtype=np.float32)
    cogs = local_cogs(sources, idx, cache, opened)
    height, provenance, _, _ = warp_sources(cogs, tile)
    valid = (provenance > 0) & np.isfinite(height) & (height != NODATA)
    return valid, height


def compare_arrays(before_valid, before_height, after_valid, after_height, gb, ne):
    """Compare identical 256-pixel grids; retain earlier valid heights exactly."""
    masks = (before_valid, after_valid, gb, ne)
    if any(np.asarray(mask).shape != SIZE for mask in masks):
        raise ValueError("Expected same 256x256 grid")
    before_valid, after_valid, gb, ne = [np.asarray(a, dtype=bool) for a in masks]
    before_height = np.asarray(before_height)
    after_height = np.asarray(after_height)
    if before_height.shape != SIZE or after_height.shape != SIZE:
        raise ValueError("Height mask grids differ")
    lost = before_valid & ~after_valid
    if np.any(lost):
        raise AssertionError("Adding an independent COG removed earlier valid DEM pixels")
    carried = before_valid & after_valid
    existing_difference = (float(np.max(np.abs(before_height[carried]-after_height[carried])))
                           if np.any(carried) else 0.0)
    if not np.isfinite(existing_difference) or existing_difference > 0.001:
        raise AssertionError(f"Existing valid DEM heights changed by {existing_difference:.4f}m")
    regained = after_valid & ~before_valid
    recovered = missing_categories(~regained, gb, ne)
    before_stats = missing_categories(before_valid, gb, ne)
    after_stats = missing_categories(after_valid, gb, ne)
    for key in CATEGORIES:
        if before_stats[key]-after_stats[key] != recovered[key]:
            raise AssertionError(f"DEM recovery partition mismatch {key}")
    n = int(np.count_nonzero(regained))
    if n != sum(recovered[key] for key in CATEGORIES):
        raise AssertionError("Incomplete recovered pixel partition")
    return {
        "before_missing_dem_pixels": int(np.count_nonzero(~before_valid)),
        "after_missing_dem_pixels": int(np.count_nonzero(~after_valid)),
        "recovered_dem_pixels": n,
        "recovered_reference_land_pixels": int(sum(recovered[key] for key in CATEGORIES[:3])),
        "recovered_outside_both_references_unknown": int(recovered[CATEGORIES[3]]),
        "recovered_pixel_reference_categories": {key: recovered[key] for key in CATEGORIES},
        "remaining_missing_reference_land_pixels": int(sum(after_stats[key] for key in CATEGORIES[:3])),
        "remaining_missing_outside_both_references_unknown": int(after_stats[CATEGORIES[3]]),
        "max_original_valid_height_difference_m": round(existing_difference, 6),
        "no_artificial_dem_pixels": True,
    }


def run(manifest, output):
    sources = parse_manifest(manifest)
    catalog = index_sources()
    augmented = plan_candidates(sources, catalog)
    references = load_references()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cache = output / "source-cache"
    cache.mkdir(exist_ok=True)
    original_count = len(sources)
    opened = {}
    site_counts = {}
    details = []
    try:
        for site, tile in site_tiles():
            if site not in TARGET_COGS:
                continue
            first, orig = render_valid(sources, opened, cache, tile)
            # Original indices are unchanged. Extras are appended in memory
            # and given priority only at pixels missing from existing COGs.
            after, height = render_valid(augmented, opened, cache, tile)
            gb, ne, _, _ = references.masks(tile)
            result = compare_arrays(first, orig, after, height, gb, ne)
            result.update({
                "site": site, "xyz": list(tile),
                "tms_y": (1 << tile[0])-1-tile[2],
                "tested_extra_cog": TARGET_COGS[site],
                "baseline_source_cogs": original_count,
                "ephemeral_extra_sources": len(TARGET_COGS),
            })
            details.append(result)
            totals = site_counts.setdefault(site, Counter())
            for key in (
                "before_missing_dem_pixels", "after_missing_dem_pixels",
                "recovered_dem_pixels", "recovered_reference_land_pixels",
                "recovered_outside_both_references_unknown",
                "remaining_missing_reference_land_pixels",
                "remaining_missing_outside_both_references_unknown",
            ):
                totals[key] += result[key]
            totals["tiles_tested"] += 1
            totals["tiles_with_recovered_pixels"] += int(result["recovered_dem_pixels"] > 0)
            print(f"{site} {tile}: recovered={result['recovered_dem_pixels']} "
                  f"land-ref={result['recovered_reference_land_pixels']} "
                  f"remaining-land-ref={result['remaining_missing_reference_land_pixels']}", flush=True)
    finally:
        for src in opened.values():
            src.close()
    if len(details) != 18 or any(site_counts[s]["tiles_tested"] != 9 for s in TARGET_COGS):
        raise AssertionError("Expected 9 consecutive z11 XYZ tiles per target site")
    if sum(s["recovered_dem_pixels"] for s in site_counts.values()) == 0:
        raise AssertionError("Neither extra source supplied any real DEM pixels; investigate")
    report = {
        "status": "two_unselected_cog_gap_comparison",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_source_cog_count": 137,
        "extra_cogs_in_temporary_comparison_only": TARGET_COGS,
        "zoom": 11, "tiles_checked": len(details),
        "site_summaries": {name: dict(items) for name, items in site_counts.items()},
        "tile_records": details,
        "geoBoundaries_url": references.url,
        "geoBoundaries_license": references.license,
        "recovery_is_native_dem_only": True,
        "baseline_manifest_modified": False,
        "national_publication_allowed": False,
        "limitations": [
            "Potential islands/territory are not certified by either reference polygon",
            "Recovered missing heights are native source pixels, not inferred water zeros",
            "The extra COGs remain outside the approved 137-source selection",
            "Even real recovered pixels outside both references are UNKNOWN as land/water",
            "This checks 18 z11 tiles at two sites, not national coasts or COG edges",
        ],
    }
    target = output / "unselected-cog-gap-comparison.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "tile_records"}, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("output/colombia_dem_manifest_extended.csv"))
    parser.add_argument("--output", type=Path, default=Path("output/source-scope-comparison"))
    args = parser.parse_args()
    run(args.manifest, args.output)


if __name__ == "__main__":
    main()
