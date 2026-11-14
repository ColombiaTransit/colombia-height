#!/usr/bin/env python3
"""Native COG recovery test for the single remaining named-island source lead.

Study Copernicus_DSM_COG_10_N03_00_W079_00_DEM, 47 existing z13
incomplete tiles near northern edge of the Gorgona/Gorgonilla study
area. Do NOT claim this whole COG cell belongs to Colombia.

Without redownloading OSM geometry, compute mathematically rigorous
lower/upper bounds on recovered OSM-land pixels from the prior exact
cell-pixel count and the exact native COG recovery mask. No synthetic
heights; original valid height samples must remain unchanged.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import numpy as np
from rasterio.warp import transform

from coastal_audit import index_sources
from national_tile_plan import parse_manifest
from source_scope_comparison import render_valid

TARGET = "Copernicus_DSM_COG_10_N03_00_W079_00_DEM"
EXPECTED_TILES=47
EXPECTED_OSM_LAND_MISSING=747
BASELINE_RUN=43573144549
NODATA=-9999.0


def cell_mask(tile):
    z,x,y=tile
    bounds=mercantile.xy_bounds(x,y,z)
    xx=bounds.left+(np.arange(256)+.5)*(bounds.right-bounds.left)/256
    yy=bounds.top-(np.arange(256)+.5)*(bounds.top-bounds.bottom)/256
    mx,my=np.meshgrid(xx,yy)
    lon,lat=transform("EPSG:3857","EPSG:4326",mx.ravel(),my.ravel())
    return ((np.floor(np.asarray(lon)).reshape((256,256))==-79)
            &(np.floor(np.asarray(lat)).reshape((256,256))==3))


def strict_native_recovery(before_valid,before_height,after_valid,after_height,in_cell,
                           prior_missing_cell,prior_osm_missing_cell):
    """Bound actual OSM-pixel recovery without rematerializing OSM polygons.

    Of N missing native pixels inside a source cell, O are known to be
    inside an OSM polygon. If R native pixels are recovered, between
    max(0,R-(N-O)) and min(R,O) recovered pixels were on OSM land.
    """
    arrays=(before_valid,before_height,after_valid,after_height,in_cell)
    if any(np.asarray(a).shape!=(256,256) for a in arrays):
        raise ValueError("Unaligned DEM/native-cell array")
    before_valid,after_valid,in_cell=[np.asarray(a,dtype=bool)
                                      for a in (before_valid,after_valid,in_cell)]
    before_height=np.asarray(before_height)
    after_height=np.asarray(after_height)
    if not (0<=prior_osm_missing_cell<=prior_missing_cell<=65536):
        raise AssertionError("Invalid original native/OSM pixel counts")
    baseline_cell=int(np.count_nonzero(~before_valid&in_cell))
    if baseline_cell!=prior_missing_cell:
        raise AssertionError("Native missing source cell differs from frozen OSM baseline")
    lost=before_valid&~after_valid
    if np.any(lost):
        raise AssertionError("A previously valid native DEM height vanished")
    common=before_valid&after_valid
    max_diff=(float(np.max(np.abs(before_height[common]-after_height[common])))
              if np.any(common) else 0.)
    if not np.isfinite(max_diff) or max_diff>.001:
        raise AssertionError("Previously valid native elevation changed")
    recovered=(~before_valid)&after_valid
    rcell=int(np.count_nonzero(recovered&in_cell))
    if rcell>prior_missing_cell:
        raise AssertionError("Impossible recovered pixels inside degree cell")
    return {
        "before_native_missing_pixels":int(np.count_nonzero(~before_valid)),
        "after_native_missing_pixels":int(np.count_nonzero(~after_valid)),
        "native_pixels_recovered":int(np.count_nonzero(recovered)),
        "native_pixels_recovered_inside_source_degree_cell":rcell,
        "prior_native_missing_inside_degree_cell":prior_missing_cell,
        "prior_OSM_land_missing_inside_degree_cell":prior_osm_missing_cell,
        "recovered_OSM_land_pixels_lower_bound":max(0,rcell-(prior_missing_cell-prior_osm_missing_cell)),
        "recovered_OSM_land_pixels_upper_bound":min(rcell,prior_osm_missing_cell),
        "max_existing_valid_native_height_change_m":max_diff,
        "OSM_land_recovery_bounds_not_direct_polygon_retest":True,
        "all_original_valid_elevations_preserved":True,
    }


def run(manifest,osm_json,output):
    baseline=json.loads(Path(osm_json).read_text())
    if (baseline.get("mode")!="national" or baseline.get("tiles_checked")!=1917
            or baseline.get("source_candidate_total")!=52
            or baseline.get("selected_source_cogs")!=137
            or baseline.get("national_publication_allowed") is not False):
        raise AssertionError("Original full OSM z13 QA baseline missing")
    selected=parse_manifest(manifest)
    if len(selected)!=137 or TARGET in {s["name"] for s in selected}:
        raise AssertionError("Target must be absent from original 137 COG selection")
    targets=[]
    for row in baseline["per_tile"]:
        candidate=(row.get("per_candidate_omitted_cog") or {}).get(TARGET)
        if candidate is not None:
            targets.append((row,candidate))
    if len(targets)!=EXPECTED_TILES or sum(c["osm_land_missing_pixel_cell_hits"] for _,c in targets)!=EXPECTED_OSM_LAND_MISSING:
        raise AssertionError("Unexpected Gorgona vicinity candidate baseline tile/pixel counts")
    catalog=index_sources()
    match=next((c for c in catalog.values() if c["name"]==TARGET),None)
    if match is None:
        raise RuntimeError("Official public Copernicus catalog no longer lists target source")
    augmented=selected+[{
        "name":TARGET, "latitude":str(match["latitude"]),
        "longitude":str(match["longitude"]),"url":match["url"],
        "status":"investigation_only_not_selected",
    }]
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    cache=output.parent/"native-cog-cache"
    cache.mkdir(exist_ok=True)
    opened={}
    rows=[]
    try:
        for original,previous in targets:
            tile=(original["z"],original["x"],original["y"])
            before_valid,before_height=render_valid(selected,opened,cache,tile)
            after_valid,after_height=render_valid(augmented,opened,cache,tile)
            if int(np.count_nonzero(~before_valid))!=original["native_missing_dem_pixels"]:
                raise AssertionError(f"Native baseline changed at {tile}")
            result=strict_native_recovery(
                before_valid,before_height,after_valid,after_height,cell_mask(tile),
                int(previous["native_missing_pixel_cell_hits"]),
                int(previous["osm_land_missing_pixel_cell_hits"]),
            )
            result["zxy"]=list(tile)
            rows.append(result)
            print("NATIVE_GORGONA_EDGE",tile,"recovered",result["native_pixels_recovered"],
                  "OSM land recovery bounds",
                  result["recovered_OSM_land_pixels_lower_bound"],
                  result["recovered_OSM_land_pixels_upper_bound"],flush=True)
    finally:
        for dataset in opened.values():
            dataset.close()
    totals={key:sum(x[key] for x in rows) for key in (
        "before_native_missing_pixels","after_native_missing_pixels",
        "native_pixels_recovered","native_pixels_recovered_inside_source_degree_cell",
        "prior_native_missing_inside_degree_cell","prior_OSM_land_missing_inside_degree_cell",
        "recovered_OSM_land_pixels_lower_bound","recovered_OSM_land_pixels_upper_bound")}
    if totals["prior_OSM_land_missing_inside_degree_cell"]!=EXPECTED_OSM_LAND_MISSING:
        raise AssertionError("OSM land references drifted")
    if totals["native_pixels_recovered"] != (
            totals["before_native_missing_pixels"]-totals["after_native_missing_pixels"]):
        raise AssertionError("Native DEM pixel recovery totals do not reconcile")
    report={
        "status":"Gorgona_vicinity_unselected_native_COG_elevation_recovery_QA",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "candidate_COG":TARGET,
        "original_selected_source_count":137,
        "temporary_extra_sources_tested":1,
        "target_candidate_z13_tile_count":len(rows),
        "original_OSM_run":BASELINE_RUN,
        "native_pixel_and_OSM_land_recovery_bound_totals":totals,
        "existing_native_elevation_max_difference_m":max(
            x["max_existing_valid_native_height_change_m"] for x in rows),
        "every_original_valid_elevation_preserved":all(
            x["all_original_valid_elevations_preserved"] for x in rows),
        "this_is_not_a_direct_OSM_land_polygon_raster_retest":True,
        "Gorgona_study_proximity_is_not_territorial_jurisdiction":True,
        "COG_source_added_to_production_manifest":False,
        "synthetic_heights_added":0,
        "national_publication_allowed":False,
        "per_tile":rows,
    }
    target=output/"gorgona-n03-w079-native-recovery.json"
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="per_tile"},indent=2),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    p.add_argument("--osm",type=Path,default=Path("output/osm-audit/osm-national-native-land-report.json"))
    p.add_argument("--output",type=Path,default=Path("output/gorgona-source-qa"))
    a=p.parse_args()
    run(a.manifest,a.osm,a.output)


if __name__=="__main__":
    main()
