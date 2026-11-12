#!/usr/bin/env python3
"""Experimental Terrain-RGB coastal/island generator; never invent DEM values.

Only publish a tile when every RGB pixel has a valid Copernicus DEM sample.
Every tile with missing data is excluded, with counts classified against an
independent Natural Earth land *reference* (not sovereign jurisdiction).
Existing valid DEM zeros are preserved, not inferred from ocean polygons.
"""
import argparse
import io
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform
from rasterio.enums import Resampling
from shapely import contains_xy
from shapely.geometry import box
from shapely.ops import unary_union

from extend_inventory import NE_SOURCES, ne_shapes
from medellin_terrain import TILE_SIZE, NODATA, rgb_decode, source_tiles
from strict_terrain import aligned_bounds, prepare_sources, build_raster, encode_tile

# Compact windows by purpose, not administrative boundaries. Web Mercator
# alignment may extend a sample well beyond its original geographic bounds.
REGIONS = {
    "cartagena": (-75.60, 10.33, -75.44, 10.50),
    "buenaventura": (-77.11, 3.81, -76.95, 3.96),
    "san_andres": (-81.77, 12.50, -81.63, 12.64),
}

def data_validity(heights):
    return np.isfinite(heights) & (heights != NODATA)

def classify_validity(valid, land):
    """Classify all DEM cells, without assuming outside-land equals ocean."""
    valid = np.asarray(valid,dtype=bool)
    land = np.asarray(land,dtype=bool)
    if valid.shape != land.shape:
        raise ValueError("DEM / reference-land masks must have the same dimensions")
    return {
        "total_pixels":int(valid.size),
        "valid_reference_land":int(np.count_nonzero(valid & land)),
        "missing_reference_land":int(np.count_nonzero(~valid & land)),
        "valid_outside_reference_land":int(np.count_nonzero(valid & ~land)),
        "missing_outside_reference_land":int(np.count_nonzero(~valid & ~land)),
    }

def reference_mask(bounds,geometry):
    """Pixel centers transformed EPSG:3857 to WGS84, then tested vs NE land."""
    x = bounds.left+(np.arange(TILE_SIZE)+0.5)*(bounds.right-bounds.left)/TILE_SIZE
    y = bounds.top-(np.arange(TILE_SIZE)+0.5)*(bounds.top-bounds.bottom)/TILE_SIZE
    xx,yy=np.meshgrid(x,y)
    lon,lat=transform("EPSG:3857","EPSG:4326",xx.ravel(),yy.ravel())
    land=np.asarray(contains_xy(geometry,lon,lat),dtype=bool)
    return land.reshape((TILE_SIZE,TILE_SIZE))

def load_land_reference():
    geometries=ne_shapes(NE_SOURCES["ne_10m_land"])
    geometries+=ne_shapes(NE_SOURCES["ne_10m_minor_islands"])
    return geometries

def process_region(name, output_dir, zoom_min, zoom_max, geometries):
    requested=REGIONS[name]
    aligned=aligned_bounds(requested,zoom_min)
    region_dir=output_dir/name
    region_dir.mkdir(parents=True,exist_ok=True)
    # Source selection with two native-pixel margin; source coverage can be
    # partial along sea edges. Never assume absent source means 0 m.
    _, paths=prepare_sources(aligned,region_dir/"sources")
    pad=2/3600
    padded=(aligned[0]-pad,aligned[1]-pad,aligned[2]+pad,aligned[3]+pad)
    dem, dem_transform=build_raster(paths,padded)
    # Discard global unrelated land geometries for faster point-in-polygon.
    local_box=box(*aligned)
    nearby=[g for g in geometries if g.intersects(local_box)]
    land_geometry=unary_union(nearby) if nearby else box(0,0,0,0)
    db_path=region_dir/(name+"-coastal-pilot.mbtiles")
    db_path.unlink(missing_ok=True)
    db=sqlite3.connect(db_path)
    tile_counts={}
    skipped_by_zoom={}
    total=0
    missing_summary={"valid_reference_land":0,"missing_reference_land":0,
                     "valid_outside_reference_land":0,
                     "missing_outside_reference_land":0,"total_pixels":0}
    min_value=math.inf
    max_value=-math.inf
    try:
        db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT)")
        db.execute("CREATE TABLE tiles(zoom_level INTEGER,tile_column INTEGER,tile_row INTEGER,tile_data BLOB, PRIMARY KEY(zoom_level,tile_column,tile_row))")
        db.executemany("INSERT INTO metadata VALUES (?,?)",[
            ("name",f"Copernicus GLO-30 Coast Pilot {name}"),
            ("format","png"),("type","baselayer"),("version","1.0"),
            ("minzoom",str(zoom_min)),("maxzoom",str(zoom_max)),
            ("bounds",",".join(str(v) for v in aligned)),
            ("attribution","Contains modified Copernicus DEM data"),
            ("description","Experimental Mapbox Terrain-RGB; complete-source-pixels only"),
        ])
        for z in range(zoom_min,zoom_max+1):
            created=0
            skipped=0
            for t in mercantile.tiles(*aligned,zooms=[z]):
                b=mercantile.xy_bounds(t)
                dst=np.full((TILE_SIZE,TILE_SIZE),NODATA,dtype=np.float32)
                reproject(
                    source=dem,destination=dst,
                    src_transform=dem_transform,src_crs="EPSG:4326",
                    src_nodata=NODATA,
                    dst_transform=from_bounds(b.left,b.bottom,b.right,b.top,TILE_SIZE,TILE_SIZE),
                    dst_crs="EPSG:3857",dst_nodata=NODATA,
                    resampling=Resampling.bilinear,num_threads=2,
                )
                valid=data_validity(dst)
                land=reference_mask(b,land_geometry)
                counts=classify_validity(valid,land)
                for key in total_keys:
                    missing_summary[key]+=counts[key]
                data,missing=encode_tile(dst,strict=False)
                if missing:
                    # Do NOT encode -10000m or silently sea-fill even one pixel.
                    skipped+=1
                    continue
                if data is None:
                    raise AssertionError("Valid source tile unexpectedly rejected")
                db.execute("INSERT INTO tiles VALUES(?,?,?,?)",
                           (z,t.x,(1<<z)-1-t.y,data))
                created+=1
                total+=1
                min_value=min(min_value,float(dst.min()))
                max_value=max(max_value,float(dst.max()))
            tile_counts[str(z)]=created
            skipped_by_zoom[str(z)]=skipped
            db.commit()
        if total==0:
            raise RuntimeError(f"No complete Terrain-RGB tiles in {name}; refuse empty MBTiles")
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise RuntimeError("SQLite integrity check failed")
        db.close()
        db=None
        report={
            "region":name,"requested_bbox":requested,"aligned_bbox":aligned,
            "reference_land_source":"Natural Earth 10m land and minor islands (reference only)",
            "source_cogs":[p.stem for p in paths],
            "download_bytes":sum(p.stat().st_size for p in paths),
            "tile_counts":tile_counts,"skipped_incomplete_tile_counts":skipped_by_zoom,
            "pixels":missing_summary,
            "valid_height_min_m":round(min_value,3),"valid_height_max_m":round(max_value,3),
            "mbtiles_bytes":db_path.stat().st_size,
            "status":"pilot_with_gaps" if sum(skipped_by_zoom.values()) else "pilot_complete",
            "policy":"DEM valid pixels only; missing tiles skipped; no water zero fill; no inferred sovereignty",
        }
        (region_dir/"report.json").write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2),flush=True)
        return report
    except BaseException:
        if db is not None:
            db.close()
        db_path.unlink(missing_ok=True)
        raise

total_keys=("total_pixels","valid_reference_land","missing_reference_land",
            "valid_outside_reference_land","missing_outside_reference_land")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--regions",nargs="+",choices=list(REGIONS)+["all"],default=["all"])
    ap.add_argument("--min-zoom",type=int,default=11)
    ap.add_argument("--max-zoom",type=int,default=12)
    ap.add_argument("--output",type=Path,default=Path("output/coastal-terrain"))
    args=ap.parse_args()
    if not (9<=args.min_zoom<=args.max_zoom<=13):
        ap.error("Require 9<=minzoom<=maxzoom<=13 for bounded coast pilot")
    names=list(REGIONS) if "all" in args.regions else list(dict.fromkeys(args.regions))
    args.output.mkdir(parents=True,exist_ok=True)
    geometry=load_land_reference()
    results=[process_region(n,args.output,args.min_zoom,args.max_zoom,geometry) for n in names]
    report={"created_utc":datetime.now(timezone.utc).isoformat(),
            "regions":results,"published":False,
            "blockers":["Production land/ocean mask not verified",
                        "Reference polygons do not establish country jurisdiction",
                        "Incomplete tiles are excluded, not transparently filled",
                        "Adjacent-tile and island full-coverage checks still needed"]}
    (args.output/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    print("Coastal 3-region pilot finished; no permanent release generated",flush=True)

if __name__=="__main__":
    main()
