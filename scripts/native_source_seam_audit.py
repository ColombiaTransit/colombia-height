#!/usr/bin/env python3
"""Investigate the 6°N GLO-30 seam on the *native* source pixel grid.

Reads only 350 longitude samples per source cell, and six native rows
each side of latitude 6. No Web Mercator downsampling. Never modify COGs.
"""
import argparse
import json
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import rasterio
from medellin_terrain import source_tiles,download

BORDER_LAT=6.0
CELLS=(-75,-74)
SAMPLES=350
INTERIOR_ROWS=6

def stats(values):
    v=np.asarray(values,dtype=np.float64)
    v=v[np.isfinite(v)]
    return {"count":int(v.size),"maximum_m":round(float(v.max()),3) if v.size else None,
            "median_m":round(float(np.median(v)),3) if v.size else None,
            "p95_m":round(float(np.percentile(v,95)),3) if v.size else None,
            "p99_m":round(float(np.percentile(v,99)),3) if v.size else None}

def seam_metrics(south,north):
    """Arrays represent rows from boundary inward in each source (0 nearest).

    Cross = north[0] vs south[0]. Interior = each consecutive source
    pixel step, at the same native resolution.
    """
    if south.shape!=north.shape or south.ndim!=2 or south.shape[0]<2:
        raise ValueError("Incompatible native source strips")
    cross=np.abs(north[0]-south[0])
    inner_n=np.abs(np.diff(north,axis=0))
    inner_s=np.abs(np.diff(south,axis=0))
    valid=np.isfinite(cross)
    local=np.maximum(inner_n[0],inner_s[0])
    # Distinctly flag exceptional border steps but don't declare a
    # DEM defect solely because cross-step metres are large.
    flag=valid & (cross>40) & (cross>3*np.maximum(local,1))
    high=np.where(flag)[0]
    return {"native_cross_border":stats(cross),
            "north_interior_1_to_5_px":stats(inner_n),
            "south_interior_1_to_5_px":stats(inner_s),
            "border_over_100m":int(np.count_nonzero(cross[valid]>100)),
            "border_gt_40m_and_gt_3x_immediate_local_gradient":int(flag.sum()),
            "flagged_sample_indices":[int(x) for x in high[:15]],
            "valid_samples":int(valid.sum())}

def sample_strips(south,north,lon,lat=BORDER_LAT,rows=INTERIOR_ROWS):
    sy=abs(south.transform.e)
    ny=abs(north.transform.e)
    if not(0<sy<0.01 and 0<ny<0.01):
        raise ValueError("Unexpected native pixel resolution")
    if abs(sy-ny)>max(sy,ny)*.01:
        raise ValueError("Different source resolution; needs separate alignment")
    lon=np.asarray(lon,dtype=float)
    strips=[]
    for dataset,sign,res in ((south,-1,sy),(north,1,ny)):
        rowarrays=[]
        for k in range(rows):
            coords=[(float(x),lat+sign*(k+.5)*res) for x in lon]
            samples=list(dataset.sample(coords,masked=True))
            a=np.ma.array(samples).reshape(-1)
            rowarrays.append(np.ma.filled(a.astype(np.float64),np.nan))
        strips.append(np.asarray(rowarrays))
    return strips[0],strips[1],(sy+ny)/2

def inspect_cell(cell,cache):
    expected={(lat,lon):v for v in source_tiles((cell+.05,5.9,cell+.95,6.1))
              for lat,lon in [(v["latitude"],v["longitude"])]}
    south_info=expected.get((5,cell))
    north_info=expected.get((6,cell))
    if south_info is None or north_info is None:
        raise RuntimeError(f"Missing source degree cells N05/N06 at longitude {cell}")
    paths=[]
    cache.mkdir(parents=True,exist_ok=True)
    for info in (south_info,north_info):
        path=cache/(info["name"]+".tif")
        download(info["url"],path)
        paths.append(path)
    with rasterio.open(paths[0]) as s,rasterio.open(paths[1]) as n:
        lon=np.linspace(cell+.08,cell+.92,SAMPLES)
        if not(s.bounds.top>=BORDER_LAT and n.bounds.bottom<=BORDER_LAT):
            raise ValueError("Unexpected source latitude edges")
        southern,northern,res=sample_strips(s,n,lon)
        result=seam_metrics(southern,northern)
        result.update({
            "longitude_degree_cell":cell,"latitude_boundary":BORDER_LAT,
            "source_south":south_info["name"],"source_north":north_info["name"],
            "source_native_resolution_deg":res,
            "approx_native_lat_step_m":round(res*111132,2),
            "extreme_examples":[
                {"lon":round(float(lon[i]),6),
                 "south_border_height_m":round(float(southern[0,i]),3),
                 "north_border_height_m":round(float(northern[0,i]),3),
                 "delta_m":round(float(abs(northern[0,i]-southern[0,i])),3),
                 "south_first_inside_step_m":round(float(abs(southern[1,i]-southern[0,i])),3),
                 "north_first_inside_step_m":round(float(abs(northern[1,i]-northern[0,i])),3)}
                for i in np.argsort(np.nan_to_num(abs(northern[0]-southern[0]),nan=-1))[-8:][::-1]
            ]
        })
    return result

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,default=Path("output/native-source-seam"))
    a=ap.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    cells=[inspect_cell(c,a.output/"sources") for c in CELLS]
    report={"generated_utc":datetime.now(timezone.utc).isoformat(),
            "status":"native_resolution_seam_audited",
            "cells":cells,"publication_allowed":False,
            "interpretation":"A large ~z10 pixel gradient is not proof of native COG seam corruption; inspect source-pixel continuity. Flags are evidence for review, not automatic height edits."}
    (a.output/"native-seam-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"results":[{"cell":r["longitude_degree_cell"],
                                  "native_border":r["native_cross_border"],
                                  "flagged":r["border_gt_40m_and_gt_3x_immediate_local_gradient"],
                                  "extremes":r["extreme_examples"][:3]} for r in cells],
                      "publication_allowed":False},indent=2),flush=True)

if __name__=="__main__":
    main()
