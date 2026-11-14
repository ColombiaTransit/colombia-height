#!/usr/bin/env python3
"""Compare real, native Copernicus DEM NoData pixels with detailed OSM land.

Read-only pilot and national z13 audit. OSMCoastline is a non-official
coastline *land reference*, not a Colombian legal border or a permission
to fill NoData. The original 137-COG selected manifest is unchanged.
"""
import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from shapely import contains_xy
from shapely.geometry import box, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree

from national_land_coverage import (
    load_references, site_tiles,
)
from official_territory_screen import (
    IGAC_SERVICE, cell_geometry, get_service_features,
    load_incomplete_rows, xyz_geometry,
)
from osm_land_reference import load_clip, STUDY_BBOX
from national_tile_plan import parse_manifest
from national_dem_coverage import (
    intersecting_source_indices, local_cogs,
)
from two_cog_seam_pilot import warp_sources


class PolygonMask:
    """Rasterize local polygon union using exact 256x256 XYZ pixel centers."""
    def __init__(self, polygons):
        self.polygons = list(polygons)
        if not self.polygons or any(x.is_empty for x in self.polygons):
            raise ValueError("Empty polygon reference")
        self.tree = STRtree(self.polygons)

    def mask(self, tile, lon, lat):
        if lon.shape != (256, 256) or lat.shape != (256, 256):
            raise ValueError("Expected 256x256 aligned pixel centers")
        rect = xyz_geometry(*tile)
        ix = self.tree.query(rect)
        local = [self.polygons[int(i)] for i in ix
                 if self.polygons[int(i)].intersects(rect)]
        if not local:
            return np.zeros((256, 256), dtype=bool)
        g = unary_union(local) if len(local)>1 else local[0]
        # Unions remove split-polygons' small overlapping seams;
        # a pixel is inside land only when its center is inside geometry.
        return np.asarray(contains_xy(g, lon.ravel(), lat.ravel()),
                          dtype=bool).reshape((256, 256))


def native_dem_mask(sources, opened, cache, tile):
    indices = intersecting_source_indices(sources, *tile)
    if not indices:
        return np.zeros((256, 256), dtype=bool)
    cogs = local_cogs(sources, indices, cache, opened)
    heights, provenance, _, _ = warp_sources(cogs, tile)
    return (provenance > 0) & np.isfinite(heights) & (heights != -9999.0)


def exact_categories(valid, osm, igac, ne, gb):
    """Exact missing DEM partition. Unknown IGAC must stay None, never zero."""
    for mask in (valid, osm, ne, gb):
        if mask.shape != (256, 256):
            raise ValueError("Mismatched DEM or reference mask")
    if igac is not None and igac.shape != (256, 256):
        raise ValueError("Mismatched IGAC pixel mask")
    missing = ~valid
    land = missing & osm
    outside = missing & ~osm
    values = {
        "native_missing_dem_pixels": int(missing.sum()),
        "missing_inside_osm_land": int(land.sum()),
        "missing_outside_osm_land_UNKNOWN_not_confirmed_ocean": int(outside.sum()),
        "missing_osm_land_and_igac_department": None,
        "missing_osm_land_outside_igac_department": None,
        "missing_osm_land_and_natural_earth": int(np.count_nonzero(land & ne)),
        "missing_osm_land_not_natural_earth": int(np.count_nonzero(land & ~ne)),
        "missing_osm_land_outside_igac_and_natural_earth": None,
        "missing_igac_but_not_osm": None,
        "missing_natural_earth_but_not_osm": int(np.count_nonzero(missing & ne & ~osm)),
        "missing_geoboundaries_but_not_osm": int(np.count_nonzero(missing & gb & ~osm)),
        "osm_reference_land_pixels": int(osm.sum()),
        "osm_igac_reference_agreement_pixels": None,
        "igac_mask_available": igac is not None,
    }
    if igac is not None:
        values.update({
            "missing_osm_land_and_igac_department": int(np.count_nonzero(land & igac)),
            "missing_osm_land_outside_igac_department": int(np.count_nonzero(land & ~igac)),
            "missing_osm_land_outside_igac_and_natural_earth": int(np.count_nonzero(land & ~igac & ~ne)),
            "missing_igac_but_not_osm": int(np.count_nonzero(missing & igac & ~osm)),
            "osm_igac_reference_agreement_pixels": int(np.count_nonzero(osm & igac)),
        })
    if values["missing_inside_osm_land"] + values["missing_outside_osm_land_UNKNOWN_not_confirmed_ocean"] != values["native_missing_dem_pixels"]:
        raise AssertionError("OSM missing-pixel partition failed")
    if igac is not None and (
        values["missing_osm_land_and_igac_department"] +
        values["missing_osm_land_outside_igac_department"] != values["missing_inside_osm_land"]):
        raise AssertionError("OSM+IGAC partition failed")
    if (values["missing_osm_land_and_natural_earth"] +
        values["missing_osm_land_not_natural_earth"] != values["missing_inside_osm_land"]):
        raise AssertionError("OSM+Natural Earth partition failed")
    return values


def cell_pixel_counts(missing, osm, igac, lon, lat, tile_candidate_names):
    """Exact per-candidate pixel-cell intersection, never a COG validity claim."""
    candidate_counts = {}
    xdeg = np.floor(lon).astype(np.int16)
    ydeg = np.floor(lat).astype(np.int16)
    for name in sorted(set(tile_candidate_names)):
        rect = cell_geometry(name)
        west, south, _, _ = rect.bounds
        in_cell = (xdeg == int(west)) & (ydeg == int(south))
        if not np.any(missing & in_cell):
            raise AssertionError(f"Catalog hint {name} has no actual missing pixels in tile")
        missing_cell = missing & in_cell
        osm_cell = missing_cell & osm
        candidate_counts[name] = {
            "native_missing_pixel_cell_hits": int(missing_cell.sum()),
            "osm_land_missing_pixel_cell_hits": int(osm_cell.sum()),
            "osm_land_and_igac_missing_pixel_cell_hits": (int(np.count_nonzero(osm_cell & igac)) if igac is not None else None),
            "igac_mask_available": igac is not None,
            "outside_osm_missing_cell_hits_UNKNOWN": int(np.count_nonzero(missing_cell & ~osm)),
            "native_source_recovery_not_tested_here": True,
            "eligible_for_automatic_inclusion": False,
        }
        if (candidate_counts[name]["osm_land_missing_pixel_cell_hits"] +
            candidate_counts[name]["outside_osm_missing_cell_hits_UNKNOWN"] !=
            candidate_counts[name]["native_missing_pixel_cell_hits"]):
            raise AssertionError("Candidate pixel partition mismatch")
    return candidate_counts


def classify_candidate(entry):
    if entry.get("igac_mask_available") and entry.get("osm_land_and_igac_missing_pixel_cell_hits"):
        return "A_osm_land_and_official_igac_agree_native_cog_recovery_REQUIRES_QA"
    if entry["osm_land_missing_pixel_cell_hits"]:
        return "B_osm_land_only_official_territory_and_cog_recovery_REQUIRES_QA"
    if entry["native_missing_pixel_cell_hits"]:
        return "C_missing_outside_osm_land_UNRESOLVED_no_ocean_inference"
    return "D_no_matching_z13_missing_pixels_no_conclusion"


def raster_reference_bundle(osm_path, osm_meta):
    metadata = json.loads(Path(osm_meta).read_text())
    if metadata.get("national_publication_allowed") is not False:
        raise RuntimeError("OSM reference must never authorize release")
    if metadata.get("study_bbox_not_country_border") != list(STUDY_BBOX):
        raise RuntimeError("Clipped study bbox does not match audited bounds")
    osm = PolygonMask(load_clip(osm_path, metadata["reference_wkb_sha256"]))
    refs = load_references()
    # IGAC is optional contextual evidence. Its server has intermittently
    # returned HTTP 503: that must not make an OSM-only audit unusable.
    # Unknown IGAC is represented by None, NEVER a fake empty land mask.
    igac, source_url = None, None
    try:
        features, url = get_service_features(IGAC_SERVICE)
        if not 25 <= len(features) <= 50:
            raise RuntimeError("Official IGAC service incomplete")
        igac = PolygonMask([shape(f["geometry"]) for f in features])
        source_url = url
    except (requests.RequestException, ValueError, RuntimeError) as error:
        print("OFFICIAL_IGAC_UNAVAILABLE: OSM+Natural Earth+geoBoundaries "
              "comparison still valid; IGAC-only statistics will be NULL, not zero. "
              + str(error)[:350], flush=True)
    return osm, refs, igac, source_url, metadata


def inspect_tile(sources, opened, cache, tile, osm, refs, igac,
                 baseline=None, site=None):
    valid = native_dem_mask(sources, opened, cache, tile)
    gb, ne, lon, lat = refs.masks(tile)
    osm_mask = osm.mask(tile, lon, lat)
    igac_mask = igac.mask(tile, lon, lat) if igac is not None else None
    counts = exact_categories(valid, osm_mask, igac_mask, ne, gb)
    if baseline is not None and counts["native_missing_dem_pixels"] != baseline["missing_dem_pixels"]:
        raise AssertionError(f"Original native DEM pixel mask has changed for {tile}")
    candidates = (baseline.get("unselected_public_cogs_at_missing_pixels", [])
                  if baseline else [])
    hints = cell_pixel_counts(~valid, osm_mask, igac_mask, lon, lat, candidates)
    return {
        "z":tile[0], "x":tile[1], "y":tile[2],
        "site":site,
        "was_in_baseline_natural_earth_gap_1004":bool(
            baseline and baseline.get("missing_natural_earth_only")),
        **counts,
        "per_candidate_omitted_cog":hints,
        "osm_is_not_official_colombia_territory":True,
        "no_dem_heights_created_or_modified":True,
        "national_publication_allowed":False,
    }


def accumulate(stats, row):
    skip = {"z","x","y","site","igac_mask_available","was_in_baseline_natural_earth_gap_1004",
            "per_candidate_omitted_cog","osm_is_not_official_colombia_territory",
            "no_dem_heights_created_or_modified","national_publication_allowed"}
    for key,value in row.items():
        if key not in skip and isinstance(value,int):
            stats[key] += value
    stats["tiles"] += 1
    stats["tiles_with_native_missing_inside_osm_land"] += int(row["missing_inside_osm_land"]>0)
    if row["igac_mask_available"]:
        stats["tiles_with_osm_and_igac_missing"] += int(row["missing_osm_land_and_igac_department"]>0)


def run(manifest, osm_path, osm_meta, output, mode="pilot", incomplete=None):
    if mode not in ("pilot","national"):
        raise ValueError("Expected pilot or national mode")
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    sources = parse_manifest(manifest)
    if len(sources) != 137:
        raise AssertionError("Frozen Copernicus national source inventory changed")
    osm, refs, igac, official_url, metadata = raster_reference_bundle(osm_path, osm_meta)
    baseline_focus_count = None
    if mode == "pilot":
        todo = ((site, tile, None) for site, tile in site_tiles())
    else:
        if incomplete is None:
            raise ValueError("National mode requires 32 baseline incomplete DEM shard artifacts")
        rows, z13, land1004, names = load_incomplete_rows(incomplete)
        if (len(rows),len(z13),len(land1004),len(names)) != (3778,1917,1004,52):
            raise AssertionError("Unexpected frozen national land reference baseline")
        baseline_focus_count = len(land1004)
        todo = ((None, (r["z"],r["x"],r["y"]), r) for r in z13)
    cache = output / "native-source-cache"
    cache.mkdir(exist_ok=True)
    opened={}
    total=0
    all_stats=Counter()
    focus_stats=Counter()
    site_stats=defaultdict(Counter)
    source_stats=defaultdict(Counter)
    per_tile=[]
    try:
        for site, tile, baseline in todo:
            record = inspect_tile(sources, opened, cache, tile, osm, refs, igac,
                                  baseline=baseline, site=site)
            total += 1
            accumulate(all_stats, record)
            if record["was_in_baseline_natural_earth_gap_1004"]:
                accumulate(focus_stats,record)
            if site:
                accumulate(site_stats[site],record)
            for name,c in record["per_candidate_omitted_cog"].items():
                for k,v in c.items():
                    if isinstance(v,int) and not isinstance(v,bool):
                        source_stats[name][k] += v
                source_stats[name]["z13_tiles_with_missing_pixel_in_this_cog_degree_cell"] += 1
            per_tile.append(record)
            if total % 100 == 0:
                print(f"OSM {mode}: exact native pixels evaluated for {total} tiles",flush=True)
    finally:
        for src in opened.values():
            src.close()
    if mode=="pilot" and (total != 36 or set(site_stats) != {
       "tumaco", "san_andres","providencia","malpelo"}):
        raise AssertionError("Missing exact 36-tile four-site pilot")
    if mode=="national":
        if total!=1917 or focus_stats["tiles"]!=baseline_focus_count:
            raise AssertionError("Incomplete baseline OSM audit")
        if not any(row["native_missing_dem_pixels"] for row in per_tile):
            raise AssertionError("National source study unexpectedly no longer has native NoData pixels")
    study_names=names if mode=="national" else sorted(source_stats)
    ranked=[]
    for name in study_names:
        stats=source_stats[name]
        entry={"name":name,
               "z13_tiles_with_missing_pixel_in_this_cog_degree_cell":stats["z13_tiles_with_missing_pixel_in_this_cog_degree_cell"],
               "native_missing_pixel_cell_hits":stats["native_missing_pixel_cell_hits"],
               "osm_land_missing_pixel_cell_hits":stats["osm_land_missing_pixel_cell_hits"],
               "osm_land_and_igac_missing_pixel_cell_hits":(stats["osm_land_and_igac_missing_pixel_cell_hits"] if igac is not None else None),
               "igac_mask_available":igac is not None,
               "outside_osm_missing_cell_hits_UNKNOWN":stats["outside_osm_missing_cell_hits_UNKNOWN"],
               "review_tier":classify_candidate(stats),
               "source_promoted":False,"native_cog_recovery_not_measured":True}
        ranked.append(entry)
    ranked.sort(key=lambda x:(x["review_tier"],
         -(x["osm_land_and_igac_missing_pixel_cell_hits"] or 0),
         -x["osm_land_missing_pixel_cell_hits"],x["name"]))
    report={
        "status":"OSM_native_DEM_land_reference_audit_complete",
        "mode":mode, "created_utc":datetime.now(timezone.utc).isoformat(),
        "baseline_national_land_run":43490555676,
        "selected_source_cogs":137,
        "original_national_incomplete_z13_tiles":1917 if mode=="national" else None,
        "original_z13_natural_earth_gap_tiles":baseline_focus_count,
        "tiles_checked":total,
        "all_checked_tile_pixel_totals":dict(all_stats),
        "previously_identified_1004_tile_subset":dict(focus_stats),
        "pilot_site_summaries":{k:dict(v) for k,v in site_stats.items()},
        "all_52_omitted_public_cog_candidates":ranked,
        "source_candidate_total":len(ranked),
        "candidate_sources_promoted":0,
        "official_IGAC_admin_source":official_url,
        "official_IGAC_context_mask_status":("evaluated" if igac is not None else "unavailable_NULL_not_zero"),
        "OSM_land_polygon_reference":metadata.get("source"),
        "OSM_archive_sha256":metadata["archive"]["sha256"],
        "osm_clipped_reference_sha256":metadata["reference_wkb_sha256"],
        "osm_land_reference_is_NOT_official_territory":True,
        "osm_outside_land_is_NOT_confirmed_ocean":True,
        "quitasueno_excluded_from_proposed_source_inclusion":True,
        "synthetic_ocean_heights_or_bathymetry_added":0,
        "national_publication_allowed":False,
        "odbl_attribution":metadata["odbl_attribution"],
        "limitations":[
            "Land polygons from OSMCoastline cover other countries and are NOT a Colombia sovereignty determination",
            "A pixel outside OSM land is UNKNOWN, not confirmed sea; OSM coastline may have gaps",
            "An administrative IGAC land polygon is not a verified high-resolution coastline",
            "A candidate COG cell containing missing land pixels does NOT prove that candidate has valid DEM pixels",
            "Original 137-source DEM valid heights must remain untouched and missing pixels unfilled",
            "OSMCoastline land/water masks may have small island coverage differences with Natural Earth",
            "OSM ODbL attribution and derived database use must be assessed before public reuse",
        ],
        "per_tile":per_tile,
    }
    target = output / f"osm-{mode}-native-land-report.json"
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("per_tile","all_52_omitted_public_cog_candidates")},
                     indent=2),flush=True)
    for c in ranked:
        if c["osm_land_missing_pixel_cell_hits"]>0:
            print("SOURCE_LAND_QA",c["name"],
                  "OSM missing",c["osm_land_missing_pixel_cell_hits"],
                  "OSM+IGAC missing",c["osm_land_and_igac_missing_pixel_cell_hits"],
                  flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    p.add_argument("--osm",type=Path,default=Path("output/osm-reference/osm-land-study.wkb.gz"))
    p.add_argument("--osm-meta",type=Path,default=Path("output/osm-reference/osm-land-study-metadata.json"))
    p.add_argument("--incomplete",type=Path,default=Path("output/national-land"))
    p.add_argument("--mode",choices=("pilot","national"),default="pilot")
    p.add_argument("--output",type=Path,default=Path("output/osm-audit"))
    a=p.parse_args()
    run(a.manifest,a.osm,a.osm_meta,a.output,a.mode,a.incomplete)


if __name__=="__main__":
    main()
