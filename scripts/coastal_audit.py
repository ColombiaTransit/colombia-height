#!/usr/bin/env python3
"""Audit Copernicus GLO-30 coastline and island coverage, without inventing elevations.

Fetches only the source COGs needed for seven compact sampling windows.
A geoBoundaries land polygon is compared to actual DEM masks, but this audit
does NOT use the polygon to fill DEM voids or publish a terrain dataset.
"""
import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
import requests
from rasterio.enums import Resampling
from rasterio.merge import merge
from rasterio.transform import xy
from shapely import contains_xy
from shapely.geometry import shape
from shapely.ops import unary_union

from inventory import BOUNDARY_URL, TILES_URL, get_json, parse_tile
from medellin_terrain import download

# Representative sample windows, NOT coastline or territorial boundaries.
# center longitude/latitude and sampling half-width in degrees
REGIONS = [
    {"id":"cartagena","category":"caribbean_coast","lon":-75.515,"lat":10.415,"half":0.14},
    {"id":"barranquilla","category":"caribbean_coast","lon":-74.82,"lat":10.98,"half":0.15},
    {"id":"buenaventura","category":"pacific_coast","lon":-77.03,"lat":3.88,"half":0.15},
    {"id":"tumaco","category":"pacific_coast","lon":-78.76,"lat":1.81,"half":0.14},
    {"id":"san_andres","category":"island","lon":-81.70,"lat":12.57,"half":0.12},
    {"id":"providencia","category":"island","lon":-81.37,"lat":13.35,"half":0.12},
    {"id":"malpelo","category":"island","lon":-81.606,"lat":4.00,"half":0.06},
]
# GeoBoundaries may omit tiny offshore islands. These are independent,
# nominated land-check points; unknown/absent data remains *unknown*.
LAND_PROBES = {
    "cartagena": [(-75.49,10.40)],
    "barranquilla": [(-74.80,10.97)],
    "buenaventura": [(-77.02,3.89)],
    "tumaco": [(-78.76,1.81)],
    "san_andres": [(-81.70,12.57)],
    "providencia": [(-81.37,13.35)],
    "malpelo": [(-81.606,4.005)],
}
# Exact sea points are not verified. Do NOT make assumptions from elevation == 0.
GRID_RESOLUTION = 1/600  # sample at ~185m north-south, not native 30m

def bbox(region):
    a=region["half"]
    return (region["lon"]-a,region["lat"]-a,region["lon"]+a,region["lat"]+a)

def index_sources():
    r=requests.get(TILES_URL,timeout=90)
    r.raise_for_status()
    tile_index={}
    for line in r.text.splitlines():
        t=parse_tile(line)
        if t:
            tile_index[(t["latitude"],t["longitude"])]=t
    if len(tile_index)<1000:
        raise RuntimeError("Invalid Copernicus public source index")
    return tile_index

def intersect_cells(bounds):
    west,south,east,north=bounds
    return [
        (lat,lon)
        for lat in range(math.floor(south),math.ceil(north))
        for lon in range(math.floor(west),math.ceil(east))
        if lon < east and lon+1 > west and lat < north and lat+1 > south
    ]

def classify(valid, land):
    """Summarize data validity by country polygon, without reclassifying any pixels."""
    valid=np.asarray(valid,dtype=bool);land=np.asarray(land,dtype=bool)
    if valid.shape!=land.shape:
        raise ValueError("Mask shape mismatch")
    return {
        "grid_cells":int(valid.size),
        "in_colombia_boundary":int(land.sum()),
        "outside_colombia_boundary":int((~land).sum()),
        "valid_inside_boundary":int((valid & land).sum()),
        "missing_inside_boundary":int((~valid & land).sum()),
        "valid_outside_boundary":int((valid & ~land).sum()),
        "missing_outside_boundary":int((~valid & ~land).sum()),
    }

def grid_land_mask(transform,rows,cols,land_geometry):
    # Sample at the center of each grid cell.
    r,c=np.indices((rows,cols))
    x,y=xy(transform,r,c,offset="center")
    # rasterio.xy flattens array-valued row/column indices into coordinate
    # vectors; reconstruct the original (rows, cols) mask shape explicitly.
    x=np.asarray(x).reshape((rows,cols))
    y=np.asarray(y).reshape((rows,cols))
    mask=np.asarray(contains_xy(land_geometry,x,y),dtype=bool)
    if mask.shape != (rows,cols):
        raise RuntimeError(f"Unexpected land mask shape {mask.shape}, expected {(rows,cols)}")
    return mask

def probe_samples(source_paths,points):
    """Return actual native DEM samples at nominated points; no interpolation."""
    samples=[]
    sources=[rasterio.open(p) for p in source_paths]
    try:
        for lon,lat in points:
            match=next((s for s in sources if s.bounds.left<=lon<s.bounds.right
                        and s.bounds.bottom<=lat<s.bounds.top),None)
            if match is None:
                samples.append({"lon":lon,"lat":lat,"status":"source_missing","height_m":None})
                continue
            sample=next(match.sample([(lon,lat)],masked=True))
            value=sample[0]
            if np.ma.is_masked(value) or not np.isfinite(float(value)):
                samples.append({"lon":lon,"lat":lat,"status":"dem_nodata","height_m":None})
            else:
                samples.append({"lon":lon,"lat":lat,"status":"dem_valid",
                                "height_m":round(float(value),2)})
    finally:
        for src in sources:
            src.close()
    return samples

def evaluate_region(region,tile_index,land_geometry,source_cache):
    bounds=bbox(region)
    expected=intersect_cells(bounds)
    found=[tile_index[c] for c in expected if c in tile_index]
    absent=[{"latitude":lat,"longitude":lon} for lat,lon in expected if (lat,lon) not in tile_index]
    result={
        "id":region["id"],"category":region["category"],
        "sampling_bbox":bounds,
        "expected_degree_cells":len(expected),
        "source_tile_count":len(found),
        "source_tiles":[x["name"] for x in found],
        "missing_source_cells":absent,
        "status":"pending",
    }
    if not found:
        result["status"]="no_source_tiles"
        result["land_probes"]=[{"lon":lon,"lat":lat,"status":"source_missing","height_m":None}
                               for lon,lat in LAND_PROBES[region["id"]]]
        return result

    paths=[]
    for item in found:
        path=source_cache/(item["name"]+".tif")
        print(f"Source for {region['id']}: {item['name']}",flush=True)
        download(item["url"],path)
        paths.append(path)
    result["source_download_bytes"]=sum(p.stat().st_size for p in paths)
    sources=[rasterio.open(p) for p in paths]
    try:
        # Low-resolution window audit avoids materializing the native 30 m mosaic.
        data,transform=merge(sources,bounds=bounds,res=(GRID_RESOLUTION,GRID_RESOLUTION),
                             nodata=-9999.0,resampling=Resampling.nearest)
        height=data[0]
        valid=np.isfinite(height)&(height!=-9999.0)
        land=grid_land_mask(transform,*height.shape,land_geometry)
        result["grid_summary"]=classify(valid,land)
        # Important: positive or zero heights outside boundary do not prove ocean;
        # geoBoundaries is a country polygon and includes neither all other
        # countries nor necessarily every tiny Colombian island.
        result["land_probes"]=probe_samples(paths,LAND_PROBES[region["id"]])
        result["status"]="audited" if not absent else "partial_sources"
    finally:
        for source in sources:
            source.close()
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=Path("output/coastal-audit"))
    parser.add_argument("--region",choices=["all"]+[r["id"] for r in REGIONS],default="all")
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    cache=args.output/"sources";cache.mkdir(exist_ok=True)
    tile_index=index_sources()
    metadata=get_json(BOUNDARY_URL)
    gj=get_json(metadata["gjDownloadURL"])
    features=gj.get("features") or []
    if not features:
        raise RuntimeError("No Colombia boundary features")
    geometry=unary_union([shape(f["geometry"]) for f in features])
    if geometry.is_empty:
        raise RuntimeError("Empty Colombia boundary geometry")
    regions=REGIONS if args.region=="all" else [r for r in REGIONS if r["id"]==args.region]
    results=[evaluate_region(r,tile_index,geometry,cache) for r in regions]
    report={
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "source_index":TILES_URL,
        "boundary_metadata":BOUNDARY_URL,
        "boundary_geometry":metadata["gjDownloadURL"],
        "boundary_license":metadata.get("boundaryLicense"),
        "sample_resolution_degrees":GRID_RESOLUTION,
        "regions":results,
        "important_limitations":[
            "These windows are diagnostic samples, not full national coastline coverage.",
            "Outside the Colombia boundary is not equivalent to ocean.",
            "A DEM pixel of height 0 does not prove that pixel represents sea water.",
            "geoBoundaries may omit very small or offshore Colombian islands.",
            "Missing DEM values must not be encoded as -10000 m or silently set to 0 m.",
            "A valid land probe is not proof that an entire island has DEM coverage."
        ],
    }
    dest=args.output/"coastal-island-audit.json"
    dest.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,ensure_ascii=False),flush=True)
    # The audit itself is successful even when island coverage is absent:
    # absent coverage is a finding. Infrastructure/parse errors still fail.
    return 0

if __name__=="__main__":
    sys.exit(main())
