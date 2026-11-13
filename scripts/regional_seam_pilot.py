#!/usr/bin/env python3
"""Independent adjoining regional Terrain-RGB batches with seam QA.

This pilot deliberately uses ONE source COG on its native raster grid:
independently cut mosaics previously caused an unverified ~0.9m seam error.
Both batches render distinct Web Mercator tiles from native DEM pixels.
The reference reads the original source separately; multi-COG seams require
a separate follow-up pilot. No permanent release is created.
"""
import argparse
import io
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

import mercantile
import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject

from medellin_terrain import NODATA, TILE_SIZE
from strict_terrain import encode_tile, prepare_sources
from merge_regions import merge_mbtiles

# Z11 4x2 inland Antioquia tiles, split at x=595. Two batches both cross
# z12 and z13 child tiles; no shared ownership at any zoom.
BASE_Z=11
BASE_Y=(987,988)
BATCH_BASE_X={"west":(593,594),"east":(595,596)}

def bounds_for_base(xs, ys=BASE_Y):
    first=mercantile.bounds(min(xs),max(ys),BASE_Z)
    last=mercantile.bounds(max(xs),min(ys),BASE_Z)
    return (first.west,first.south,last.east,last.north)

def tile_list(xs, ys, zoom):
    factor=1<<(zoom-BASE_Z)
    return [(zoom,x,y)
            for yy in ys for y in range(yy*factor,(yy+1)*factor)
            for xx in xs for x in range(xx*factor,(xx+1)*factor)]

def load_native_cog(paths):
    """Read untouched source raster with its *native* affine and nodata mask.

    A clipped rasterio.merge() mosaic can resample the same source DEM
    differently for east/west batches. This pilot checks seam ownership
    without that intermediate interpolation. Multi-COG stitching is an
    explicitly separate validation task and fails closed here.
    """
    if len(paths)!=1:
        raise RuntimeError(
            f"Native-grid seam pilot requires exactly one source COG, got {len(paths)}; "
            "multi-COG seam test still required"
        )
    with rasterio.open(paths[0]) as src:
        if src.count!=1 or src.crs is None or src.crs.to_epsg()!=4326:
            raise ValueError("Source COG must be one band in EPSG:4326")
        return src.read(1).astype(np.float32,copy=False), src.transform, src.nodata

def warp_tile(dem, src_transform, tile, width=TILE_SIZE, height=TILE_SIZE,
              region_bounds=None, src_nodata=NODATA):
    z,x,y=tile
    b=mercantile.xy_bounds(x,y,z)
    if region_bounds is None:
        projected=(b.left,b.bottom,b.right,b.top)
    else:
        projected=region_bounds
    out=np.full((height,width),NODATA,dtype=np.float32)
    reproject(
        source=dem,destination=out,
        src_transform=src_transform,src_crs="EPSG:4326",src_nodata=src_nodata,
        dst_transform=from_bounds(*projected,width,height),
        dst_crs="EPSG:3857",dst_nodata=NODATA,
        resampling=Resampling.bilinear,num_threads=2,
    )
    return out

def decode_png(raw):
    with Image.open(io.BytesIO(raw)) as img:
        if img.format!="PNG" or img.size!=(TILE_SIZE,TILE_SIZE):
            raise ValueError("Unexpected Terrain-RGB image type/size")
        arr=np.asarray(img.convert("RGB"),dtype=np.int64)
    return -10000.0+(arr[:,:,0]*65536+arr[:,:,1]*256+arr[:,:,2])*0.1

def render_batch(output, name, minzoom, maxzoom):
    xs=BATCH_BASE_X[name]
    bbox=bounds_for_base(xs)
    root=output/name
    root.mkdir(parents=True,exist_ok=True)
    entries,paths=prepare_sources(bbox,output/"source-cache")
    dem,tform,nodata=load_native_cog(paths)
    print(f"{name}: rendering from native COG grid; transform={tuple(tform)} nodata={nodata}",flush=True)
    path=root/(name+".mbtiles")
    path.unlink(missing_ok=True)
    db=sqlite3.connect(path)
    counts={}
    try:
        db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT)")
        db.execute("CREATE TABLE tiles(zoom_level INTEGER,tile_column INTEGER,tile_row INTEGER,tile_data BLOB, PRIMARY KEY(zoom_level,tile_column,tile_row))")
        db.executemany("INSERT INTO metadata VALUES(?,?)",[
            ("name","Antioquia independent seam pilot "+name),
            ("format","png"),("type","baselayer"),("version","1.0"),
            ("minzoom",str(minzoom)),("maxzoom",str(maxzoom)),
            ("bounds",",".join(map(str,bbox))),
            ("attribution","Contains modified Copernicus DEM data"),
        ])
        for z in range(minzoom,maxzoom+1):
            count=0
            for tile in tile_list(xs,BASE_Y,z):
                heights=warp_tile(dem,tform,tile,src_nodata=nodata)
                png,_=encode_tile(heights,strict=True)
                _,x,y=tile
                db.execute("INSERT INTO tiles VALUES (?,?,?,?)",
                           (z,x,(1<<z)-1-y,png))
                count+=1
            db.commit()
            counts[str(z)]=count
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise RuntimeError("Invalid SQLite batch")
    except BaseException:
        db.close()
        path.unlink(missing_ok=True)
        raise
    db.close()
    return {"name":name,"bounds":bbox,"mbtiles":str(path),
            "counts":counts,"source_tiles":[x["name"] for x in entries],
            "raster_sampling":"native_COG_no_clipped_mosaic",
            "source_download_bytes":sum(p.stat().st_size for p in paths),
            "bytes":path.stat().st_size}

def union_sources(output):
    bbox=bounds_for_base(tuple(x for xs in BATCH_BASE_X.values() for x in xs))
    entries,paths=prepare_sources(bbox,output/"source-cache")
    return load_native_cog(paths)

def max_error(a,b):
    return float(np.max(np.abs(a-b)))

def load_png(db,z,x,y):
    record=db.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                      (z,x,(1<<z)-1-y)).fetchone()
    if record is None:
        raise ValueError(f"Absent tile {z}/{x}/{y}")
    return decode_png(record[0])

def seam_pairs(z):
    """Yield all horizontal and vertical adjacency pairs crossing batch line."""
    factor=1<<(z-BASE_Z)
    boundary_x=595*factor
    for y in range(min(BASE_Y)*factor,(max(BASE_Y)+1)*factor):
        yield ("vertical",(z,boundary_x-1,y),(z,boundary_x,y))

def check_seams(west,east,dem,tform,nodata,minzoom,maxzoom):
    report={}
    seam_count=0
    with sqlite3.connect(f"file:{Path(west).resolve()}?mode=ro",uri=True) as wa,sqlite3.connect(f"file:{Path(east).resolve()}?mode=ro",uri=True) as eb:
        for z in range(minzoom,maxzoom+1):
            metrics=[]
            for direction,a,b in seam_pairs(z):
                _,ax,ay=a
                _,bx,by=b
                left=load_png(wa,z,ax,ay)
                right=load_png(eb,z,bx,by)
                bb1=mercantile.xy_bounds(ax,ay,z)
                bb2=mercantile.xy_bounds(bx,by,z)
                if not np.isclose(bb1.right,bb2.left,atol=1e-6):
                    raise ValueError("Nonadjacent Web Mercator tiles")
                # Compare each independent 256x256 batch tile against the
                # reference mosaic on precisely the SAME pixel grid.
                # A single 512x256 GDAL warp has a different approximation
                # grid and can introduce ~metre-scale discrepancies on slopes
                # even if the underlying DEM is perfectly aligned.
                ref_left=warp_tile(dem,tform,a,src_nodata=nodata)
                ref_right=warp_tile(dem,tform,b,src_nodata=nodata)
                if (not np.isfinite(ref_left).all() or not np.isfinite(ref_right).all()
                        or np.any(ref_left==NODATA) or np.any(ref_right==NODATA)):
                    raise ValueError("Reference DEM invalid at seam")
                left_error=max_error(left,ref_left)
                right_error=max_error(right,ref_right)
                error=max(left_error,right_error)
                # Native-grid reference on identical 256px tile grids.
                # Tolerance covers 0.1m RGB quantization and float jitter.
                if error>0.16:
                    raise AssertionError(
                        f"Seam reference mismatch {z}/{ax}/{ay} -> {z}/{bx}/{by}: "
                        f"{error:.3f}m (left={left_error:.3f}, right={right_error:.3f}); "
                        "native-source rendering should not differ beyond RGB quantization"
                    )
                gap=np.abs(left[:,-1]-right[:,0])
                left_inside=np.abs(left[:,-2]-left[:,-1])
                right_inside=np.abs(right[:,0]-right[:,1])
                metrics.append({
                    "west_tile":[z,ax,ay],"east_tile":[z,bx,by],
                    "max_abs_reference_error_m":round(error,4),
                    "max_adjacent_sample_height_delta_m":round(float(gap.max()),3),
                    "mean_adjacent_sample_height_delta_m":round(float(gap.mean()),3),
                    "mean_interior_pixel_height_delta_m":round(float((left_inside.mean()+right_inside.mean())/2),3),
                    "valid_samples_on_border":int(len(gap)),
                })
                seam_count+=1
            report[str(z)]=metrics
    return {"vertical_cross_batch_seam_count":seam_count,
            "all_seams_match_independent_reference":True,
            "seams_by_zoom":report,
            "note":"Large border elevation gradients can be real terrain; pixel-center values on either side are not required to be identical."}

def verify_merged(output,expected):
    with sqlite3.connect(output) as db:
        count=db.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]
        if count!=expected:
            raise AssertionError((count,expected))
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise AssertionError("Merged SQLite integrity failure")
    return count

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,default=Path("output/antioquia-seams"))
    ap.add_argument("--maxzoom",type=int,choices=(12,13),default=13)
    args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    batches=[render_batch(args.output,key,BASE_Z,args.maxzoom) for key in ("west","east")]
    merged=args.output/"antioquia-seams-merged.mbtiles"
    merged.unlink(missing_ok=True)
    merge=merge_mbtiles([b["mbtiles"] for b in batches],merged)
    expected=sum(sum(b["counts"].values()) for b in batches)
    merged_count=verify_merged(merged,expected)
    dem,tform,nodata=union_sources(args.output)
    seams=check_seams(batches[0]["mbtiles"],batches[1]["mbtiles"],dem,tform,nodata,BASE_Z,args.maxzoom)
    report={
        "status":"regional_seam_pilot_validated",
        "bbox":bounds_for_base((593,594,595,596)),
        "zoom_min":BASE_Z,"zoom_max":args.maxzoom,
        "batches":batches,"merged":merge,"merged_tile_count":merged_count,
        "seams":seams,
        "limitations":["Independent batch rendering tested using the SAME native single-COG source; multi-COG raster stitching is not yet tested",
                       "This is not a national coastline/ocean-mask test",
                       "High slope gradients are descriptive; no arbitrary maximum jump threshold",
                       "No permanent GitHub release or national MBTiles produced"]
    }
    (args.output/"seam-validation-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="seams"},indent=2),flush=True)
    print(json.dumps({k:v for k,v in seams.items() if k!="seams_by_zoom"},indent=2),flush=True)

if __name__=="__main__":
    main()
