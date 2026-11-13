#!/usr/bin/env python3
"""Conservative land-reference audit of Colombia DEM coverage, never a water mask.

A DEM pixel is never filled or re-encoded here. Two independent reference
datasets (geoBoundaries COL ADM0 and Natural Earth 10m land + minor islands)
are compared separately; agreement is evidence, not official jurisdiction.
"""
import argparse
import gzip
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import numpy as np
from rasterio.warp import transform
from shapely import contains_xy
from shapely.geometry import box, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from inventory import BOUNDARY_URL, get_json
from extend_inventory import NE_SOURCES, ne_shapes
from coastal_audit import index_sources
from national_tile_plan import candidate_tiles, parse_manifest
from national_dem_coverage import (
    PIXELS, assess_tile, geographical_owner, intersecting_source_indices,
    local_cogs,
)
from two_cog_seam_pilot import warp_sources

# Center points choose study windows only; not certified shoreline positions.
SITES = {
    "tumaco": (-78.76, 1.81),
    "san_andres": (-81.70, 12.57),
    "providencia": (-81.37, 13.35),
    "malpelo": (-81.606, 4.005),
}
REFERENCE_DESCRIPTION = (
    "geoBoundaries COL ADM0 and Natural Earth 10m land + minor islands: "
    "non-authoritative land-reference comparison"
)
CATEGORIES = (
    "missing_both_land_references",
    "missing_geoboundaries_only",
    "missing_natural_earth_only",
    "missing_outside_both_references",
)


def site_tiles(zoom=11):
    """Four separate 3x3 neighborhoods; preserve site provenance."""
    if zoom != 11:
        raise ValueError("Pilot sampling is explicitly fixed at zoom 11")
    output = []
    seen = set()
    for name, (lon, lat) in SITES.items():
        center = mercantile.tile(lon, lat, zoom)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                key = (zoom, center.x + dx, center.y + dy)
                if key not in seen:
                    output.append((name, key))
                    seen.add(key)
    return output


def missing_categories(valid, gb, ne):
    """Exhaustive disjoint classification. Outside references is NOT ocean."""
    valid = np.asarray(valid, dtype=bool)
    gb = np.asarray(gb, dtype=bool)
    ne = np.asarray(ne, dtype=bool)
    if valid.shape != (256, 256) or gb.shape != valid.shape or ne.shape != valid.shape:
        raise ValueError("Expected three aligned 256x256 masks")
    missing = ~valid
    stats = {
        "missing_both_land_references": int(np.count_nonzero(missing & gb & ne)),
        "missing_geoboundaries_only": int(np.count_nonzero(missing & gb & ~ne)),
        "missing_natural_earth_only": int(np.count_nonzero(missing & ~gb & ne)),
        "missing_outside_both_references": int(np.count_nonzero(missing & ~gb & ~ne)),
        "reference_geoboundaries_land_pixels": int(np.count_nonzero(gb)),
        "reference_natural_earth_land_pixels": int(np.count_nonzero(ne)),
        "reference_land_agreement_pixels": int(np.count_nonzero(gb & ne)),
    }
    if sum(stats[key] for key in CATEGORIES) != int(missing.sum()):
        raise AssertionError("Land-reference mask partition does not reconcile")
    return stats


class References:
    def __init__(self, gb_geometry, ne_geometries, gb_url, gb_license):
        if gb_geometry.is_empty or not ne_geometries:
            raise ValueError("Missing land-reference geometry")
        self.gb = gb_geometry
        self.ne = ne_geometries
        self.index = STRtree(self.ne)
        self.url = gb_url
        self.license = gb_license

    def masks(self, tile):
        z, x, y = tile
        bounds = mercantile.bounds(x, y, z)
        bb = mercantile.xy_bounds(x, y, z)
        px = bb.left + (np.arange(256) + .5) * (bb.right - bb.left) / 256
        py = bb.top - (np.arange(256) + .5) * (bb.top - bb.bottom) / 256
        xx, yy = np.meshgrid(px, py)
        lon, lat = transform("EPSG:3857", "EPSG:4326", xx.ravel(), yy.ravel())
        geo = np.asarray(contains_xy(self.gb, lon, lat), dtype=bool).reshape((256, 256))
        # Spatially index minor islands and land polygons rather than joining
        # unrelated worldwide Natural Earth polygons for every national tile.
        matches = self.index.query(box(bounds.west, bounds.south, bounds.east, bounds.north))
        ne_local = unary_union([self.ne[int(i)] for i in matches]) if len(matches) else None
        if ne_local is None or ne_local.is_empty:
            natural = np.zeros((256, 256), dtype=bool)
        else:
            natural = np.asarray(contains_xy(ne_local, lon, lat), dtype=bool).reshape((256, 256))
        return geo, natural, np.asarray(lon).reshape((256, 256)), np.asarray(lat).reshape((256, 256))


def load_references():
    metadata = get_json(BOUNDARY_URL)
    url = metadata["gjDownloadURL"]
    gj = get_json(url)
    features = gj.get("features") or []
    if not features:
        raise RuntimeError("Missing Colombia geoBoundaries geometry")
    geo = unary_union([shape(f["geometry"]) for f in features])
    ne = ne_shapes(NE_SOURCES["ne_10m_land"])
    ne.extend(ne_shapes(NE_SOURCES["ne_10m_minor_islands"]))
    return References(geo, ne, url, metadata.get("boundaryLicense"))


def catalog_candidates(missing, lon, lat, catalog, selected_cells, zoom):
    """Identify *unselected* public COG cells, without downloading them.

    Only enumerate at z>=9: at low zoom a tile may cover many continents;
    the absence of those distant cells is not a coastal source diagnosis.
    """
    if zoom < 9 or not np.any(missing):
        return []
    y_cells = np.floor(lat[missing]).astype(int)
    x_cells = np.floor(lon[missing]).astype(int)
    cells = set(zip(y_cells.tolist(), x_cells.tolist()))
    return sorted({
        catalog[cell]["name"]
        for cell in cells if cell not in selected_cells and cell in catalog
    })


def inspect(sources, opened, cache, references, catalog, selected_cells,
            tile, site=None, include_full=False):
    z, x, y = tile
    result, names, source_count = assess_tile(sources, opened, cache, tile)
    if result["coverage"] == "full_dem_coverage" and not include_full:
        return None, result["coverage"]
    indices = intersecting_source_indices(sources, z, x, y)
    native = local_cogs(sources, indices, cache, opened) if indices else []
    if native:
        heights, provenance, _, _ = warp_sources(native, tile)
        valid = (provenance > 0) & np.isfinite(heights) & (heights != -9999.)
    else:
        valid = np.zeros((256, 256), dtype=bool)
    if PIXELS - int(valid.sum()) != result["missing_pixels"]:
        raise AssertionError(f"Native DEM mask changed within tile {tile}")
    gb, ne, lon, lat = references.masks(tile)
    counts = missing_categories(valid, gb, ne)
    missing = ~valid
    outside_source_cell = np.zeros((256, 256), dtype=bool)
    if np.any(missing):
        # Integer-degree selection is a diagnostic, not a native COG mask.
        for cell in set(zip(np.floor(lat[missing]).astype(int).tolist(),
                            np.floor(lon[missing]).astype(int).tolist())):
            if cell not in selected_cells:
                outside_source_cell |= (np.floor(lat) == cell[0]) & (np.floor(lon) == cell[1])
    extra = catalog_candidates(missing, lon, lat, catalog, selected_cells, z)
    row = {
        "z": z, "x": x, "y": y, "tms_y": (1 << z) - 1 - y,
        "site": site,
        "dem_coverage": result["coverage"],
        "valid_dem_pixels": result["valid_pixels"],
        "missing_dem_pixels": result["missing_pixels"],
        "selected_source_cogs": names,
        "missing_outside_selected_degree_cells": int(np.count_nonzero(missing & outside_source_cell)),
        "unselected_public_cogs_at_missing_pixels": extra,
        **counts,
        "requires_review": bool(
            counts["missing_both_land_references"]
            or counts["missing_geoboundaries_only"]
            or counts["missing_natural_earth_only"]
            or extra
        ),
    }
    return row, result["coverage"]


def scan(manifest, output, mode="pilot", shard=None):
    if mode not in ("pilot", "full"):
        raise ValueError("Unknown mode")
    if mode == "full" and (shard is None or not 0 <= shard < 32):
        raise ValueError("Full scan requires a shard in 0..31")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    sources = parse_manifest(manifest)
    if len(sources) != 137:
        raise AssertionError("Source inventory changed from 137; review before scanning")
    references = load_references()
    catalog = index_sources()
    selected_cells = {(int(s["latitude"]), int(s["longitude"])) for s in sources}
    if mode == "pilot":
        todo = site_tiles()
    else:
        todo = ((None, (z, x, y))
                for z in range(14)
                for x, y in sorted(candidate_tiles(sources, z))
                if geographical_owner(z, x, y) == shard)
    rows = output / ("land-pilot-tiles.ndjson.gz" if mode == "pilot"
                     else f"land-shard-{shard:02d}.ndjson.gz")
    report_path = output / ("land-pilot-summary.json" if mode == "pilot"
                            else f"land-summary-{shard:02d}.json")
    opened = {}
    total = 0
    dem_status = Counter()
    missing_stats = Counter()
    sites = {}
    review_count = 0
    omitted = set()
    try:
        with gzip.open(rows, "wt", encoding="utf-8", compresslevel=6) as stream:
            for site, tile in todo:
                total += 1
                record, status = inspect(
                    sources, opened, output / "source-cache", references,
                    catalog, selected_cells, tile, site=site,
                    include_full=(mode == "pilot"))
                dem_status[status] += 1
                if record is None:
                    continue
                if mode == "pilot":
                    site_summary = sites.setdefault(site, {
                        "tiles_checked": 0, "missing_dem_pixels": 0,
                        "missing_reference_land_pixels": 0,
                        "tiles_with_reference_land": 0,
                    })
                    site_summary["tiles_checked"] += 1
                    site_summary["missing_dem_pixels"] += record["missing_dem_pixels"]
                    site_summary["missing_reference_land_pixels"] += sum(
                        record[k] for k in CATEGORIES[:3])
                    site_summary["tiles_with_reference_land"] += int(
                        bool(record["reference_geoboundaries_land_pixels"]
                             or record["reference_natural_earth_land_pixels"]))
                for key in CATEGORIES:
                    missing_stats[key] += record[key]
                review_count += int(record["requires_review"])
                omitted.update(record["unselected_public_cogs_at_missing_pixels"])
                stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
                if total % 1000 == 0:
                    print(f"{mode} shard={shard}: {total} checked", flush=True)
    finally:
        for src in opened.values():
            src.close()
    if mode == "pilot":
        if set(sites) != set(SITES) or any(v["tiles_checked"] != 9 for v in sites.values()):
            raise AssertionError("Pilot did not process 9 tiles at each of four sites")
    if sum(dem_status.values()) != total:
        raise AssertionError("DEM coverage candidate accounting mismatch")
    summary = {
        "status": "provisional_land_reference_audit",
        "mode": mode, "shard": shard,
        "source_cog_count": len(sources), "tiles_checked": total,
        "dem_coverage_counts": dict(dem_status),
        "missing_pixel_reference_categories": dict(missing_stats),
        "tiles_requiring_review": review_count,
        "unselected_public_cogs_at_missing_pixels": sorted(omitted),
        "pilot_sites": sites if mode == "pilot" else None,
        "geoBoundaries_url": references.url,
        "geoBoundaries_license": references.license,
        "natural_earth_urls": NE_SOURCES,
        "all_missing_pixels_classified_as_water": False,
        "complete": mode == "full",
        "national_publication_allowed": False,
        "limitations": [
            "Both land references are non-authoritative for Colombian maritime or island jurisdiction",
            "Outside both references does NOT prove ocean or permission to fabricate sea-level pixels",
            "Unselected public COGs are only candidates and are NOT added to the verified 137-source inventory",
            "Only exact native Copernicus DEM pixels are counted; none are filled or encoded",
            "Pilot checks 9 zoom-11 tiles at each site; full mode covers the existing 137-source national candidate set",
        ],
    }
    report_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return summary


def reconcile(root, output):
    summaries = sorted(Path(root).glob("land-summary-*.json"))
    files = sorted(Path(root).glob("land-shard-*.ndjson.gz"))
    if len(summaries) != 32 or len(files) != 32:
        raise AssertionError(f"Require exactly 32 full land shards: {len(summaries)}, {len(files)}")
    coverage = Counter()
    categories = Counter()
    seen = set()
    outside_sources = set()
    total = 0
    review = 0
    for shard in range(32):
        summary = json.loads((Path(root) / f"land-summary-{shard:02d}.json").read_text())
        if summary["mode"] != "full" or summary["shard"] != shard or not summary["complete"]:
            raise AssertionError(f"Invalid or partial shard {shard}")
        if summary["source_cog_count"] != 137:
            raise AssertionError("Changed source inventory")
        total += summary["tiles_checked"]
        coverage.update(summary["dem_coverage_counts"])
        review += summary["tiles_requiring_review"]
        outside_sources.update(summary["unselected_public_cogs_at_missing_pixels"])
        with gzip.open(Path(root) / f"land-shard-{shard:02d}.ndjson.gz", "rt", encoding="utf-8") as stream:
            local = Counter()
            for line in stream:
                row = json.loads(line)
                tile = (row["z"], row["x"], row["y"])
                if tile in seen or geographical_owner(*tile) != shard:
                    raise AssertionError(f"Duplicate or wrongly assigned XYZ {tile}")
                seen.add(tile)
                if row["dem_coverage"] == "full_dem_coverage":
                    raise AssertionError("Full-DEM tile should not enter partial land register")
                if sum(row[k] for k in CATEGORIES) != row["missing_dem_pixels"]:
                    raise AssertionError(f"Incomplete per-tile partition {tile}")
                local.update({key: row[key] for key in CATEGORIES})
        expected = summary["missing_pixel_reference_categories"]
        if any(local[key] != expected.get(key, 0) for key in CATEGORIES):
            raise AssertionError(f"Shard {shard} pixel totals mismatch")
        categories.update(local)
    if total != 96751 or coverage["partial_dem_coverage"] != 3778 or coverage["full_dem_coverage"] != 92973:
        raise AssertionError(f"Changed national coverage baseline: {total} {dict(coverage)}")
    if len(seen) != coverage["partial_dem_coverage"] + coverage["no_dem_coverage"]:
        raise AssertionError("Missing, duplicated, or unrecorded incomplete tile")
    report = {
        "status": "national_provisional_land_reference_reconciled",
        "checked_candidate_tiles": total, "classified_incomplete_tiles": len(seen),
        "coverage_counts": dict(coverage),
        "missing_pixel_reference_categories": dict(categories),
        "tiles_requiring_review": review,
        "unselected_public_cogs_at_missing_pixels": sorted(outside_sources),
        "all_32_shards_present": True, "unique_partial_xyz": True,
        "national_publication_allowed": False,
        "note": "The categories are agreement/disagreement of two NON-AUTHORITATIVE references, not a legal water mask.",
    }
    Path(output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("output/colombia_dem_manifest_extended.csv"))
    parser.add_argument("--output", type=Path, default=Path("output/national-land"))
    parser.add_argument("--mode", choices=("pilot", "full"), default="pilot")
    parser.add_argument("--shard", type=int)
    parser.add_argument("--reconcile", action="store_true")
    args = parser.parse_args()
    if args.reconcile:
        reconcile(args.output, args.output / "national-land-reference-summary.json")
    else:
        scan(args.manifest, args.output, mode=args.mode, shard=args.shard)


if __name__ == "__main__":
    main()
