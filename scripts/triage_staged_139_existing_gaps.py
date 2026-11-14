#!/usr/bin/env python3
"""Low-cost staged-139 geographic triage from existing exact pixel registers.

No GLO-30 COG downloads, no OSM land polygons, no national re-scan, and
no change to the approved 139 staging source inventory. Reconciles the
1005 remaining incomplete z13 OSM-land tiles from two already-verified
GitHub Actions reports, and adds only *whole-XYZ-tile* foreign/Colombia
geoBoundaries ADM0 containment references.

Full tile containment allows the known count of OSM land/NoData samples
to be associated with that entire geographic reference footprint;
PARTIAL intersections never permit per-pixel country attribution.
geoBoundaries are approximate, NOT official coastline or jurisdiction.
Original IGAC overlapping native pixels are retained as 2026-11-14
historical official *administrative-polygon* evidence, not a rerun.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
from shapely.geometry import box

from official_territory_screen import xyz_geometry
from osm_territorial_source_triage import (
    GEOBOUNDARIES, NEIGHBORS, get_border_geometries,
)

RUN_137_OSM=43573144549
RUN_139_STAGE=43605294875
EXPECTED_OSM_OLD=23879764
EXPECTED_OSM_STAGE=23878663
EXPECTED_IGAC_JOINT=5865
EXPECTED_NEW_SCOPE=112


def build_gap_registry(original_osm,staged):
    """Reconstruct exact 1005 remaining OSM-land tiles, no pixel resampling."""
    if (original_osm.get("mode")!="national"
            or original_osm.get("selected_source_cogs")!=137
            or original_osm.get("tiles_checked")!=1917
            or original_osm.get("official_IGAC_context_mask_status")!="evaluated"
            or original_osm.get("national_publication_allowed") is not False):
        raise AssertionError("Original 137 native/OSM/IGAC audited input not validated")
    if (staged.get("baseline_run_exact_osm_land_z13")!=RUN_137_OSM
            or staged.get("original_selected_COG_count")!=137
            or staged.get("staged_selected_COG_count")!=139
            or staged.get("national_Terrain_RGB_publication_allowed") is not False
            or staged.get("no_original_valid_elevations_changed") is not True):
        raise AssertionError("139-source national report failed provenance/safety gate")
    land=staged["new_139_source_OSM_land_z13_comparison"]
    original=original_osm["per_tile"]
    if len(original)!=1917:
        raise AssertionError("Original OSM per-tile rows incomplete")
    old={ (r["z"],r["x"],r["y"]):r for r in original}
    if len(old)!=1917:
        raise AssertionError("Original OSM XYZ duplicates")
    changes={}
    for r in land["changed_original_incomplete_z13_tile_rows"]:
        zxy=tuple(r["zxy"])
        if zxy not in old or zxy in changes:
            raise AssertionError("Unknown/duplicate z13 affected source tile")
        if old[zxy]["missing_inside_osm_land"]-r["OSM_land_recovered_pixels"]!=r["staged_missing_OSM_land_pixels"]:
            raise AssertionError("Original and staged exact OSM land pixel values disagree")
        if old[zxy]["missing_osm_land_and_igac_department"] and r["OSM_land_recovered_pixels"]:
            # Neither source intersects Nariño. If this ever changes,
            # rerun the exact official polygon mask before claiming the
            # old positive IGAC count still applies.
            raise AssertionError("Staging affected IGAC-positive land tile: exact re-evaluation required")
        changes[zxy]=r
    if len(changes)!=land["tiles_affected_original_incomplete_z13_rechecked"]:
        raise AssertionError("Original incomplete tile changes not reconciled")
    assert sum(r["missing_inside_osm_land"] for r in original)==EXPECTED_OSM_OLD
    found=[]
    for zxy,r in old.items():
        missing=(changes[zxy]["staged_missing_OSM_land_pixels"] if zxy in changes
                 else r["missing_inside_osm_land"])
        if missing<0:
            raise AssertionError("Negative incomplete land pixel count")
        if missing:
            igac=int(r["missing_osm_land_and_igac_department"] or 0)
            if igac>missing:
                raise AssertionError("Official IGAC joint missing pixels exceed staged OSM land count")
            found.append({
                "zxy":list(zxy),
                "missing_native_DEM_inside_OSM_land_pixels":missing,
                "historical_missing_OSM_and_official_IGAC_department_pixels":igac,
                "original_139_COG_source_gap_coverage_run":RUN_139_STAGE,
                "original_137_source_OSM_and_IGAC_pixel_audit_run":RUN_137_OSM,
            })
    new_rows=land["new_scope_incomplete_z13_tile_rows"]
    if len(new_rows)!=EXPECTED_NEW_SCOPE:
        raise AssertionError("Unknown new z13 candidate footprint")
    if any(r["missing_inside_osm_land"] for r in new_rows):
        raise AssertionError("New 139 source only tiles contain unaccounted-for OSM land")
    if (len(found)!=1005 or sum(r["missing_native_DEM_inside_OSM_land_pixels"] for r in found)!=EXPECTED_OSM_STAGE
            or sum(r["historical_missing_OSM_and_official_IGAC_department_pixels"] for r in found)!=EXPECTED_IGAC_JOINT):
        raise AssertionError("Frozen 139-source remaining national OSM land totals changed")
    if land["staged_139_z13_missing_native_pixel_totals"]["missing_inside_osm_land"]!=EXPECTED_OSM_STAGE:
        raise AssertionError("Staged result register is not the original successful run")
    return sorted(found,key=lambda r:-r["missing_native_DEM_inside_OSM_land_pixels"])


def categorize_whole_tile(tile,foreign,colombia):
    """Map only WHOLE tile containment, never use area contact to label pixels."""
    z,x,y=tile
    shape=xyz_geometry(z,x,y)
    outside=[iso for iso,g in foreign.items() if g.covers(shape)]
    inside_colombia=colombia is not None and colombia.covers(shape)
    if len(outside)>1 or (outside and inside_colombia):
        return {"reference_group":"conflicting_full_tile_country_geometries_UNRESOLVED",
                "full_tile_reference_ISO_codes":sorted(outside),
                "country_contact_codes":[],
                "proof_of_legal_colombian_land":False}
    if inside_colombia:
        return {"reference_group":"whole_tile_within_colombia_geoBoundaries_ADM0_REFERENCE_ONLY",
                "full_tile_reference_ISO_codes":["COL"],
                "country_contact_codes":[],
                "proof_of_legal_colombian_land":False}
    if len(outside)==1:
        return {"reference_group":"whole_tile_within_foreign_geoBoundaries_ADM0_REFERENCE_ONLY",
                "full_tile_reference_ISO_codes":outside,
                "country_contact_codes":[],
                "proof_of_legal_colombian_land":False}
    contacts=sorted([iso for iso,g in foreign.items()
                     if g.intersects(shape) and g.intersection(shape).area>0])
    if colombia is not None and colombia.intersects(shape) and colombia.intersection(shape).area>0:
        contacts.append("COL")
    if contacts:
        return {"reference_group":"partial_country_or_border_reference_NO_pixel_country_assignment",
                "full_tile_reference_ISO_codes":[],
                "country_contact_codes":sorted(contacts),
                "proof_of_legal_colombian_land":False}
    return {"reference_group":"no_country_ADM0_land_reference_contact_UNRESOLVED",
            "full_tile_reference_ISO_codes":[],
            "country_contact_codes":[],
            "proof_of_legal_colombian_land":False}


def apply_geographic_triage(tiles, foreign, colombia, sources, missing):
    if len(tiles)!=1005:
        raise AssertionError("Expected exactly 1005 original gap tiles")
    by_group=Counter()
    pixel_by_group=Counter()
    by_country=Counter()
    completed=[]
    for t in tiles:
        val=categorize_whole_tile(t["zxy"],foreign,colombia)
        group=val["reference_group"]
        n=t["missing_native_DEM_inside_OSM_land_pixels"]
        by_group[group]+=1
        pixel_by_group[group]+=n
        if val["full_tile_reference_ISO_codes"]:
            by_country[val["full_tile_reference_ISO_codes"][0]]+=n
        completed.append({**t,**val})
    if sum(by_group.values())!=1005 or sum(pixel_by_group.values())!=EXPECTED_OSM_STAGE:
        raise AssertionError("Geographic tile references lose or duplicate missing DEM samples")
    assert sum(t["historical_missing_OSM_and_official_IGAC_department_pixels"] for t in completed)==EXPECTED_IGAC_JOINT
    # Official positive pixel evidence is a separate overlapping variable.
    # It is NOT additive to geoBoundaries bucket counts.
    return {
        "categories_by_tiles":dict(by_group),
        "missing_OSM_land_pixels_by_tile_reference_class":dict(pixel_by_group),
        "missing_OSM_land_pixels_entirely_in_geoBoundaries_reference_country":dict(by_country),
        "tiles":completed,
        "country_reference_retrieved":sources,
        "country_reference_unavailable":missing,
        "positive_historical_official_IGAC_and_OSM_pixel_evidence":EXPECTED_IGAC_JOINT,
        "historical_IGAC_positive_tile_count":sum(
            t["historical_missing_OSM_and_official_IGAC_department_pixels"]>0 for t in completed),
        "unclassified_or_partially_intersected_country_tiles_require_pixel_level_review":True,
    }


def run(osm_file,stage_file,output):
    prior=json.loads(Path(osm_file).read_text())
    staged=json.loads(Path(stage_file).read_text())
    tiles=build_gap_registry(prior,staged)
    session=requests.Session()
    session.headers.update({"User-Agent":"ColombiaTransit-national-139-gap-geography-triage/1.0"})
    # Reuse the existing geoBoundaries download/validity routine; only
    # 9 small ADM0 geometry downloads, not 1GB OSM or any DEM source.
    foreign,meta1,errors1=get_border_geometries(session)
    col,meta2,errors2=get_border_geometries(session,("COL",))
    allmeta={**meta1,**meta2}
    errors={**errors1,**errors2}
    classified=apply_geographic_triage(tiles,foreign,col.get("COL"),allmeta,errors)
    sorted_tiles=sorted(classified.pop("tiles"),key=lambda t:(
        -int(t["historical_missing_OSM_and_official_IGAC_department_pixels"]>0),
        -t["historical_missing_OSM_and_official_IGAC_department_pixels"],
        -t["missing_native_DEM_inside_OSM_land_pixels"]))
    out=Path(output)
    out.mkdir(parents=True,exist_ok=True)
    result={
        "status":"staged_139_genuine_source_gaps_reused_geographic_triad_without_recomputing_DEM",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "input_139_national_run":RUN_139_STAGE,
        "input_137_exact_OSM_land_IGAC_run":RUN_137_OSM,
        "remaining_z13_OSM_land_missing_tile_count":1005,
        "remaining_z13_OSM_land_missing_native_DEM_pixels":EXPECTED_OSM_STAGE,
        "old_native_COG_mask_rerun":False,
        "OSM_Coastline_download_or_geometry_regeneration":False,
        "original_137_source_inventory_regeneration":False,
        "139_source_inventory_recalculation":False,
        "actual_Copernicus_COG_downloads":0,
        "historic_official_IGAC_positive_missing_pixels":EXPECTED_IGAC_JOINT,
        "historic_official_IGAC_intersected_tiles":2,
        "official_IGAC_admin_polygons_are_not_fine_shoreline":True,
        **classified,
        "next_geographic_target":"review Tumaco N01_W080 and only ambiguous/border/offshore pixels, not all 23.9 million non-Colombian or unassigned pixels",
        "country_references_are_approximate_not_legal_land_certification":True,
        "not_all_remaining_OSM_land_pixels_assigned_to_a_country":True,
        "outside_OSM_land_is_unknown_not_ocean":True,
        "original_139_COG_staging_unchanged":True,
        "quitasueno_excluded":True,
        "national_Terrain_RGB_publication_allowed":False,
        "source_methods":"Existing audited exact 137 OSM pixel counts + successful 139 source z13 deltas; whole tile geoBoundaries coverage (non-authoritative) only; OSM/IGAC exact positive historical mask retained.",
        "top_priority_gap_tiles":sorted_tiles[:30],
        "full_geographic_gap_roster_file":"remaining-139-osm-land-z13-tiles.json",
    }
    (out/"remaining-139-osm-land-z13-tiles.json").write_text(
        json.dumps({"total":len(sorted_tiles),"tiles":sorted_tiles,
                    "never_automatic_country_attribution":True},ensure_ascii=False,
                   separators=(",",":"))+"\n")
    (out/"staged139-geographic-gap-triage.json").write_text(
        json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items()
                      if k not in ("top_priority_gap_tiles","country_reference_retrieved")},
                     ensure_ascii=False,indent=2),flush=True)
    return result


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--osm",type=Path,default=Path(
        "output/baseline-osm/osm-audit/osm-national-native-land-report.json"))
    ap.add_argument("--staged",type=Path,default=Path(
        "output/staged-139/national-staged-139-dem-and-osm-coverage.json"))
    ap.add_argument("--output",type=Path,default=Path("output/staged139-geography"))
    a=ap.parse_args()
    run(a.osm,a.staged,a.output)


if __name__=="__main__":
    main()
