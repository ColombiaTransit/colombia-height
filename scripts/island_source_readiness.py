#!/usr/bin/env python3
"""Read-only release-gate research for two omitted island COGs and minor islets.

Checks real native DEM per-tile coverage at z11-z13 around Malpelo and Gorgona
(including the 4 N and 3 N degree borders), then real native pixel samples
on eight previously registered Natural Earth 10m minor-island polygons.

A DEM cell footprint or named island point does NOT establish sovereignty,
or guarantee DEM validity. No synthetic ocean values. No source promotion.
"""
import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import numpy as np
from shapely import contains_xy
from shapely.geometry import Point
from shapely.strtree import STRtree

from coastal_audit import index_sources
from extend_inventory import NE_SOURCES, ne_shapes
from island_native_recovery_qa import xyz_centers
from national_dem_coverage import intersecting_source_indices, local_cogs
from national_tile_plan import parse_manifest
from two_cog_seam_pilot import warp_sources

SITES = {
    "malpelo": {"cog": "Copernicus_DSM_COG_10_N03_00_W082_00_DEM",
                "probe": (-81.606, 4.005), "degree_border": (-81.606, 4.0)},
    "gorgona": {"cog": "Copernicus_DSM_COG_10_N03_00_W079_00_DEM",
                "probe": (-78.18, 2.97), "degree_border": (-78.18, 3.0)},
}
NO_DATA = -9999.
EXPECTED_MINOR = 8
ZOOMS = (11, 12, 13)


def tiles_for_checks(site):
    """Deterministic, bounded nearby tiles at three levels incl. source border."""
    tiles = set()
    for z in ZOOMS:
        for lon, lat in (site["probe"], site["degree_border"]):
            t = mercantile.tile(lon, lat, z)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    tiles.add((z, t.x+dx, t.y+dy))
    if len(tiles) > 54 or not tiles:
        raise AssertionError("Island source seam test unexpectedly broad")
    return sorted(tiles)


def render_with_owner(sources, opened, cache, tile):
    ids = intersecting_source_indices(sources, *tile)
    if not ids:
        empty = np.full((256,256), NO_DATA, dtype=np.float32)
        return empty, np.zeros((256,256), dtype=bool), np.zeros((256,256), dtype=np.uint8), []
    handles = local_cogs(sources, ids, cache, opened)
    dem, prov, overlaps, overlap_delta = warp_sources(handles, tile)
    valid = (prov > 0) & np.isfinite(dem) & (dem != NO_DATA)
    # Native source provenance is local to the tile; idx=1 means ids[0].
    owners = [sources[i]["name"] for i in ids]
    return dem, valid, prov, owners


def check_added_source_preserves_original(before_dem, before_valid,
                                          after_dem, after_valid):
    arrays = [np.asarray(x) for x in
              (before_dem,before_valid,after_dem,after_valid)]
    if any(x.shape != (256,256) for x in arrays):
        raise ValueError("Source masks/heights are not aligned on exact 256x256 XYZ grids")
    if np.any(before_valid & ~after_valid):
        raise AssertionError("Previously valid original DEM pixels were lost")
    shared = before_valid & after_valid
    max_changed = (float(np.max(np.abs(before_dem[shared]-after_dem[shared])))
                   if np.any(shared) else 0.)
    if not np.isfinite(max_changed) or max_changed > .001:
        raise AssertionError("Existing native GLO-30 heights changed")
    recovered = ~before_valid & after_valid
    return {
        "before_missing_pixels":int(np.count_nonzero(~before_valid)),
        "recovered_genuine_native_pixels":int(np.count_nonzero(recovered)),
        "after_missing_pixels":int(np.count_nonzero(~after_valid)),
        "max_original_height_delta_m":max_changed,
    }


def transition_metrics(heights, valid, provenance, owner_names, extra_name):
    """Quantify observed source joins; gradients are evidence, not an error."""
    if heights.shape!=(256,256) or valid.shape!=heights.shape or provenance.shape!=heights.shape:
        raise ValueError("Unaligned provenance or DEM grid")
    local_ids={i+1 for i,n in enumerate(owner_names) if n==extra_name}
    if len(local_ids)>1:
        raise AssertionError("Candidate COG listed repeatedly")
    if not local_ids:
        return {"candidate_valid_pixels":0, "candidate_original_transition_pairs":0,
                "max_transition_gradient_m":None, "flags_grad_gt40m":0,
                "transition_incomplete_adjacent_pixels":0}
    cid=next(iter(local_ids))
    candidate=(provenance==cid) & valid
    pairs=0
    flags=0
    max_delta=None
    for y0,y1,x0,x1 in (
        (slice(None),slice(None),slice(None,-1),slice(1,None)),
        (slice(None,-1),slice(1,None),slice(None),slice(None))):
        a=provenance[y0,x0]
        b=provenance[y1,x1]
        good=valid[y0,x0]&valid[y1,x1]
        crossing=good&(((a==cid)&(b!=cid)&(b!=0))|((b==cid)&(a!=cid)&(a!=0)))
        ds=np.abs(heights[y0,x0]-heights[y1,x1])[crossing]
        if ds.size:
            pairs+=int(ds.size)
            flags+=int(np.count_nonzero(ds>40.))
            value=float(ds.max())
            max_delta=value if max_delta is None else max(max_delta,value)
    # Missing adjacent original/candidate samples are not automatically ocean.
    missing_near=0
    for start,end in ((candidate[:,:-1],valid[:,1:]),(candidate[:,1:],valid[:,:-1]),
                      (candidate[:-1,:],valid[1:,:]),(candidate[1:,:],valid[:-1,:])):
        missing_near+=int(np.count_nonzero(start & ~end))
    return {
        "candidate_valid_pixels":int(candidate.sum()),
        "candidate_original_transition_pairs":pairs,
        "max_transition_gradient_m":round(max_delta,3) if max_delta is not None else None,
        "flags_grad_gt40m":flags,
        "transition_incomplete_adjacent_pixels":missing_near,
        "gradient_flag_is_not_an_automatic_source_failure":True,
    }


def run_seams(selected,catalog,cache):
    original={s["name"] for s in selected}
    records=[]
    summary={}
    opened={}
    try:
        for site,info in SITES.items():
            name=info["cog"]
            if name in original or name not in catalog:
                raise AssertionError("Missing or already selected candidate")
            cog=catalog[name]
            augmented=selected+[{
                "name":name,"latitude":str(cog["latitude"]),
                "longitude":str(cog["longitude"]),"url":cog["url"],
                "status":"investigation_only_not_selected"}]
            stats=Counter()
            max_height_change=0.
            max_gradient=None
            for tile in tiles_for_checks(info):
                before,valid_b,_,_=render_with_owner(selected,opened,cache,tile)
                after,valid_a,prov,owners=render_with_owner(augmented,opened,cache,tile)
                diag=check_added_source_preserves_original(before,valid_b,after,valid_a)
                trans=transition_metrics(after,valid_a,prov,owners,name)
                for k in ("before_missing_pixels","recovered_genuine_native_pixels",
                          "after_missing_pixels"):
                    stats[k]+=diag[k]
                for k in ("candidate_valid_pixels","candidate_original_transition_pairs",
                          "flags_grad_gt40m","transition_incomplete_adjacent_pixels"):
                    stats[k]+=trans[k]
                max_height_change=max(max_height_change,diag["max_original_height_delta_m"])
                if trans["max_transition_gradient_m"] is not None:
                    max_gradient=(trans["max_transition_gradient_m"] if max_gradient is None
                                  else max(max_gradient,trans["max_transition_gradient_m"]))
                stats["checked_tiles"]+=1
                stats["tiles_where_candidate_adds_native_pixels"]+=int(
                    diag["recovered_genuine_native_pixels"]>0)
                records.append({"site":site,"zxy":list(tile),**diag,**trans})
            summary[site]={
                "candidate_source":name,**dict(stats),
                "max_original_height_delta_m":max_height_change,
                "max_observed_source_transition_gradient_m":max_gradient,
                "original_137_manifest_modified":False,
                "border_visited":list(info["degree_border"]),
            }
            # Crucial: extra source index 137 is reused for another candidate.
            # Closing prevents the two source files being aliased in cache.
            temp=opened.pop(137,None)
            if temp is not None:
                temp.close()
    finally:
        for dataset in opened.values():
            dataset.close()
    for site,stat in summary.items():
        if stat["checked_tiles"]<20 or stat["recovered_genuine_native_pixels"]==0:
            raise AssertionError(f"No bounded multi-zoom real-DEM test for {site}")
    return summary,records


def sample_one_native_height(dataset,lon,lat):
    """Sample original 30m source grid; do not use z13 warp as native 30m proof."""
    if not (dataset.bounds.left<=lon<dataset.bounds.right and
            dataset.bounds.bottom<=lat<dataset.bounds.top):
        return {"status":"probe_outside_original_COG_geotransform","height_m":None}
    v=next(dataset.sample([(float(lon),float(lat))],masked=True))[0]
    if np.ma.is_masked(v) or not np.isfinite(float(v)):
        return {"status":"native_COG_NoData","height_m":None}
    n=float(v)
    if dataset.nodata is not None and np.isclose(n,float(dataset.nodata)):
        return {"status":"native_COG_NoData","height_m":None}
    return {"status":"native_COG_valid","height_m":n}


def minor_reference_polygon(point,polygons,index):
    hits=[polygons[int(i)] for i in index.query(point)
          if polygons[int(i)].covers(point)]
    if not hits:
        return None
    return min(hits,key=lambda v:v.area)


def run_minor_islands(selected,review_path,cache):
    data=json.loads(Path(review_path).read_text())
    cases=data["candidates"]
    if len(cases)!=EXPECTED_MINOR or len(set(x["id"] for x in cases))!=EXPECTED_MINOR:
        raise AssertionError("Original eight-island source study changed")
    shapes=ne_shapes(NE_SOURCES["ne_10m_minor_islands"])
    tree=STRtree(shapes)
    by_name={s["name"]:i for i,s in enumerate(selected)}
    opened={}
    results=[]
    try:
        for case in cases:
            name=case["expected_cog"]
            if name not in by_name:
                raise AssertionError(f"Original 137 source omitted minor-island cell {name}")
            lon,lat=case["center_lon"],case["center_lat"]
            point=Point(float(lon),float(lat))
            geom=minor_reference_polygon(point,shapes,tree)
            source=local_cogs(selected,[by_name[name]],cache,opened)[0]
            native=sample_one_native_height(source,lon,lat)
            result={
                "id":case["id"],"reference_group":case["near_registry_id"],
                "expected_original_selected_COG":name,"native_probe":native,
                "Natural_Earth_minor_land_point_in_polygon":geom is not None,
                "NE_minor_polygon_not_official_colombian_territory":True,
                "z13_polygon_tile_count":None,
                "z13_polygon_land_pixels":None,
                "z13_polygon_missing_native_pixels":None,
                "requires_source_review":True,
            }
            if geom is not None:
                if geom.area>0.01:
                    result["polygon_status"]="reference_geometry_unexpectedly_large"
                else:
                    west,south,east,north=geom.bounds
                    tiles={(13,t.x,t.y) for t in mercantile.tiles(
                        west+1e-9,south+1e-9,east-1e-9,north-1e-9,zooms=[13])}
                    if len(tiles)>20:
                        result["polygon_status"]="exceeds_bounded_island_pixel_inspection"
                    else:
                        land_total=missing_total=0
                        for tile in sorted(tiles):
                            xx,yy=xyz_centers(tile)
                            inside=np.asarray(contains_xy(geom,xx.ravel(),yy.ravel()),
                                              dtype=bool).reshape((256,256))
                            if not np.any(inside):
                                continue
                            ds=intersecting_source_indices(selected,*tile)
                            handles=local_cogs(selected,ds,cache,opened) if ds else []
                            if handles:
                                dem,prov,_,_=warp_sources(handles,tile)
                                valid=(prov>0)&np.isfinite(dem)&(dem!=NO_DATA)
                            else:
                                valid=np.zeros((256,256),bool)
                            land_total+=int(np.count_nonzero(inside))
                            missing_total+=int(np.count_nonzero(inside&~valid))
                        result.update({
                            "polygon_status":"observed_NE_minor_reference_geometry",
                            "z13_polygon_tile_count":len(tiles),
                            "z13_polygon_land_pixels":land_total,
                            "z13_polygon_missing_native_pixels":missing_total,
                            "requires_source_review":bool(missing_total or not land_total),
                        })
            results.append(result)
    finally:
        for ds in opened.values():
            ds.close()
    if len(results)!=8:
        raise AssertionError("Missing minor island studies")
    return results


def run(manifest,review,output):
    selected=parse_manifest(manifest)
    if len(selected)!=137:
        raise AssertionError("137-source baseline changed")
    catalog={c["name"]:c for c in index_sources().values()}
    root=Path(output).parent
    root.mkdir(parents=True,exist_ok=True)
    cache=root/"native-cog-cache"
    cache.mkdir(parents=True,exist_ok=True)
    seams,seam_tiles=run_seams(selected,catalog,cache)
    small=run_minor_islands(selected,review,cache)
    report={
        "status":"two_island_sources_and_eight_minor_islands_native_readiness_audit",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "original_selected_COG_count":137,
        "temporarily_added_COGs":{k:v["cog"] for k,v in SITES.items()},
        "island_seam_native_COG_summary":seams,
        "island_source_per_tile_metrics":seam_tiles,
        "eight_minor_island_source_checks":small,
        "island_reference_source":NE_SOURCES["ne_10m_minor_islands"],
        "eight_minor_islands_only_provisional_Natural_Earth_geography":True,
        "extra_COGs_approved_or_added":0,
        "national_publication_allowed":False,
        "original_native_height_samples_preserved":True,
        "artificial_height_or_ocean_fill_pixels":0,
        "quitasueno_excluded":True,
        "note":"Source-transition gradients >40m are diagnostic only, not proof of bad terrain; matching source coverage is not Colombian jurisdiction.",
    }
    out=Path(output)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="island_source_per_tile_metrics"},
                     indent=2,ensure_ascii=False),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    parser.add_argument("--minor",type=Path,default=Path("data/minor-island-review.json"))
    parser.add_argument("--output",type=Path,default=Path("output/island-source-readiness/island-source-readiness.json"))
    args=parser.parse_args()
    run(args.manifest,args.minor,args.output)


if __name__=="__main__":
    main()
