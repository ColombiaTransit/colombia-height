#!/usr/bin/env python3
"""Final OSM-COL relation check on ALL 997 original-scope missing OSM-land tiles.

Unlike the previous 27-case shortlist, this reuses the FULL original 1005
139-stage exact OSM LAND and native NoData roster and the 140 incremental
original Copernicus recovery artifact to avoid silently assuming that
foreign geoBoundaries = OSM foreign land. It checks every still-missing
OSM-land z13 tile against the OSM Colombia admin_level=2 relation 120027,
not administrative polygons from another provider.

All 23,748,406 old-scope unresolved OSM land pixel centers are accounted
for. Entire-tile relation containment -> candidate Colombia OSM-land gap;
disjoint -> excluded from Colombia; partial -> exact country attribution
unknown (potential land), require one targeted pixel-mask test only.
No elevation or land/ocean synthetic fill and no national DEM rerun.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from osm_only_colombia_land_finish import get_osm_col_boundary, tile_osm_context

ORIGINAL_139_RUN=43607959646
INCREMENT_140_RUN=43609826904
INITIAL_TILES=1005
EXPECTED_140_TILES=997
EXPECTED_140_LAND_MISSING=23748406


def recover_old_140_case_register(older,increment):
    if (older.get("total")!=INITIAL_TILES or len(older.get("tiles") or [])!=INITIAL_TILES
            or increment.get("new_staging_COG_count")!=140
            or increment.get("prior_139_national_coverage_run")!=43605294875
            or increment.get("national_Terrain_RGB_publication_allowed") is not False):
        raise AssertionError("Original 139 and 140 verified geographic/native inputs changed")
    modifications={}
    for row in increment["recomputed_z13_per_tile"]:
        if not row["in_old_139_candidate_area"]:
            continue
        if "OSM_land_recovered_lower_bound" not in row:
            continue
        lo=row["OSM_land_recovered_lower_bound"]
        hi=row["OSM_land_recovered_upper_bound"]
        if lo != hi:
            raise AssertionError("Unexpected uncertain old-scope native OSM-land pixel recovery; cannot infer exact 997 tiles")
        zxy=tuple(row["zxy"])
        if zxy in modifications:
            raise AssertionError("Duplicate changed z13 native tile")
        modifications[zxy]=row
    out=[]
    removed=0
    oldsum=0
    for row in older["tiles"]:
        zxy=tuple(row["zxy"])
        old_count=int(row["missing_native_DEM_inside_OSM_land_pixels"])
        oldsum+=old_count
        changed=modifications.get(zxy)
        if changed:
            if changed["prior_139_missing_OSM_land_pixels"]!=old_count:
                raise AssertionError(f"Original OSM-land missing count differs at {zxy}")
            count=old_count-changed["OSM_land_recovered_lower_bound"]
        else:
            count=old_count
        if count<0:
            raise AssertionError("Negative missing OSM land after source addition")
        if count==0:
            removed+=1
            continue
        out.append({
            "zxy":list(zxy),
            "confirmed_140_stage_missing_native_pixels_inside_OSM_land":count,
            "previous_139_OM_land_count":old_count,
            "140_recovered_native_OSM_land_count":old_count-count,
        })
    if (len(out)!=EXPECTED_140_TILES or sum(x["confirmed_140_stage_missing_native_pixels_inside_OSM_land"] for x in out)!=EXPECTED_140_LAND_MISSING
            or removed!=8 or oldsum!=23878663):
        raise AssertionError("Full 139->140 997 remaining OSM-land tiles failed exact reconciliation")
    return out


def classify_against_osm_relation(rows,colombia):
    stats=Counter()
    amounts=Counter()
    resolved=[]
    for row in rows:
        t=row["zxy"]
        geom=tile_osm_context(t,colombia,[],[],[])
        group=geom["OSM_COL_country_relation_tile_context"]
        n=row["confirmed_140_stage_missing_native_pixels_inside_OSM_land"]
        stats[group]+=1
        amounts[group]+=n
        resolved.append({**row,**geom})
    if sum(stats.values())!=EXPECTED_140_TILES or sum(amounts.values())!=EXPECTED_140_LAND_MISSING:
        raise AssertionError("Final full OSM Colombia country relation tile scope has missing records")
    return {"tile_counts":dict(stats),"known_missing_OSM_land_pixels":dict(amounts),
            "tiles_touching_or_within_OSM_Colombia_relation":[r for r in resolved if
                r["OSM_COL_country_relation_tile_context"]!="disjoint_OSM_Colombia_relation"],
            "tiles_disjoint_OSM_Colombia_relation":sum(
                r["OSM_COL_country_relation_tile_context"]=="disjoint_OSM_Colombia_relation"
                for r in resolved)}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--old-139-roster",type=Path,default=Path("output/old-139/remaining-139-osm-land-z13-tiles.json"))
    ap.add_argument("--increment-140",type=Path,default=Path("output/native-140/tumaco-139-to-140-exact-increment.json"))
    ap.add_argument("--latest-68-scope",type=Path,default=Path("output/new-68/osm-colombia-land-scope.json"))
    ap.add_argument("--output",type=Path,default=Path("output/all-997-colombia-osm/remaining-997-osm-country-check.json"))
    args=ap.parse_args()
    prior=json.loads(args.old_139_roster.read_text())
    native=json.loads(args.increment_140.read_text())
    coastal=json.loads(args.latest_68_scope.read_text())
    if (coastal.get("country_relation",{}).get("osm_relation")!=120027
            or len(coastal.get("new_140_only_68_tiles",[]))!=68
            or len(coastal.get("old_known_OSM_land_27_tiles",[]))!=27
            or coastal.get("national_release_approved") is not False):
        raise AssertionError("Existing 27+68 OSM coast/Colombia reference result invalid")
    all997=recover_old_140_case_register(prior,native)
    import requests
    session=requests.Session()
    relation,relation_info=get_osm_col_boundary(session)
    result=classify_against_osm_relation(all997,relation)
    expected27={tuple(r["zxy"]) for r in coastal["old_known_OSM_land_27_tiles"]}
    residual27={tuple(r["zxy"]) for r in all997 if tuple(r["zxy"]) in expected27}
    if len(residual27)!=27:
        raise AssertionError("Previously studied 27 OSM foreign-border tiles not in final 997")
    for entry in result["tiles_touching_or_within_OSM_Colombia_relation"]:
        if tuple(entry["zxy"]) in expected27:
            raise AssertionError("Earlier 27 disjoint OSM Colombia country border classifications conflict")
    record={
        "status":"full_997_140_source_remaining_OSM_land_tiles_country_relation_scope_complete",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "OSM_only_Colombia_country_relation_id":120027,
        "OSM_country_relation_reference":relation_info,
        "baseline_139_known_OSM_land_source_run":ORIGINAL_139_RUN,
        "incremental_140_native_source_run":INCREMENT_140_RUN,
        "new_68_coastline_and_country_scope_study_reused_run":43611992754,
        "OSM_positive_land_pixels_original_study_scope_total":EXPECTED_140_LAND_MISSING,
        "all_old_original_source_scope_tiles_with_OSM_land_missing":EXPECTED_140_TILES,
        "previous_known_27_foreign_border_tiles_unchanged":True,
        "previous_new_68_Tumaco_coastline_query_not_repeated":True,
        "original_GLO30_COGs_downloaded":0,
        "original_global_OSM_land_polygons_downloaded":0,
        "sea_and_ocean_outside_project_land_only":True,
        "no_bathymetry_or_synthetic_ocean_elevations":True,
        "quitasueno_excluded":True,
        "no_137_139_140_national_DEM_rerun":True,
        "national_Terrain_RGB_publication_allowed":False,
        **result,
        "interpretation":"All 997 source coverage NoData counts were exact OSM land from earlier audit. Country attribution is only CERTAIN for tiles wholly outside/inside the OSM relation; partial tiles may mix countries, require a targeted 256x256 pixel intersection, not a national DEM rerun.",
        "osm_license":"© OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in record.items() if k!="tiles_touching_or_within_OSM_Colombia_relation"},indent=2,ensure_ascii=False),flush=True)
    print("OSM_COL_REMAINING_CANDIDATES",json.dumps(record["tiles_touching_or_within_OSM_Colombia_relation"],ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
