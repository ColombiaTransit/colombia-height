#!/usr/bin/env python3
"""Exact island-pixel native GLO-30 recovery with two temporary COG sources.

Only documented missing z13 pixel centers inside their actual OSMCoastline
polygon are counted. These are geographical data points, NOT legal territory
or an ocean mask. Selected 137 COGs unchanged; no MBTiles or ocean fill.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import numpy as np
from rasterio.warp import transform
from shapely import contains_xy
from shapely.geometry import Point
from shapely.ops import nearest_points

from coastal_audit import index_sources
from island_osm_native_scope import choose_island_polygons
from national_tile_plan import parse_manifest
from osm_land_reference import load_clip
from source_scope_comparison import render_valid

TARGETS = {
    "malpelo": ("Copernicus_DSM_COG_10_N03_00_W082_00_DEM", 97),
    "gorgona": ("Copernicus_DSM_COG_10_N03_00_W079_00_DEM", 86),
}
UNRESOLVED = ("santa_catalina", "gorgonilla")
EXPECTED_ISLAND_RUN = 43593099062
NODATA = -9999.0


def xyz_centers(tile):
    """Same pixel-center reference grid as existing national OSM audit."""
    z, x, y = tile
    bounds = mercantile.xy_bounds(x, y, z)
    xx = bounds.left + (np.arange(256) + .5) * (bounds.right - bounds.left) / 256
    yy = bounds.top - (np.arange(256) + .5) * (bounds.top - bounds.bottom) / 256
    mx, my = np.meshgrid(xx, yy)
    lon, lat = transform("EPSG:3857", "EPSG:4326", mx.ravel(), my.ravel())
    return np.asarray(lon).reshape((256, 256)), np.asarray(lat).reshape((256, 256))


def compare_exact_island_pixels(before_valid, before_heights, after_valid,
                                after_heights, island_mask, expected_missing):
    """No guessing recovery: compare exact native validity on same pixel centers."""
    arrays = [np.asarray(v) for v in
              (before_valid, before_heights, after_valid, after_heights, island_mask)]
    if any(v.shape != (256, 256) for v in arrays):
        raise ValueError("All native DEM and island masks must be 256x256")
    original, earlier, augmented, later, land = arrays
    original = original.astype(bool)
    augmented = augmented.astype(bool)
    land = land.astype(bool)
    if np.any(original & ~augmented):
        raise AssertionError("Original valid elevations were lost")
    common = original & augmented
    max_difference = (float(np.max(np.abs(earlier[common] - later[common])))
                      if np.any(common) else 0.)
    if not np.isfinite(max_difference) or max_difference > .001:
        raise AssertionError(f"Original valid heights changed by {max_difference}m")
    missing_on_island = land & ~original
    before = int(np.count_nonzero(missing_on_island))
    if before != expected_missing:
        raise AssertionError(f"Island polygon/native baseline mismatch: {before} != {expected_missing}")
    truly_recovered = land & ~original & augmented
    recovered = int(np.count_nonzero(truly_recovered))
    after = int(np.count_nonzero(land & ~augmented))
    if before != recovered + after:
        raise AssertionError("Missing island pixels do not reconcile")
    recovered_values = later[truly_recovered]
    if np.any(~np.isfinite(recovered_values)) or np.any(recovered_values == NODATA):
        raise AssertionError("Reported native recovered values include NoData or nonfinite values")
    return {
        "OSM_island_native_missing_before": before,
        "OSM_island_native_recovered_with_real_COG": recovered,
        "OSM_island_native_still_missing_after": after,
        "island_pixel_centers": int(np.count_nonzero(land)),
        "native_heights_unchanged_max_abs_m": max_difference,
        "real_recovered_height_min_m": (float(recovered_values.min()) if recovered else None),
        "real_recovered_height_max_m": (float(recovered_values.max()) if recovered else None),
        "original_native_height_values_preserved": True,
        "no_synthetic_pixels_added": True,
    }


def shortlist_unresolved_polygon_leads(polygons, probes, island_geometries,
                                       radius_degrees=.04, maximum=5):
    """Rank nearest *real* OSM polygon pieces as review leads; no buffer is land.

    Exclude large mainland pieces and polygons containing known named island
    probes (such as nearby Providencia/Gorgona) so those aren't confused for
    Santa Catalina/Gorgonilla. Distance in degrees is a discovery hint only.
    """
    if not 0 < radius_degrees <= .08:
        raise ValueError("Unsafe island search radius")
    named_points = [Point(float(p["lon"]), float(p["lat"])) for p in probes
                    if p["id"] in ("gorgona", "providencia", "san_andres", "malpelo")]
    results = {}
    for p in probes:
        if p["id"] not in UNRESOLVED:
            continue
        pt = Point(float(p["lon"]), float(p["lat"]))
        leads = []
        for geom in polygons:
            if geom.is_empty or geom.area > .01:
                continue
            if any(geom.covers(k) for k in named_points):
                continue
            distance = float(geom.distance(pt))
            if not 0 < distance <= radius_degrees:
                continue
            near_pt = nearest_points(pt, geom)[1]
            leads.append({
                "probe_distance_degrees_context_only": round(distance, 9),
                "geometry_bounds": [round(v, 9) for v in geom.bounds],
                "nearest_OSM_polygon_point_lonlat": [
                    round(float(near_pt.x), 9), round(float(near_pt.y), 9)],
                "area_square_degrees": float(geom.area),
                "identity_unverified": True,
                "not_automatically_assigned_to_island": True,
            })
        leads.sort(key=lambda l: (l["probe_distance_degrees_context_only"],
                                  l["area_square_degrees"]))
        results[p["id"]] = {
            "status": "review_nearby_nonmatching_OSM_polygons_only",
            "original_probe_lonlat": [float(p["lon"]), float(p["lat"])],
            "max_search_distance_degrees": radius_degrees,
            "nearby_polygon_leads": leads[:maximum],
            "no_polygon_or_probe_automatically_accepted": True,
            "manual_geographic_identity_review_required": True,
        }
    if set(results) != set(UNRESOLVED):
        raise AssertionError("Unresolved island probe registry incomplete")
    return results


def run(manifest, osm_path, osm_metadata, island_report, probes_path, output):
    sources = parse_manifest(manifest)
    if len(sources) != 137 or any(
        name in {s["name"] for s in sources} for name, _ in TARGETS.values()
    ):
        raise AssertionError("The native 137-source baseline must remain unmodified")
    old = json.loads(Path(island_report).read_text())
    meta = json.loads(Path(osm_metadata).read_text())
    probes = json.loads(Path(probes_path).read_text())["locations"]
    if (old.get("selected_COG_count_unchanged") != 137
            or old.get("named_island_probes_checked") != 6
            or old.get("COGs_promoted") != 0
            or old.get("national_publication_allowed") is not False
            or meta.get("national_publication_allowed") is not False):
        raise AssertionError("Frozen exact island audit or OSM metadata failed verification")
    polygons = load_clip(osm_path, meta["reference_wkb_sha256"])
    names = choose_island_polygons(polygons, probes)
    catalog = {row["name"]: row for row in index_sources().values()}
    all_details = []
    site_summaries = {}
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    cache = output.parent / "native-source-cache"
    cache.mkdir(exist_ok=True)
    opened = {}
    try:
        for site, (target, expected) in TARGETS.items():
            record = names[site]
            previous = old["islands"][site]
            if (record["geometry"] is None
                    or previous.get("missing_native_island_pixels") != expected
                    or previous.get("source_candidate_hits", {}).get(target) != expected):
                raise AssertionError(f"{site}: the original {expected} exact land gaps were not verified")
            candidate = catalog.get(target)
            if not candidate:
                raise AssertionError(f"Missing public Copernicus source: {target}")
            extra = {
                "name": target, "latitude": str(candidate["latitude"]),
                "longitude": str(candidate["longitude"]), "url": candidate["url"],
                "status": "investigation_only_not_selected",
            }
            augmented = sources + [extra]
            old_tiles = [row for row in old["per_tile"] if row["island"] == site]
            if not old_tiles or len(old_tiles) != previous["z13_tiles"]:
                raise AssertionError(f"{site}: previous island tile coverage incomplete")
            summary = {
                "source": target, "z13_tiles": len(old_tiles),
                "OSM_island_native_missing_before": 0,
                "OSM_island_native_recovered_with_real_COG": 0,
                "OSM_island_native_still_missing_after": 0,
                "native_heights_unchanged_max_abs_m": 0.,
            }
            for prev in old_tiles:
                tile = tuple(prev["zxy"])
                if len(tile) != 3 or tile[0] != 13:
                    raise AssertionError("Expected original z13 island pixels")
                lon, lat = xyz_centers(tile)
                island_mask = np.asarray(
                    contains_xy(record["geometry"], lon.ravel(), lat.ravel()),
                    dtype=bool).reshape((256, 256))
                original_valid, original_height = render_valid(sources, opened, cache, tile)
                after_valid, after_height = render_valid(augmented, opened, cache, tile)
                result = compare_exact_island_pixels(
                    original_valid, original_height, after_valid, after_height,
                    island_mask, prev["missing_native_island_pixels"])
                if result["island_pixel_centers"] != prev["OSM_island_pixels"]:
                    raise AssertionError(f"OSM polygon changed since prior island run: {site}")
                for key in (
                    "OSM_island_native_missing_before",
                    "OSM_island_native_recovered_with_real_COG",
                    "OSM_island_native_still_missing_after",
                ):
                    summary[key] += result[key]
                summary["native_heights_unchanged_max_abs_m"] = max(
                    summary["native_heights_unchanged_max_abs_m"],
                    result["native_heights_unchanged_max_abs_m"])
                all_details.append({"island": site, "zxy": list(tile), **result})
            if summary["OSM_island_native_missing_before"] != expected:
                raise AssertionError(f"{site}: total missing native height drift")
            summary["original_island_pixels_reconciled"] = True
            summary["all_new_heights_native_Copernicus"] = True
            summary["source_permanently_selected"] = False
            site_summaries[site] = summary
    finally:
        for src in opened.values():
            src.close()
    leads = shortlist_unresolved_polygon_leads(polygons, probes, names)
    result = {
        "status": "exact_OSM_island_native_Copernicus_recovery_test",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_exact_island_audit_run": EXPECTED_ISLAND_RUN,
        "osm_land_polygon_sha256": meta["reference_wkb_sha256"],
        "original_selected_source_COG_count": 137,
        "additional_COGs_tested_in_memory_only": {k: v[0] for k, v in TARGETS.items()},
        "island_native_recovery": site_summaries,
        "original_island_gaps": {k: v[1] for k, v in TARGETS.items()},
        "unresolved_island_polygon_leads": leads,
        "per_tile_native_recovery": all_details,
        "quitasueno_excluded": True,
        "osm_not_certified_Colombian_jurisdiction": True,
        "no_source_promoted_to_manifest": True,
        "no_synthetic_ocean_or_dem_values": True,
        "national_publication_allowed": False,
        "osm_attribution": meta["odbl_attribution"],
    }
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "per_tile_native_recovery"},
                     indent=2, ensure_ascii=False), flush=True)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, default=Path("output/colombia_dem_manifest_extended.csv"))
    ap.add_argument("--osm", type=Path, default=Path("output/osm-reference/osm-land-study.wkb.gz"))
    ap.add_argument("--osm-meta", type=Path, default=Path("output/osm-reference/osm-land-study-metadata.json"))
    ap.add_argument("--island-report", type=Path, default=Path("output/island-previous/native-island-polygon-qa.json"))
    ap.add_argument("--probes", type=Path, default=Path("data/colombia-island-probes.json"))
    ap.add_argument("--output", type=Path, default=Path("output/island-native-recovery/island-native-recovery.json"))
    args = ap.parse_args()
    run(args.manifest, args.osm, args.osm_meta, args.island_report, args.probes, args.output)


if __name__ == "__main__":
    main()
