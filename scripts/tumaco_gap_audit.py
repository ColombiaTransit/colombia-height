#!/usr/bin/env python3
"""Locate Tumaco z11 DEM gaps by exact z/x/y and original COG mask.

Missing output pixels are NOT filled or published. Use Natural Earth as
a reference for pixel positions, not as a legally valid ocean classifier.
"""
import argparse
import json
from contextlib import ExitStack
from datetime import datetime,timezone
from pathlib import Path
import mercantile
import numpy as np
from shapely.geometry import box
from shapely.ops import unary_union
from rasterio.warp import transform
from coastal_terrain_pilot import reference_mask,load_land_reference
from two_cog_seam_pilot import warp_sources,open_sources,source_files

SITE=(-78.76,1.81)
ZOOM=11
SIZE=256

def extent_of_mask(mask,bounds):
    y,x=np.where(mask)
    if not y.size:
        return None
    # bounds are Web Mercator meters; convert mask outer edges back to WGS84.
    x0=bounds.left+float(x.min())/SIZE*(bounds.right-bounds.left)
    x1=bounds.left+float(x.max()+1)/SIZE*(bounds.right-bounds.left)
    y_top=bounds.top-float(y.min())/SIZE*(bounds.top-bounds.bottom)
    y_bottom=bounds.top-float(y.max()+1)/SIZE*(bounds.top-bounds.bottom)
    lon,lat=transform("EPSG:3857","EPSG:4326",[x0,x1],[y_bottom,y_top])
    return [round(lon[0],7),round(lat[0],7),round(lon[1],7),round(lat[1],7)]

def classify_native_source_point(sources,lon,lat):
    inside=[s for s in sources if s.bounds.left<=lon<s.bounds.right
            and s.bounds.bottom<=lat<s.bounds.top]
    if not inside:
        return "outside_downloaded_COG_extents"
    for src in inside:
        sample=next(src.sample([(lon,lat)],masked=True))
        item=np.ma.array(sample)
        if not np.any(np.ma.getmaskarray(item)) and np.isfinite(item[0]):
            return "native_source_pixel_valid_but_warp_missing"
    return "inside_COG_extent_but_native_nodata"

def classify_missing_pixel_samples(sources,mask,bounds,limit=64):
    y,x=np.where(mask)
    if not y.size:
        return {"sample_count":0,"sample_categories":{},"example_points":[]}
    indexes=np.unique(np.linspace(0,len(y)-1,min(limit,len(y)),dtype=int))
    categories={}
    examples=[]
    for i in indexes:
        px,py=int(x[i]),int(y[i])
        merc_x=bounds.left+(px+.5)/SIZE*(bounds.right-bounds.left)
        merc_y=bounds.top-(py+.5)/SIZE*(bounds.top-bounds.bottom)
        lon,lat=transform("EPSG:3857","EPSG:4326",[merc_x],[merc_y])
        category=classify_native_source_point(sources,lon[0],lat[0])
        categories[category]=categories.get(category,0)+1
        if len(examples)<12:
            examples.append({"lon":round(float(lon[0]),7),"lat":round(float(lat[0]),7),"category":category})
    return {"sample_count":len(indexes),"sample_categories":categories,"example_points":examples}

def audit(output):
    center=mercantile.tile(*SITE,ZOOM)
    tiles=[(ZOOM,center.x+dx,center.y+dy) for dy in (-1,0,1) for dx in (-1,0,1)]
    bb=[mercantile.bounds(x,y,ZOOM) for _,x,y in tiles]
    bbox=(min(b.west for b in bb),min(b.south for b in bb),
          max(b.east for b in bb),max(b.north for b in bb))
    names,paths=source_files(bbox,output/"sources")
    land=load_land_reference()
    local_geometry=unary_union([g for g in land if g.intersects(box(*bbox))])
    details=[]
    with ExitStack() as stack:
        sources=open_sources(paths,stack)
        for tile in tiles:
            heights,provenance,overlaps,delta=warp_sources(sources,tile)
            invalid=(provenance==0)|(~np.isfinite(heights))
            bounds=mercantile.xy_bounds(tile[1],tile[2],ZOOM)
            reference_land=reference_mask(bounds,local_geometry)
            n=int(invalid.sum())
            row={"xyz":list(tile),"tms_y":(1<<ZOOM)-1-tile[2],
                 "tile_bounds_lonlat":[round(v,7) for v in mercantile.bounds(tile)],
                 "missing_pixels":n,
                 "missing_inside_Natural_Earth_land":int((invalid&reference_land).sum()),
                 "missing_outside_Natural_Earth_land":int((invalid&~reference_land).sum()),
                 "missing_pixel_bbox_lonlat":extent_of_mask(invalid,bounds),
                 "native_source_samples":classify_missing_pixel_samples(sources,invalid,bounds)}
            details.append(row)
    gaps=[row for row in details if row["missing_pixels"]]
    if not gaps:
        raise AssertionError("Expected missing source pixels in known Tumaco z11 pilot area; audit assumptions changed")
    report={"generated_utc":datetime.now(timezone.utc).isoformat(),
            "status":"tumaco_gap_located_in_native_source_coverage",
            "site":"tumaco","probe_lonlat":list(SITE),"zoom":ZOOM,
            "source_cogs":names,
            "tiles_checked":len(details),"tiles_incomplete":len(gaps),
            "missing_pixels_total":sum(d["missing_pixels"] for d in details),
            "missing_inside_reference_land_total":sum(d["missing_inside_Natural_Earth_land"] for d in details),
            "missing_outside_reference_land_total":sum(d["missing_outside_Natural_Earth_land"] for d in details),
            "affected_tiles":gaps,
            "all_tiles":details,
            "production_policy":"Do not encode incomplete tiles or fill unknown heights with 0m/-10000m. Reference outside-land is not proof of ocean.",
            "national_publication_allowed":False}
    (output/"tumaco-native-gap-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("all_tiles",)},indent=2),flush=True)
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,default=Path("output/tumaco-gap"))
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    audit(a.output)

if __name__=="__main__":
    main()
