#!/usr/bin/env python3
"""Exact incremental native GLO-30 validity changes from 139 to 140 sources.

Only the new Tumaco N01_W080 source footprint may be re-warped. Reuse the
successful 139-source all-zoom countrywide SUMMARIES and frozen original OSM
per-tile evidence. Do not rebuild 137/139 national shard masks or download
the global OSM archive. Native/OSM pixels outside the candidate footprint
are mathematically unchanged.

No new OSM geometry is loaded: old z13 OSM-land recovered pixels are
reported as rigorous LOWER/UPPER bounds unless all missing pixels on a
given tile are recovered (then the number is exact). New 140-only tiles
have UNKNOWN OSM-land fraction, never guessed ocean or legal Colombia.
"""
import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import numpy as np

from national_dem_coverage import intersecting_source_indices, local_cogs
from national_tile_plan import candidate_tiles, parse_manifest
from stage_tumaco_140 import TUMACO, ISLANDS, STAGING_RUN_139, COVERAGE_RUN_139
from two_cog_seam_pilot import warp_sources

P=65536
OSM_RUN=43573144549


def safe_sources(old,new):
    if len(old)!=139 or len(new)!=140:
        raise AssertionError("Expected exactly source 139 -> 140 staging")
    if [s["name"] for s in new[:139]] != [s["name"] for s in old]:
        raise AssertionError("Existing 139 source order or content changed")
    if {s["name"] for s in old[137:]}!=ISLANDS or new[139]["name"]!=TUMACO:
        raise AssertionError("Exactly one Tumaco COG appended after two island stages")
    if any(s["name"]==TUMACO for s in old):
        raise AssertionError("Tumaco already in old baseline")
    if new[139]["status"]!="ok":
        raise AssertionError("Tumaco source not verified as original native COG")


def all_zxy(sources):
    return {(z,x,y) for z in range(14) for x,y in candidate_tiles(sources,z)}


def source_influenced(source,tile):
    return bool(intersecting_source_indices([source],*tile))


def selected_ids_for_new_source(old,new,tile,whole_tile=False):
    """Return exact old and new index lists with stable precedence.

    At z<=6 global tiles span hundreds of 1-degree COGs; use the
    *local* original sources intersecting the new COG cell. A distant
    source cannot contribute valid pixels inside the new source cell.
    At z>=7 read the complete tile's small source list to determine
    full/partial tile status without any estimate.
    """
    if whole_tile or tile[0]>=7:
        ids=intersecting_source_indices(old,*tile)
        return ids,ids+[139]
    target=new[139]
    west=float(target["longitude"]);south=float(target["latitude"])
    eps=2/3600
    nearby=[
        i for i,s in enumerate(old)
        if float(s["longitude"])<west+1+eps
        and float(s["longitude"])+1>west-eps
        and float(s["latitude"])<south+1+eps
        and float(s["latitude"])+1>south-eps
    ]
    return nearby,nearby+[139]


def native_mask(sources,ids,opened,cache,tile):
    if not ids:
        return np.zeros((256,256),bool),np.full((256,256),-9999.,np.float32)
    raster=local_cogs(sources,ids,cache,opened)
    h,prov,_,_=warp_sources(raster,tile)
    valid=(prov>0)&np.isfinite(h)&(h!=-9999.)
    return valid,h


def compare_masks(before,bheight,after,aheight):
    if any(x.shape!=(256,256) for x in (before,bheight,after,aheight)):
        raise AssertionError("Unaligned native 256x256 raster pixel centers")
    if np.any(before & ~after):
        raise AssertionError("Valid old source height disappeared")
    joint=before&after
    d=float(np.max(np.abs(bheight[joint]-aheight[joint]))) if joint.any() else 0.
    if not np.isfinite(d) or d>.001:
        raise AssertionError(f"Previously valid native heights changed {d}m")
    return int(np.count_nonzero(after&~before))


def classify(valid):
    if valid==P:
        return "full_dem_coverage"
    if valid==0:
        return "no_dem_coverage"
    return "partial_dem_coverage"


def guaranteed_outside_all_COGs(tile,source_list):
    """Prove one lowzoom 256px pixel could never be valid from any selected source.

    This uses only native 1-degree source bounding cells, NOT a land or
    sea model. A pixel with no COG source proves 'not full' and is
    sufficient to preserve the low-zoom tile-classification aggregate.
    """
    z,x,y=tile
    if z>6:
        raise ValueError("Use full native render for z>=7")
    b=mercantile.bounds(x,y,z)
    # Candidate source has only ~1x1 degree footprint. Prove at least
    # one pixel position has no source in a conservative 2 arcsec margin.
    # mercantile.xy_bounds local-to-raster uses Web Mercator pixel centers;
    # calculate x/y bounds of each pixel in lon/lat without OSM geometries.
    import rasterio.warp
    xy=mercantile.xy_bounds(x,y,z)
    gx=xy.left+(np.arange(256)+.5)*(xy.right-xy.left)/256
    gy=xy.top-(np.arange(256)+.5)*(xy.top-xy.bottom)/256
    # Deterministically sample a 16x16 grid first; if none, full
    # 65536-pixel grid as a very low-cost geometry fallback.
    for step in (16,1):
        X,Y=np.meshgrid(gx[::step],gy[::step])
        lo,la=rasterio.warp.transform("EPSG:3857","EPSG:4326",
                                    X.ravel().tolist(),Y.ravel().tolist())
        lo=np.asarray(lo);la=np.asarray(la)
        covered=np.zeros(lo.shape,dtype=bool)
        for s in source_list:
            w=float(s["longitude"]);h=float(s["latitude"])
            eps=2/3600
            covered |= ((lo>=w-eps)&(lo<=w+1+eps)&
                        (la>=h-eps)&(la<=h+1+eps))
        if np.any(~covered):
            return True
    return False


def previous_osm_tile_index(land,old_osm):
    previous=land["new_139_source_OSM_land_z13_comparison"]
    if (old_osm.get("mode")!="national" or old_osm.get("tiles_checked")!=1917
            or old_osm.get("selected_source_cogs")!=137
            or old_osm.get("official_IGAC_context_mask_status")!="evaluated"):
        raise AssertionError("Not the original verified 137/IGAC/OSM land evidence")
    base={ (r["z"],r["x"],r["y"]):r for r in old_osm["per_tile"]}
    if len(base)!=1917:
        raise AssertionError("Original reference tile count changed")
    changed={tuple(r["zxy"]):r for r in previous["changed_original_incomplete_z13_tile_rows"]}
    additions={tuple(r["zxy"]):r for r in previous["new_scope_incomplete_z13_tile_rows"]}
    if len(changed)!=previous["tiles_affected_original_incomplete_z13_rechecked"]:
        raise AssertionError("Original 139 land-mask changes incomplete")
    if len(additions)!=previous["new_scope_z13_incomplete_tiles"]:
        raise AssertionError("New 139-source tile classification incomplete")
    if previous["staged_139_z13_missing_native_pixel_totals"]["missing_inside_osm_land"]!=23878663:
        raise AssertionError("139-stage exact OSM-land baseline changed")
    return base,changed,additions


def frozen_land_before(tile,missing,base,changed,additions):
    if tile in changed:
        r=changed[tile]
        if r["staged_missing_OSM_land_pixels"]+r["staged_missing_outside_OSM_land_UNKNOWN"]!=missing:
            raise AssertionError("139 OSM changed row and actual native tile mask differ")
        return r["staged_missing_OSM_land_pixels"],None
    if tile in additions:
        r=additions[tile]
        if r["native_missing_dem_pixels"]!=missing:
            raise AssertionError("New 139 scope OSM tile and native mask differ")
        return r["missing_inside_osm_land"],r.get("missing_osm_land_and_igac_department")
    if tile in base:
        r=base[tile]
        if r["native_missing_dem_pixels"]!=missing:
            raise AssertionError("Unchanged 137 OSM baseline tile and 139 native mask differ")
        return r["missing_inside_osm_land"],r["missing_osm_land_and_igac_department"]
    if missing!=0:
        raise AssertionError("Previously incomplete 139 source tile has no frozen OSM record")
    return 0,0


def rigorous_land_bounds(old_missing,old_osm_land,native_recovered):
    """No spurious exact OSM claim without actual land geometry."""
    if not 0<=old_osm_land<=old_missing or not 0<=native_recovered<=old_missing:
        raise ValueError("Native/OSM bounds not consistent")
    lo=max(0,native_recovered-(old_missing-old_osm_land))
    hi=min(native_recovered,old_osm_land)
    if lo>hi:
        raise AssertionError("Impossible exact land recovery bounds")
    return lo,hi


def run(stage139,stage140,prior139,prior_osm,output):
    old=parse_manifest(stage139)
    new=parse_manifest(stage140)
    safe_sources(old,new)
    before=json.loads(Path(prior139).read_text())
    if (before["staged_selected_COG_count"]!=139
            or before["baseline_run_exact_osm_land_z13"]!=OSM_RUN
            or before["national_Terrain_RGB_publication_allowed"] is not False
            or before["staged_national_candidate_tile_count"]!=98152):
        raise AssertionError("139 national aggregate is not verified")
    old_osm=json.loads(Path(prior_osm).read_text())
    base,changed,additions=previous_osm_tile_index(before,old_osm)
    oldkeys=all_zxy(old)
    if len(oldkeys)!=98152 or len(oldkeys)!=sum(before["candidate_tile_counts_by_zoom"].values()):
        raise AssertionError("Original 139-source national source candidate plan drift")
    newkeys=all_zxy(new)
    if not oldkeys.issubset(newkeys):
        raise AssertionError("140 COG source candidate plan removed original tiles")
    newly_planned=newkeys-oldkeys
    touched={tile for tile in newkeys if source_influenced(new[139],tile)}
    if not newly_planned.issubset(touched):
        raise AssertionError("New Tumaco candidate tiles missing from source-affected set")
    initial=defaultdict(Counter)
    for z,types in before["staged_by_zoom_native_DEM_tile_coverage"].items():
        initial[int(z)].update(types)
    after=defaultdict(Counter,{z:Counter(s) for z,s in initial.items()})
    missing_by_zoom=Counter({int(z):int(n) for z,n in
                             before["staged_by_zoom_missing_native_sample_pixels"].items()})
    recovered_by_zoom=Counter()
    newly_missing_by_zoom=Counter()
    transition=Counter()
    aggregate_osm_lo=aggregate_osm_hi=0
    aggregate_igac_lo=aggregate_igac_hi=0
    new_z13_unknown_missing=0
    affected_details=[]
    cache=Path(output).parent/"local-original-COG-cache"
    cache.mkdir(parents=True,exist_ok=True)
    opened={}
    try:
        for tile in sorted(touched):
            oldids,newids=selected_ids_for_new_source(old,new,tile)
            valid_old,h_old=native_mask(new,oldids,opened,cache,tile)
            valid_new,h_new=native_mask(new,newids,opened,cache,tile)
            added=compare_masks(valid_old,h_old,valid_new,h_new)
            old_scope=tile in oldkeys
            if tile[0]<=6:
                if not old_scope:
                    raise AssertionError("Unexpected entirely new world tile at low zoom")
                if not guaranteed_outside_all_COGs(tile,new):
                    raise AssertionError("Cannot prove old/new lowzoom status stays incomplete")
                # All source inputs at z0-z6 were already incomplete in
                # independently audited 139 by-zoom counts.
                if initial[tile[0]].get("full_dem_coverage",0)!=0:
                    raise AssertionError("Missing per-tile lowzoom classification evidence")
                prior_cls=next(k for k,n in initial[tile[0]].items()
                               if n>0 and k!="full_dem_coverage")
                new_cls=prior_cls
                old_missing=None
                new_missing=None
            else:
                old_count=int(valid_old.sum())
                new_count=int(valid_new.sum())
                prior_cls=classify(old_count) if old_scope else None
                new_cls=classify(new_count)
                old_missing=P-old_count if old_scope else None
                new_missing=P-new_count
            if old_scope:
                if prior_cls!=new_cls:
                    after[tile[0]][prior_cls]-=1
                    after[tile[0]][new_cls]+=1
                    if after[tile[0]][prior_cls]<0:
                        raise AssertionError("139 original per-zoom coverage status overdecremented")
                    transition[(prior_cls,new_cls)]+=1
                recovered_by_zoom[tile[0]]+=added
                missing_by_zoom[tile[0]]-=added
            else:
                after[tile[0]][new_cls]+=1
                newly_missing_by_zoom[tile[0]]+=new_missing
                missing_by_zoom[tile[0]]+=new_missing
            row={
                "zxy":list(tile),"in_old_139_candidate_area":old_scope,
                "real_native_DEM_pixel_centers_recovered":added,
                "original_valid_heights_preserved":True,
                "old_tile_status":prior_cls,"new_tile_status":new_cls,
            }
            if tile[0]>=7:
                row.update({"old_native_NoData_pixels":old_missing,
                            "new_native_NoData_pixels":new_missing})
            if tile[0]==13:
                if old_scope:
                    land,igac=frozen_land_before(tile,old_missing,base,changed,additions)
                    rlo,rhi=rigorous_land_bounds(old_missing,land,added)
                    row["prior_139_missing_OSM_land_pixels"]=land
                    row["OSM_land_recovered_lower_bound"]=rlo
                    row["OSM_land_recovered_upper_bound"]=rhi
                    if igac is not None:
                        ilo,ihi=rigorous_land_bounds(old_missing,igac,added)
                        row["historic_IGAC_administrative_missing_recovered_lower_bound"]=ilo
                        row["historic_IGAC_administrative_missing_recovered_upper_bound"]=ihi
                        aggregate_igac_lo+=ilo
                        aggregate_igac_hi+=ihi
                    aggregate_osm_lo+=rlo;aggregate_osm_hi+=rhi
                else:
                    # Exact OSM geometry for added 140-only tiles wasn't
                    # in the old 137/139 incomplete tile audit. Keep
                    # possible OSM land as UNKNOWN, not invented zero.
                    new_z13_unknown_missing+=new_missing
                    row["new_140_only_OSM_land_membership"]="UNKNOWN_0_to_new_native_NoData"
            if tile[0]>=9 or added or not old_scope:
                affected_details.append(row)
    finally:
        for raster in opened.values():
            raster.close()
    for z in range(14):
        planned=sum(1 for t in newkeys if t[0]==z)
        if any(n<0 for n in after[z].values()):
            raise AssertionError("Negative staged tile category")
        if sum(after[z].values())!=planned or not 0<=missing_by_zoom[z]<=planned*P:
            raise AssertionError(f"Staged 140 tile count/pixels inconsistent at z{z}")
    previous_l=23878663
    old_l_lower=previous_l-aggregate_osm_hi
    old_l_upper=previous_l-aggregate_osm_lo
    if not 0<=old_l_lower<=old_l_upper:
        raise AssertionError("139->140 old-OSM pixel recovery bounds invalid")
    result={
        "status":"140_staged_native_139_to_140_incremental_actual_COG_pixel_result_NOT_release",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "source_change":"append original Tumaco N01_W080, first 139 unchanged",
        "prior_139_national_coverage_run":COVERAGE_RUN_139,
        "prior_137_exact_OSM_and_IGAC_pixel_run":OSM_RUN,
        "production_native_COG_count_unmodified":137,
        "prior_staging_COG_count":139,"new_staging_COG_count":140,
        "old_139_candidate_tiles":len(oldkeys),
        "new_140_candidate_tiles":len(newkeys),
        "new_source_only_candidate_tiles":len(newly_planned),
        "tiles_with_candidate_native_COG_footprint_recomputed":len(touched),
        "source_height_preservation_exact_for_all_affected_tiles":True,
        "true_native_pixel_centers_restored_in_prior_scope_by_zoom":{
            str(z):recovered_by_zoom[z] for z in range(14)},
        "new_140_scope_native_missing_pixels_by_zoom":{
            str(z):newly_missing_by_zoom[z] for z in range(14)},
        "new_140_missing_native_DEM_pixel_centers_by_zoom":{
            str(z):missing_by_zoom[z] for z in range(14)},
        "new_140_coverage_status_by_zoom":{
            str(z):dict(after[z]) for z in range(14)},
        "old_139_coverage_status_by_zoom":{
            str(z):dict(initial[z]) for z in range(14)},
        "full_or_partial_native_DEM_tile_transitions":{
            str(k):n for k,n in transition.items()},
        "reference_z13":{
            "old_139_missing_OSM_land_pixels_exact":previous_l,
            "restored_OSM_land_pixels_lower_bound":aggregate_osm_lo,
            "restored_OSM_land_pixels_upper_bound":aggregate_osm_hi,
            "remaining_original_139_scope_OSM_land_NoData_lower_bound":old_l_lower,
            "remaining_original_139_scope_OSM_land_NoData_upper_bound":old_l_upper,
            "new_140_only_tile_NoData_pixels_with_unknown_OSM_land_membership":new_z13_unknown_missing,
            "full_140_scope_remaining_OSM_land_NoData_lower_bound":old_l_lower,
            "full_140_scope_remaining_OSM_land_NoData_upper_bound":old_l_upper+new_z13_unknown_missing,
            "historic_IGAC_administrative_positive_recovered_lower_bound":aggregate_igac_lo,
            "historic_IGAC_administrative_positive_recovered_upper_bound":aggregate_igac_hi,
            "IGAC_not_refetched":True,
            "OSM_Coastline_polygon_download_not_repeated":True,
            "outside_OSM_reference_NOT_proven_ocean":True,
            "new_tumaco_COG_one_degree_extent_NOT_all_certified_Colombia_land":True,
        },
        "recomputed_z13_per_tile":[r for r in affected_details if r["zxy"][0]==13],
        "all_native_study_zoom_categories_reconciled":True,
        "no_national_137_shards_recomputed":True,
        "no_national_139_source_coverage_recomputed":True,
        "all_other_49_source_candidates_still_not_added":True,
        "no_MBtiles_or_Terrain_RGB_generated":True,
        "no_artificial_ocean_zero_DEM_or_bathymetry":True,
        "quitasueno_excluded":True,
        "national_Terrain_RGB_publication_allowed":False,
        "important_limit":"OSM land category stays rigorous bounds where full z13 OSM polygon mask absent; next true fine-land mask QA restricted to Tumaco if needed, never silently treating uncertainty as ocean.",
    }
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="recomputed_z13_per_tile"},
                     indent=2,ensure_ascii=False),flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--old",type=Path,default=Path("output/stage139/colombia_dem_manifest_island_staging_139.csv"))
    p.add_argument("--new",type=Path,default=Path("output/stage140/colombia_dem_manifest_tumaco_staging_140.csv"))
    p.add_argument("--old-report",type=Path,default=Path("output/stage139-coverage/national-staged-139-dem-and-osm-coverage.json"))
    p.add_argument("--old-osm",type=Path,default=Path("output/old-osm/osm-audit/osm-national-native-land-report.json"))
    p.add_argument("--output",type=Path,default=Path("output/tumaco-staging-140/tumaco-139-to-140-exact-increment.json"))
    a=p.parse_args()
    run(a.old,a.new,a.old_report,a.old_osm,a.output)


if __name__=="__main__":
    main()
