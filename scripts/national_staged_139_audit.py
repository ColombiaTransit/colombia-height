#!/usr/bin/env python3
"""Incremental *national* 137->139 Copernicus DEM source and OSM-land audit.

Reuse all 32 independently completed 137-source national land/DEM shards and
the exact 1,917-tile original OSM audit. Recompute with original COG rasters
only the tiles intersected by the TWO reviewed new degree-cell sources,
including previously unplanned z0-z13 candidate tiles.

This is exactly equivalent to a re-count of 139-source DEM validity over
the union of all 139 degree-cell candidate tiles, subject to documented
source order, frozen original checks, and source masks. It is NOT official
Colombia territory (OSM includes neighboring countries), ocean detection,
or permission to create Terrain-RGB from NoData.
"""
import argparse
import gzip
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from shapely.geometry import shape

from national_dem_coverage import (
    classify_mask, geographical_owner, intersecting_source_indices, local_cogs,
)
from national_tile_plan import candidate_tiles, parse_manifest
from osm_national_land_audit import (
    PolygonMask, exact_categories, raster_reference_bundle,
)
from official_territory_screen import xyz_geometry
from stage_island_sources import ALLOWLIST, approved_sources
from two_cog_seam_pilot import warp_sources

PIXLEN=256*256
BASELINE_OSM_RUN=43573144549
BASELINE_NATIONAL_RUN=43490555676
EXPECTED_BASE_CANDIDATES=96751
EXPECTED_BASE_INCOMPLETE_Z13=1917
REQUIRED_TILE_KEYS=("z","x","y")
TRACKED_LAND_KEYS=(
    "native_missing_dem_pixels",
    "missing_inside_osm_land",
    "missing_outside_osm_land_UNKNOWN_not_confirmed_ocean",
    "missing_osm_land_and_natural_earth",
    "missing_osm_land_not_natural_earth",
    "missing_osm_land_and_igac_department",
    "missing_osm_land_outside_igac_department",
    "missing_igac_but_not_osm",
)


def validate_stage_selection(original,staged,decision):
    if len(original)!=137 or len(staged)!=139:
        raise AssertionError("Unexpected frozen/staged source count")
    if [x["name"] for x in staged[:137]] != [x["name"] for x in original]:
        raise AssertionError("Staged order must preserve all 137 native DEM source priorities")
    if {x["name"] for x in staged[137:]}!=set(ALLOWLIST):
        raise AssertionError("Only reviewed two offshore sources may be added")
    if {x["name"] for x in original} & set(ALLOWLIST):
        raise AssertionError("Staging source already in original selection")
    approved_sources(decision)
    return staged[137:]


def read_original_national_shards(root,original_sources):
    root=Path(root)
    shards=sorted(root.glob("land-shard-*.ndjson.gz"))
    summaries=sorted(root.glob("land-summary-*.json"))
    if len(shards)!=32 or len(summaries)!=32:
        raise AssertionError(f"Missing original 32 national data shards: {len(shards)} rows, {len(summaries)} summaries")
    data={}
    by_zoom=defaultdict(Counter)
    shard_totals=Counter()
    for path in shards:
        shard=int(path.name[len("land-shard-"):-len(".ndjson.gz")])
        if shard not in range(32):
            raise AssertionError("Invalid shard number")
        with gzip.open(path,"rt",encoding="utf-8") as stream:
            for line in stream:
                row=json.loads(line)
                key=(row["z"],row["x"],row["y"])
                if key in data or geographical_owner(*key)!=shard:
                    raise AssertionError(f"Original unique XYZ/shard provenance violated {key}")
                valid=row["valid_dem_pixels"]
                missing=row["missing_dem_pixels"]
                expected_status=("full_dem_coverage" if valid==PIXLEN else
                                 "no_dem_coverage" if valid==0 else "partial_dem_coverage")
                if valid+missing!=PIXLEN or row["dem_coverage"]!=expected_status:
                    raise AssertionError("Original source coverage classification corrupt")
                data[key]=valid
                by_zoom[key[0]][row["dem_coverage"]]+=1
                shard_totals[shard]+=1
    # The original land-shard files intentionally store ONLY incomplete
    # tiles. The complete 92,973 original source tiles are implicit and
    # audited in each shard summary. Rebuild the full candidate key set
    # without resampling a single already-verified full tile.
    if len(data)!=3778 or any(v==PIXLEN for v in data.values()):
        raise AssertionError("Expected exactly 3,778 original incomplete z0-z13 records")
    totals=0
    for path in summaries:
        stat=json.loads(path.read_text())
        if (stat.get("mode")!="full" or stat.get("complete") is not True
                or stat.get("source_cog_count")!=137
                or stat.get("national_publication_allowed") is not False):
            raise AssertionError("Only full immutable original 137-source evidence permitted")
        shard=stat["shard"]
        incomplete_here=sum(n for k,n in stat["dem_coverage_counts"].items()
                            if k!="full_dem_coverage")
        if shard_totals[shard]!=incomplete_here:
            raise AssertionError("Original incomplete register shard count mismatch")
        if sum(stat["dem_coverage_counts"].values())!=stat["tiles_checked"]:
            raise AssertionError("Shard count excludes inferred fully covered DEM tiles")
        totals+=stat["tiles_checked"]
    if totals!=EXPECTED_BASE_CANDIDATES:
        raise AssertionError("Original national shard reconciliation failed")
    # Valid source-driven geographical shards may be EMPTY. The 32 required
    # files and summaries still exist; do not mistake zero data rows for a
    # missing shard.
    if {int(x.name[len("land-shard-"):-len(".ndjson.gz")]) for x in shards}!=set(range(32)):
        raise AssertionError("Not all 32 original shard identities present")
    if {json.loads(x.read_text())["shard"] for x in summaries}!=set(range(32)):
        raise AssertionError("Missing original shard summary IDs")
    planned=set()
    for z in range(14):
        for x,y in candidate_tiles(original_sources,z):
            planned.add((z,x,y))
    if len(planned)!=EXPECTED_BASE_CANDIDATES or not set(data).issubset(planned):
        raise AssertionError("Original full 137-source candidate plan and incomplete source rows differ")
    for tile in planned-set(data):
        data[tile]=PIXLEN
        by_zoom[tile[0]]["full_dem_coverage"]+=1
    if len(data)!=EXPECTED_BASE_CANDIDATES or sum(
        c["full_dem_coverage"] for c in by_zoom.values())!=92973:
        raise AssertionError("Original 92,973 implicit full-coverage tiles missing")
    # Verify FULL + incomplete counts reconcile precisely to shard summaries
    # after materializing the implicit original fully-covered candidates.
    global_shard_counts=Counter()
    for key in planned:
        global_shard_counts[geographical_owner(*key)]+=1
    for path in summaries:
        stat=json.loads(path.read_text())
        if global_shard_counts[stat["shard"]]!=stat["tiles_checked"]:
            raise AssertionError("Complete original source tile count drift within geographical shard")
    return data,by_zoom


def tile_bounds_overlap_new(source,tile):
    # Same exact 2 arcsecond conservative source-window behavior used by
    # national_dem_coverage.intersecting_source_indices (not a land mask).
    return bool(intersecting_source_indices([source],*tile))


def local_indices_to_check(original,staged,extras,tile,include_extras):
    """At low zoom avoid downloading 137 remote COGs for global z0-z8 tiles.

    Only original COGs touching the NEW COG footprints can contribute a
    valid native DEM pixel where a new height could possibly be added.
    This is mathematically sufficient for the *increment* in valid pixels,
    not for reconstructing the original global map (which is reused).
    """
    if tile[0]>=9:
        return intersecting_source_indices(staged if include_extras else original,*tile)
    eps=2./3600
    near=[]
    for i,old in enumerate(original):
        west=float(old["longitude"]);south=float(old["latitude"])
        if any(west< float(new["longitude"])+1+eps
               and west+1>float(new["longitude"])-eps
               and south<float(new["latitude"])+1+eps
               and south+1>float(new["latitude"])-eps
               for new in extras):
            near.append(i)
    if include_extras:
        near.extend(137+i for i,s in enumerate(extras) if tile_bounds_overlap_new(s,tile))
    return near


def render_subset(sources,ids,opened,cache,tile):
    if not ids:
        return (np.zeros((256,256),dtype=bool),
                np.full((256,256),-9999.,dtype=np.float32))
    cogs=local_cogs(sources,ids,cache,opened)
    heights, provenance, _, _=warp_sources(cogs,tile)
    valid=(provenance>0)&np.isfinite(heights)&(heights!=-9999.)
    return valid,heights


def compare_native_pixel_arrays(before_valid,before_height,after_valid,after_height):
    if any(np.asarray(a).shape!=(256,256) for a in
           (before_valid,before_height,after_valid,after_height)):
        raise ValueError("Native DEM grid mismatch")
    if np.any(before_valid & ~after_valid):
        raise AssertionError("The two extra island COGs removed valid original heights")
    shared=before_valid&after_valid
    delta=(float(np.max(np.abs(before_height[shared]-after_height[shared])))
           if np.any(shared) else 0.)
    if not np.isfinite(delta) or delta>.001:
        raise AssertionError(f"Extra island COGs overwrote original valid heights: {delta}")
    newly_valid=(~before_valid)&after_valid
    return {"newly_valid_pixels":int(newly_valid.sum()),
            "max_original_height_change_m":delta,
            "all_native_elevations_preserved":True}


def stage_coverage_counts(original_counts,all_staged_keys,affected_results):
    """Aggregate exact all-zoom DEM tile status without scanning 97k originals."""
    status=Counter()
    by_zoom=defaultdict(Counter)
    missing_by_zoom=Counter()
    original_keys=set(original_counts)
    if not original_keys.issubset(all_staged_keys):
        raise AssertionError("New source inventory removed originally planned tiles")
    if not set(affected_results).issubset(all_staged_keys):
        raise AssertionError("Affected tile outside staged plan")
    for key in all_staged_keys:
        valid=(affected_results[key]["staged_valid_pixels"]
               if key in affected_results else original_counts[key])
        if not isinstance(valid,int) or not 0<=valid<=PIXLEN:
            raise AssertionError("Invalid national native-DEM pixel count")
        status_name=("full_dem_coverage" if valid==PIXLEN else
                     "no_dem_coverage" if valid==0 else "partial_dem_coverage")
        status[status_name]+=1
        by_zoom[str(key[0])][status_name]+=1
        missing_by_zoom[str(key[0])]+=PIXLEN-valid
    return dict(status), {k:dict(v) for k,v in sorted(by_zoom.items(),key=lambda x:int(x[0]))},dict(missing_by_zoom)


def accumulate_land(counter,counts,delta=1,igac_enabled=True):
    for k in TRACKED_LAND_KEYS:
        if not igac_enabled and ("igac" in k):
            continue
        n=counts.get(k)
        if n is None:
            continue
        counter[k]+=delta*n
        if counter[k]<0:
            raise AssertionError(f"Negative summed reference-land count {k}")


def compute_land_changes(original_osm,original_counts,affected,extras,
                         staged,osm,refs,igac,opened,cache):
    """One physical OSM polygon reference for original and staged gaps."""
    original_per={tuple(row[k] for k in REQUIRED_TILE_KEYS):row
                  for row in original_osm["per_tile"]}
    if len(original_per)!=EXPECTED_BASE_INCOMPLETE_Z13:
        raise AssertionError("Expected frozen 1,917 original z13 OSM gap entries")
    original_osm_totals=original_osm["all_checked_tile_pixel_totals"]
    prior=Counter()
    for k in TRACKED_LAND_KEYS:
        if original_osm_totals.get(k) is not None:
            prior[k]=original_osm_totals[k]
    after=Counter(prior)
    all_after_missing=set(original_per)
    rewritten=[]
    new_rows=[]
    no_change_unrelated=0
    new_z13_affected=0
    igac_available=(igac is not None)
    for tile in sorted(affected):
        if tile[0]!=13:
            continue
        a=affected[tile]
        if a["staged_valid_pixels"]==PIXLEN and a["new_scope"] is False and tile not in original_per:
            no_change_unrelated+=1
            continue
        gb,ne,lon,lat=refs.masks(tile)
        landmask=osm.mask(tile,lon,lat)
        igacmask=igac.mask(tile,lon,lat) if igac_available else None
        if a["new_scope"]:
            # Entirely new candidate tiles (some sea; some valid real COG).
            if a["staged_valid_pixels"]==PIXLEN:
                continue
            valid=a["staged_valid_mask"]
            row=exact_categories(valid,landmask,igacmask,ne,gb)
            accumulate_land(after,row,igac_enabled=igac_available)
            all_after_missing.add(tile)
            new_z13_affected+=1
            new_rows.append({"zxy":list(tile),**{k:row.get(k) for k in TRACKED_LAND_KEYS}})
        elif tile in original_per:
            prev=original_per[tile]
            original_native=a["original_valid_mask"]
            staged_native=a["staged_valid_mask"]
            before_counts=exact_categories(original_native,landmask,igacmask,ne,gb)
            after_counts=exact_categories(staged_native,landmask,igacmask,ne,gb)
            for key in ("native_missing_dem_pixels","missing_inside_osm_land",
                        "missing_outside_osm_land_UNKNOWN_not_confirmed_ocean",
                        "missing_osm_land_and_natural_earth","missing_osm_land_not_natural_earth"):
                if before_counts[key]!=prev[key]:
                    raise AssertionError(f"Frozen OSM study land pixel disagreement at {tile}: {key}: {before_counts[key]} vs {prev[key]}")
            if igac_available:
                for key in ("missing_osm_land_and_igac_department",
                            "missing_osm_land_outside_igac_department",
                            "missing_igac_but_not_osm"):
                    if before_counts[key]!=prev[key]:
                        raise AssertionError(f"Frozen IGAC land baseline differs at {tile}: {key}")
            accumulate_land(after,before_counts,-1,igac_available)
            accumulate_land(after,after_counts,1,igac_available)
            if after_counts["native_missing_dem_pixels"]==0:
                all_after_missing.discard(tile)
            rewritten.append({"zxy":list(tile),
                              "source_recovered_pixels":a["genuine_native_height_pixels_recovered"],
                              "OSM_land_recovered_pixels":before_counts["missing_inside_osm_land"]-after_counts["missing_inside_osm_land"],
                              "outside_OSM_land_recovered_pixels_UNKNOWN":before_counts["missing_outside_osm_land_UNKNOWN_not_confirmed_ocean"]-after_counts["missing_outside_osm_land_UNKNOWN_not_confirmed_ocean"],
                              "staged_missing_OSM_land_pixels":after_counts["missing_inside_osm_land"],
                              "staged_missing_outside_OSM_land_UNKNOWN":after_counts["missing_outside_osm_land_UNKNOWN_not_confirmed_ocean"]})
    if not igac_available:
        for k in TRACKED_LAND_KEYS:
            if "igac" in k:
                after.pop(k,None)
    assert after["native_missing_dem_pixels"]==(
        after["missing_inside_osm_land"]+after["missing_outside_osm_land_UNKNOWN_not_confirmed_ocean"])
    return {
        "original_137_z13_missing_native_pixel_totals":{k:original_osm_totals.get(k) for k in TRACKED_LAND_KEYS},
        "staged_139_z13_missing_native_pixel_totals":{k:(after.get(k) if ("igac" not in k or igac_available) else None) for k in TRACKED_LAND_KEYS},
        "original_137_incomplete_z13_tiles":len(original_per),
        "staged_139_incomplete_z13_tiles":len(all_after_missing),
        "original_137_tiles_with_missing_OSM_land":original_osm_totals.get("tiles_with_native_missing_inside_osm_land"),
        "tiles_affected_original_incomplete_z13_rechecked":len(rewritten),
        "new_scope_z13_incomplete_tiles":new_z13_affected,
        "changed_original_incomplete_z13_tile_rows":rewritten,
        "new_scope_incomplete_z13_tile_rows":new_rows,
        "IGAC_classification_status":("verified_against_original_where_impacted" if igac_available else "unavailable_NULL_not_zero"),
        "OSM_outside_land_is_UNKNOWN_not_ocean":True,
    }


def run(baseline_land,base_osm,base_manifest,staged_manifest,
        selection,osm_clip,osm_metadata,output):
    old=parse_manifest(base_manifest)
    new=parse_manifest(staged_manifest)
    approved=validate_stage_selection(old,new,json.loads(Path(selection).read_text()))
    baseline,old_zoom=read_original_national_shards(baseline_land,old)
    original_osm=json.loads(Path(base_osm).read_text())
    if (original_osm.get("mode")!="national"
            or original_osm.get("tiles_checked")!=1917
            or original_osm.get("selected_source_cogs")!=137
            or original_osm.get("national_publication_allowed") is not False
            or original_osm.get("source_candidate_total")!=52):
        raise AssertionError("Wrong original national OSM 137-source reference report")
    stage_tiles=set()
    zoom_expected={}
    for z in range(14):
        planned=candidate_tiles(new,z)
        zoom_expected[str(z)]=len(planned)
        stage_tiles.update((z,x,y) for x,y in planned)
    if not set(baseline).issubset(stage_tiles):
        raise AssertionError("139 staged source plan is not a superset of original 137 source plan")
    # Only 2 new native source cells can alter DEM: no other national
    # coordinate requires re-warping. ALL new-source-only XYZ candidate
    # tiles are included, including those absent in the 137-source study.
    changed={tile for tile in stage_tiles if
             any(tile_bounds_overlap_new(s,tile) for s in approved)}
    new_scope=stage_tiles-set(baseline)
    if not new_scope.issubset(changed):
        raise AssertionError("A new 139-source candidate tile lacks a matching approved COG")
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    cache=output/"native-source-cache"
    cache.mkdir(parents=True,exist_ok=True)
    opened={}
    delta={}
    changed_by_zoom=Counter()
    recovered_by_zoom=Counter()
    original_base_subsets_exact_z9_plus=0
    try:
        for tile in sorted(changed):
            old_ids=local_indices_to_check(old,new,approved,tile,False)
            new_ids=local_indices_to_check(old,new,approved,tile,True)
            original_valid,original_height=render_subset(new,old_ids,opened,cache,tile)
            staged_valid,staged_height=render_subset(new,new_ids,opened,cache,tile)
            diff=compare_native_pixel_arrays(original_valid,original_height,
                                             staged_valid,staged_height)
            prev=baseline.get(tile)
            if tile[0]>=9 and prev is not None:
                if int(original_valid.sum())!=prev:
                    raise AssertionError(f"Frozen original native full-tile mask changed at {tile}: {int(original_valid.sum())} vs {prev}")
                original_base_subsets_exact_z9_plus+=1
            if prev is not None:
                total=prev+diff["newly_valid_pixels"]
            else:
                total=int(staged_valid.sum())
            if total>PIXLEN:
                raise AssertionError(f"Staged source generated impossible DEM coverage: {tile}")
            delta[tile]={
                "staged_valid_pixels":total,
                "genuine_native_height_pixels_recovered":diff["newly_valid_pixels"],
                "max_original_valid_height_change_m":diff["max_original_height_change_m"],
                "new_scope":prev is None,
            }
            if tile[0]==13:
                delta[tile]["staged_valid_mask"]=staged_valid
                delta[tile]["original_valid_mask"]=original_valid
            changed_by_zoom[str(tile[0])]+=1
            recovered_by_zoom[str(tile[0])]+=diff["newly_valid_pixels"]
            if len(delta)%150==0:
                print("139 source incremental national DEM:",len(delta),"/",len(changed),
                      "affected original/new tiles verified",flush=True)
    finally:
        for ds in opened.values():
            ds.close()
    statuses,byzoom,missing_byzoom=stage_coverage_counts(baseline,stage_tiles,delta)
    osm,refs,igac,official_source,osm_meta=raster_reference_bundle(osm_clip,osm_metadata)
    if osm_meta.get("archive",{}).get("sha256")!=original_osm.get("OSM_archive_sha256"):
        raise AssertionError("Global OSM land source archive drifted: original z13 land comparison unsafe")
    land=compute_land_changes(original_osm,baseline,delta,approved,new,osm,refs,
                              igac,{},cache)
    # The reference pixel math needs original exact binary masks for only
    # the changed z13 tiles, not every unchanged national z13 tile.
    assert all(val["max_original_valid_height_change_m"]<=.001 for val in delta.values())
    if sum(statuses.values())!=len(stage_tiles):
        raise AssertionError("139 countrywide staged candidate total incorrect")
    if (sum(changed_by_zoom.values())!=len(changed)
            or sum(zoom_expected.values())!=len(stage_tiles)):
        raise AssertionError("New-source-only tile enumeration incomplete")
    original_z13_affected=sum(1 for tile in delta if tile[0]==13 and tile in baseline)
    new_z13=sum(1 for t in new_scope if t[0]==13)
    original_land=land["original_137_z13_missing_native_pixel_totals"]
    staged_land=land["staged_139_z13_missing_native_pixel_totals"]
    if staged_land["missing_inside_osm_land"]>original_land["missing_inside_osm_land"]+PIXLEN*new_z13:
        raise AssertionError("Impossible staged OSM land missing pixel count")
    result={
        "status":"full_countrywide_139_COG_candidate_tile_coverage_exact_incremental_from_137_complete_shards",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "baseline_run_countrywide_32_shards":BASELINE_NATIONAL_RUN,
        "baseline_run_exact_osm_land_z13":BASELINE_OSM_RUN,
        "original_selected_COG_count":137,
        "staged_selected_COG_count":139,
        "additional_original_Copernicus_COGs":[s["name"] for s in approved],
        "source_precedence":"all original 137 COGs first, then the two staged island COGs",
        "original_national_candidate_tile_count":len(baseline),
        "staged_national_candidate_tile_count":len(stage_tiles),
        "new_staged_candidate_tiles_total":len(new_scope),
        "original_all_zoom_coverage_counts":{z:dict(c) for z,c in old_zoom.items()},
        "staged_all_zoom_native_DEM_coverage_counts":statuses,
        "staged_by_zoom_native_DEM_tile_coverage":byzoom,
        "staged_by_zoom_missing_native_sample_pixels":missing_byzoom,
        "candidate_tile_counts_by_zoom":zoom_expected,
        "recomputed_tiles_across_all_zooms":len(delta),
        "recomputed_existing_source_tiles_z9_to_z13_verified_against_frozen_baseline":original_base_subsets_exact_z9_plus,
        "recomputed_new_candidate_tiles_by_zoom":dict(Counter(str(t[0]) for t in new_scope)),
        "recomputed_original_candidate_tiles_by_zoom":dict(Counter(str(t[0]) for t in delta if t in baseline)),
        "native_source_pixel_recovery_by_zoom":dict(recovered_by_zoom),
        "new_139_source_OSM_land_z13_comparison":land,
        "previous_52_source_candidates_still_advisory":True,
        "candidates_remaining_outside_staging":50,
        "official_IGAC_reference_url_if_available":official_source,
        "OSM_archive_sha256_unchanged":original_osm["OSM_archive_sha256"],
        "OSM_is_NOT_official_colombia_territory":True,
        "outside_OSM_land_is_NOT_verified_ocean":True,
        "geographic_extent_includes_foreign_and_offshore_source_cells":True,
        "no_original_valid_elevations_changed":True,
        "no_synthetic_bathymetry_or_ocean_heights":True,
        "quitasueno_explicitly_excluded_from_source_approval":True,
        "national_Terrain_RGB_publication_allowed":False,
        "limitations":[
            "DEM counts cover all 139 selected 1-degree COG candidate tiles at zoom 0-13, not a certified Colombian land-only polygon",
            "Low-zoom incremental pixel recoveries use only original COGs physically adjacent to the two new source cells; original total valid counts come from exact frozen 32-shard national baseline",
            "OSM land totals are native 256x256 z13 pixel centers and may include parts of neighboring countries; outside OSM land is unknown, not verified water",
            "The original 1,917 incomplete z13 tiles are reused only when physically unaffected by the two new GLO-30 source COGs",
            "Source raster bilinear reprojection and source order unchanged; no original native height samples were replaced",
            "IGAC counts are NULL rather than invented when live IGAC administrative layers are inaccessible",
            "No Mapbox Terrain-RGB encoded, no national release, and no ocean or bathymetry synthesis",
        ],
    }
    path=output/"national-staged-139-dem-and-osm-coverage.json"
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items()
                      if k!="new_139_source_OSM_land_z13_comparison" and
                         k!="original_all_zoom_coverage_counts"},
                     indent=2,ensure_ascii=False),flush=True)
    print("NATIONAL_139_OSM_RESULTS",json.dumps({
        k:v for k,v in land.items() if "tile_rows" not in k and "changed_original" not in k},
        indent=2,ensure_ascii=False),flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-land",type=Path,default=Path("output/national-land"))
    p.add_argument("--base-osm",type=Path,default=Path("output/osm-baseline/osm-audit/osm-national-native-land-report.json"))
    p.add_argument("--base-manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    p.add_argument("--staged-manifest",type=Path,default=Path("output/island-stage/colombia_dem_manifest_island_staging_139.csv"))
    p.add_argument("--selection",type=Path,default=Path("data/staged-island-source-selection-2026-11-14.json"))
    p.add_argument("--osm",type=Path,default=Path("output/osm-reference/osm-land-study.wkb.gz"))
    p.add_argument("--osm-meta",type=Path,default=Path("output/osm-reference/osm-land-study-metadata.json"))
    p.add_argument("--output",type=Path,default=Path("output/national-staged139"))
    a=p.parse_args()
    run(a.base_land,a.base_osm,a.base_manifest,a.staged_manifest,
        a.selection,a.osm,a.osm_meta,a.output)


if __name__=="__main__":
    main()
