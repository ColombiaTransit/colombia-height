#!/usr/bin/env python3
"""One NEW Tumaco native longitudinal COG source seam check (79°W).

Existing 24-tile GLO-30 native restoration and IGAC evidence are reused
from immutable run 43497684367. No re-running original 24 z13 tile masks,
national DEM/OSM, islands, extra sources, or MBTiles.

Check the native 30 m western N01_W080 source against the existing
selected eastern N01_W079 COG at longitude -79 (not a latitudinal join).
Every previously valid source height remains untouched; if the seam
signals unusual gradients they remain diagnostic only, not smoothed.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio

from coastal_audit import index_sources
from medellin_terrain import download
from national_tile_plan import parse_manifest
from native_source_seam_audit import seam_metrics

WEST="Copernicus_DSM_COG_10_N01_00_W080_00_DEM"
EAST="Copernicus_DSM_COG_10_N01_00_W079_00_DEM"
LONGITUDE_EDGE=-79.
SAMPLE_POINTS=350
ROW_DEPTH=6
LATS=(1.05,1.95)
VERIFIED_NATIVE_RECOVERY_RUN=43497684367


def sample_longitude_border(west,east,latitudes,depth=ROW_DEPTH):
    """Sample six TRUE native pixel columns inward from each COG's boundary."""
    wx=abs(west.transform.a)
    ex=abs(east.transform.a)
    if west.crs.to_epsg()!=4326 or east.crs.to_epsg()!=4326:
        raise AssertionError("Wrong DEM native EPSG:4326 coordinate reference")
    if not (0<wx<0.01 and 0<ex<0.01 and abs(wx-ex)<max(wx,ex)*.01):
        raise AssertionError("Native ~30m horizontal source resolution unexpected")
    if (abs(west.bounds.right-LONGITUDE_EDGE)>3*wx or
            abs(east.bounds.left-LONGITUDE_EDGE)>3*ex):
        raise AssertionError("COG native source seam far from 79°W")
    latitudes=np.asarray(latitudes,dtype=float)
    strips=[]
    for raster,edge,direction,res in (
        (west,west.bounds.right,-1.,wx),
        (east,east.bounds.left,+1.,ex)):
        sampled=[]
        for k in range(depth):
            lon=edge+direction*(k+.5)*res
            points=[(lon,float(lat)) for lat in latitudes]
            a=np.ma.array(list(raster.sample(points,masked=True))).reshape(-1)
            samples=np.ma.filled(a.astype(float),np.nan)
            if raster.nodata is not None:
                samples[np.isclose(samples,float(raster.nodata))]=np.nan
            sampled.append(samples)
        strips.append(np.array(sampled))
    return strips[0],strips[1],(wx+ex)/2


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    p.add_argument("--output",type=Path,default=Path("output/tumaco-native-source-edge/tumaco-native-longitude-seam.json"))
    a=p.parse_args()
    source=parse_manifest(a.manifest)
    selected={r["name"] for r in source}
    if len(source)!=137 or WEST in selected or EAST not in selected:
        raise AssertionError("Frozen selected 137-source inventory incorrectly includes/excludes Tumaco border sources")
    catalog={r["name"]:r for r in index_sources().values()}
    if not {WEST,EAST}.issubset(catalog):
        raise AssertionError("Public original GLO-30 source catalog incomplete")
    root=a.output.parent;root.mkdir(parents=True,exist_ok=True)
    cache=root/"native-source-cache";cache.mkdir(parents=True,exist_ok=True)
    source_paths={}
    for name in (WEST,EAST):
        item=catalog[name]
        target=cache/(name+".tif")
        download(item["url"],target)
        source_paths[name]=target
    with rasterio.open(source_paths[WEST]) as west,rasterio.open(source_paths[EAST]) as east:
        lats=np.linspace(*LATS,SAMPLE_POINTS)
        arows,brows,res=sample_longitude_border(west,east,lats)
        metrics=seam_metrics(arows,brows)
        values=metrics["native_cross_border"]
        result={
            "status":"one_targeted_Tumaco_N01_W080_to_original_N01_W079_native_30m_source_seam_evidence",
            "checked_utc":datetime.now(timezone.utc).isoformat(),
            "source_west_candidate_not_in_existing_inventory":WEST,
            "source_east_original_137_selected":EAST,
            "source_boundary_longitude":LONGITUDE_EDGE,
            "source_native_resolution_deg":res,
            "latitude_sample_range":list(LATS),
            "number_of_boundary_latitude_samples":SAMPLE_POINTS,
            "inward_native_columns_each_side":ROW_DEPTH,
            "actual_native_boundary_west_source_right":west.bounds.right,
            "actual_native_boundary_east_source_left":east.bounds.left,
            "horizontal_georeference_gap_m_at_equator_approx":(east.bounds.left-west.bounds.right)*111320.,
            "original_24tile_Tumaco_native_recovery_verified_run":VERIFIED_NATIVE_RECOVERY_RUN,
            "IGAC_dept_positive_native_recovery_was_previously_verified":True,
            "seam_statistics":metrics,
            "border_native_valid_samples_present":values["count"]>0,
            "native_gradient_flag_does_not_automatically_reject_source":True,
            "no_original_source_elevation_modified":True,
            "only_existing_two_native_COGs_downloaded":True,
            "no_redundant_national_or_24tile_native_audit":True,
            "source_auto_added_to_139_staging":False,
            "source_countrywide_publication_allowed":False,
            "synthetic_ocean_or_bathymetry_created":False,
            "quitasueno_excluded":True,
        }
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(result,indent=2,ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
