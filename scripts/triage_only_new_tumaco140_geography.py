#!/usr/bin/env python3
"""Triage only 68 NEW z13 Tumaco NoData tiles using two ADM0 references.

No DEM recalculation, global OSMCoastline archive, inventory generation,
previous 27-tile repeat, or source selection. A whole-tile ADM0 polygon
containment is a NON-AUTHORITATIVE country reference; partial contact
assigns NO missing pixels to any country. No ADM0 contact NEVER proves
ocean/sea or proves no Colombian islands.

Inputs: frozen successful 139->140 native Tumaco run #43609826904 and
the already committed 27 remaining old-scope geo cases.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import requests

from official_territory_screen import xyz_geometry
from osm_territorial_source_triage import get_border_geometries

NATIVE_RUN=43609826904
EXPECTED_NEW_TILES=552
EXPECTED_MISSING_TILES=68
EXPECTED_NO_DATA=2688103
OLD_SCOPE_PENDING_TILES=27
OLD_SCOPE_PENDING_OSM_PIXELS=394622
ISO_CODES=("COL","ECU")


def classify_whole_tile(zxy,country):
    geom=xyz_geometry(*zxy)
    contained=sorted(code for code,g in country.items() if g.covers(geom))
    contact=sorted(code for code,g in country.items()
                   if g.intersects(geom) and g.intersection(geom).area>0)
    if len(contained)>1:
        status="overlapping_full_country_references_UNRESOLVED"
    elif len(contained)==1:
        status="whole_tile_country_reference_only_NOT_official_territory"
    elif contact:
        status="partial_country_reference_NO_pixel_attribution"
    else:
        status="no_adm0_contact_UNRESOLVED_NOT_verified_ocean"
    return {
        "status":status,
        "whole_tile_ADM0_reference_ISO_codes":contained,
        "intersecting_ADM0_reference_ISO_codes":contact,
        "actual_pixel_country_membership_verified":False,
        "actual_pixel_land_membership_verified":False,
        "not_verified_ocean":True,
        "not_a_legal_land_or_coastline_boundary":True,
    }


def select_only_new_140_missing(native, old):
    if (native.get("prior_139_national_coverage_run")!=43605294875
            or native.get("new_staging_COG_count")!=140
            or native.get("prior_staging_COG_count")!=139
            or native.get("new_source_only_candidate_tiles")!=752
            or native.get("national_Terrain_RGB_publication_allowed") is not False
            or native.get("source_height_preservation_exact_for_all_affected_tiles") is not True):
        raise AssertionError("Expected successfully verified 140-source incremental baseline")
    rows=native["recomputed_z13_per_tile"]
    selected=[r for r in rows if not r["in_old_139_candidate_area"]]
    if len(selected)!=EXPECTED_NEW_TILES or len({tuple(r["zxy"]) for r in selected})!=EXPECTED_NEW_TILES:
        raise AssertionError("Original 552 new z13 Tumaco XYZ tile entries incomplete")
    incomplete=[r for r in selected if r["new_native_NoData_pixels"]>0]
    if (len(incomplete)!=EXPECTED_MISSING_TILES
            or sum(r["new_native_NoData_pixels"] for r in incomplete)!=EXPECTED_NO_DATA
            or any(r["zxy"][0]!=13 or r["new_tile_status"]!="partial_dem_coverage"
                   for r in incomplete)):
        raise AssertionError("Original 68 incomplete new Tumaco tiles/NoData counts changed")
    if (native["reference_z13"]["new_140_only_tile_NoData_pixels_with_unknown_OSM_land_membership"]
            !=EXPECTED_NO_DATA):
        raise AssertionError("Original native 140 land uncertainty count changed")
    if (old["remaining_140_ambiguous_country_tiles"]!=OLD_SCOPE_PENDING_TILES
            or old["remaining_140_ambiguous_missing_OSM_land_pixels"]!=OLD_SCOPE_PENDING_OSM_PIXELS
            or len(old["remaining_140_ambiguous_tile_priorities"])!=OLD_SCOPE_PENDING_TILES
            or old["national_publication_allowed"] is not False):
        raise AssertionError("Previously resolved 27 known border cases must be reused untouched")
    return incomplete


def build(native,old,shapes,meta,errors):
    missing=select_only_new_140_missing(native,old)
    if set(shapes)!=set(ISO_CODES):
        raise RuntimeError("Both independent Colombia and Ecuador ADM0 references are required; incomplete reference coverage cannot classify these tiles")
    grouped=Counter()
    land_possible=Counter()
    out=[]
    for r in missing:
        t=r["zxy"]
        m=r["new_native_NoData_pixels"]
        g=classify_whole_tile(t,shapes)
        group=g["status"]
        grouped[group]+=1
        land_possible[group]+=m
        b=mercantile.bounds(t[1],t[2],t[0])
        out.append({
            "zxy":t,
            "bbox_lonlat":[round(b.west,8),round(b.south,8),
                           round(b.east,8),round(b.north,8)],
            "original_verified_native_NoData_pixel_centers":m,
            **g,
        })
    out.sort(key=lambda r:(-r["original_verified_native_NoData_pixel_centers"],r["zxy"]))
    if sum(grouped.values())!=EXPECTED_MISSING_TILES or sum(land_possible.values())!=EXPECTED_NO_DATA:
        raise AssertionError("New Tumaco study NoData samples not fully accounted for")
    return {
        "status":"tumaco_140_only_new_z13_missing_geographical_ADM0_reference_context_ONLY",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "source_140_unchanged":True,
        "source_verification_run":NATIVE_RUN,
        "previous_national_139_source_QA_not_repeated":True,
        "previous_native_140_source_QA_not_repeated":True,
        "old_27_geographic_cases_not_reclassified":True,
        "no_GLO30_native_raster_downloads":True,
        "no_OSM_land_archive_download":True,
        "no_IGAC_administrative_boundary_repeat":True,
        "new_140_scope_candidate_z13_tiles":EXPECTED_NEW_TILES,
        "new_140_scope_partially_covered_z13_tiles":EXPECTED_MISSING_TILES,
        "new_140_scope_native_NoData_sample_pixels":EXPECTED_NO_DATA,
        "previous_139_scope_ambiguous_tiles_left_unchanged":OLD_SCOPE_PENDING_TILES,
        "previous_139_scope_ambiguous_OSM_land_NoData_pixels_unchanged":OLD_SCOPE_PENDING_OSM_PIXELS,
        "reference_layer":"geoBoundaries gbOpen ADM0 nonauthoritative country boundary for Colombia/Ecuador",
        "country_reference_loaded":meta,
        "country_reference_unavailable":errors,
        "reference_groups_tile_count":dict(grouped),
        "reference_groups_missing_native_samples":dict(land_possible),
        "original_missing_native_samples_each_z13_tile":out,
        "no_contact_does_not_prove_sea":True,
        "partial_contact_does_not_assign_any_pixel_to_a_country":True,
        "country_boundary_is_not_certified_colombia_coastline":True,
        "missing_native_DEM_not_same_as_missing_colombia_land":True,
        "osm_land_not_certified_country_territory":True,
        "no_synthetic_sea_or_bathymetry":True,
        "quitasueno_excluded":True,
        "national_Terrain_RGB_publication_allowed":False,
        "next_decision":"If a tile has positive country-land reference, seek a bounded high-quality land mask and compare missing native pixel centers only there. Unknown/no-contact pixels remain unclassified, not water. Do not repeat national COG masks.",
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--native-report",type=Path,
                    default=Path("output/140-native/tumaco-139-to-140-exact-increment.json"))
    ap.add_argument("--old-residual",type=Path,
                    default=Path("data/staged140-residual-geography-2026-11-14.json"))
    ap.add_argument("--output",type=Path,
                    default=Path("output/tumaco140-geo/tumaco-new-z13-geographic-reference.json"))
    a=ap.parse_args()
    source=json.loads(a.native_report.read_text())
    older=json.loads(a.old_residual.read_text())
    select_only_new_140_missing(source,older)
    session=requests.Session()
    session.headers.update({"User-Agent":"ColombiaTransit-tumaco140-no-rerun-geo-reference/1.0"})
    ref,meta,errors=get_border_geometries(session,ISO_CODES)
    report=build(source,older,ref,meta,errors)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="original_missing_native_samples_each_z13_tile"},
                     indent=2,ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
