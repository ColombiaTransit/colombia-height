#!/usr/bin/env python3
"""Two-COG regional Terrain-RGB seam pilot without intermediate DEM mosaics.

A west/east z11 batch partition straddles the Copernicus longitude -75°
degree boundary. Each output Web Mercator tile is warped directly from its
original source COG(s) on that tile's exact pixel grid. Nodata remains nodata.
A second independent source-open of the union validates batch boundaries.

This deliberately does not assume adjacent pixel elevations are equal:
a real terrain gradient exists even across perfectly aligned sources.
"""
import argparse
import io
import json
import sqlite3
from contextlib import ExitStack
from pathlib import Path

import mercantile
import numpy as np
import rasterio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform as transform_coords

from medellin_terrain import NODATA, TILE_SIZE
from strict_terrain import encode_tile, prepare_sources
from merge_regions import merge_mbtiles

BASE_Z=11
BASE_Y=(987,988)
BATCH_BASE_X={"west":(596,597), "east":(598,599)}
SOURCE_BORDER_LON=-75.0
ACCEPTANCE_M=0.16

def base_bounds(xs,ys=BASE_Y):
    lo=mercantile.bounds(min(xs),max(ys),BASE_Z)
    hi=mercantile.bounds(max(xs),min(ys),BASE_Z)
    return lo.west,lo.south,hi.east,hi.north

def tiles_for(xs,ys,z):
    if z<BASE_Z:
        raise ValueError("Zoom below parent grid")
    factor=1<<(z-BASE_Z)
    return [(z,x,y) for row in ys for y in range(row*factor,(row+1)*factor)
            for col in xs for x in range(col*factor,(col+1)*factor)]

def boundary_pairs(z):
    factor=1<<(z-BASE_Z)
    boundary_x=598*factor
    for y in range(min(BASE_Y)*factor,(max(BASE_Y)+1)*factor):
        yield (z,boundary_x-1,y),(z,boundary_x,y)

def open_sources(paths,stack):
    """Keep native COGs open for windowed warp; no intermediate mosaic."""
    sources=[stack.enter_context(rasterio.open(p)) for p in paths]
    if not sources:
        raise ValueError("No source COGs")
    if any(s.crs is None or s.crs.to_epsg()!=4326 or s.count!=1 for s in sources):
        raise ValueError("Expected single-band EPSG:4326 DEM COGs")
    # west-to-east; source selection is deterministic and independent of
    # discovery ordering. Adjacent COGs should not overlap in area.
    return sorted(sources,key=lambda s:(s.bounds.left,s.bounds.bottom,s.name))

def warp_sources(sources,tile):
    """Map all source DEMs directly into one tile, retaining ownership mask."""
    z,x,y=tile
    b=mercantile.xy_bounds(x,y,z)
    affine=from_bounds(b.left,b.bottom,b.right,b.top,TILE_SIZE,TILE_SIZE)
    out=np.full((TILE_SIZE,TILE_SIZE),NODATA,dtype=np.float32)
    provenance=np.zeros((TILE_SIZE,TILE_SIZE),dtype=np.uint8)
    overlaps=0
    max_overlap_delta=0.0
    for idx,source in enumerate(sources,1):
        if idx>255:
            raise ValueError("Too many source rasters for provenance")
        tmp=np.full_like(out,NODATA)
        reproject(
            source=rasterio.band(source,1),destination=tmp,
            src_transform=source.transform,src_crs=source.crs,
            src_nodata=source.nodata,
            dst_transform=affine,dst_crs="EPSG:3857",
            dst_nodata=NODATA,resampling=Resampling.bilinear,
            num_threads=2,
        )
        valid=np.isfinite(tmp)&(tmp!=NODATA)
        overlap=valid&(provenance!=0)
        if np.any(overlap):
            overlaps+=int(overlap.sum())
            max_overlap_delta=max(max_overlap_delta,
                                  float(np.max(np.abs(out[overlap]-tmp[overlap]))))
        take=valid&(provenance==0)
        out[take]=tmp[take]
        provenance[take]=idx
    return out,provenance,overlaps,max_overlap_delta

def source_boundary_stats(heights,provenance):
    """Natural adjacent-pixel gradients where COG assignment switches."""
    different=(provenance[:,1:]!=provenance[:,:-1]) & (provenance[:,1:]!=0) & (provenance[:,:-1]!=0)
    gradients=np.abs(heights[:,1:]-heights[:,:-1])[different]
    return {
        "cross_source_adjacent_pixel_pairs":int(different.sum()),
        "max_adjacent_height_difference_m":round(float(gradients.max()),3) if gradients.size else None,
        "mean_adjacent_height_difference_m":round(float(gradients.mean()),3) if gradients.size else None,
    }

def decode_png(raw):
    with Image.open(io.BytesIO(raw)) as im:
        if im.format!="PNG" or im.size!=(TILE_SIZE,TILE_SIZE):
            raise ValueError("Invalid stored Terrain-RGB PNG")
        a=np.asarray(im.convert("RGB"),dtype=np.int64)
    return -10000.0+(a[:,:,0]*65536+a[:,:,1]*256+a[:,:,2])*0.1

def source_files(bbox,cache):
    entries,paths=prepare_sources(bbox,cache)
    names=[e["name"] for e in entries]
    return names,paths

def render_batch(root,name,minzoom,maxzoom):
    bbox=base_bounds(BATCH_BASE_X[name])
    names,paths=source_files(bbox,root/"source-cache")
    output=root/name
    output.mkdir(parents=True,exist_ok=True)
    mbtiles=output/(name+".mbtiles")
    mbtiles.unlink(missing_ok=True)
    counts={}
    source_pair_count=0
    overlaps=0
    maximum_overlap_delta=0.0
    with ExitStack() as stack:
        sources=open_sources(paths,stack)
        db=sqlite3.connect(mbtiles)
        try:
            db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT)")
            db.execute("CREATE TABLE tiles(zoom_level INTEGER,tile_column INTEGER,tile_row INTEGER,tile_data BLOB, PRIMARY KEY(zoom_level,tile_column,tile_row))")
            db.executemany("INSERT INTO metadata VALUES(?,?)",[
                ("name",f"Antioquia two-COG pilot {name}"),
                ("format","png"),("type","baselayer"),("version","1.0"),
                ("minzoom",str(minzoom)),("maxzoom",str(maxzoom)),
                ("bounds",",".join(str(x) for x in bbox)),
                ("attribution","Contains modified Copernicus DEM data"),
            ])
            for z in range(minzoom,maxzoom+1):
                count=0
                for tile in tiles_for(BATCH_BASE_X[name],BASE_Y,z):
                    dem,provenance,overlap,delta=warp_sources(sources,tile)
                    if np.any(provenance==0):
                        raise ValueError(f"Missing source DEM pixels in {name} tile {tile}: {int((provenance==0).sum())}")
                    png,_=encode_tile(dem,strict=True)
                    _,x,y=tile
                    db.execute("INSERT INTO tiles VALUES(?,?,?,?)",
                               (z,x,(1<<z)-1-y,png))
                    stats=source_boundary_stats(dem,provenance)
                    source_pair_count+=stats["cross_source_adjacent_pixel_pairs"]
                    overlaps+=overlap
                    maximum_overlap_delta=max(maximum_overlap_delta,delta)
                    count+=1
                db.commit()
                counts[str(z)]=count
            if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise AssertionError("Batch SQLite corrupted")
        except BaseException:
            db.close()
            mbtiles.unlink(missing_ok=True)
            raise
        db.close()
    return {
        "name":name,"bounds":bbox,"source_cogs":names,
        "source_download_bytes":sum(p.stat().st_size for p in paths),
        "tile_counts":counts,"mbtiles":str(mbtiles),
        "mbtiles_bytes":mbtiles.stat().st_size,
        "source_transition_adjacent_pairs":source_pair_count,
        "overlap_pixels":overlaps,
        "max_overlapping_source_delta_m":round(maximum_overlap_delta,3),
    }

def get_png(db,tile):
    z,x,y=tile
    row=db.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                   (z,x,(1<<z)-1-y)).fetchone()
    if row is None:
        raise AssertionError(f"Missing batch tile {tile}")
    return decode_png(row[0])

def check_all_sources(root,batches,minzoom,maxzoom):
    """Reopen union-area native COGs and independently recompute shared seams."""
    full=base_bounds(tuple(sorted(set(x for xs in BATCH_BASE_X.values() for x in xs))))
    names,paths=source_files(full,root/"source-cache")
    if len(names)<2:
        raise AssertionError("Not a multi-source test: fewer than two Copernicus COGs")
    metrics={}
    max_reference=0.0
    transition_count=0
    total_cross_batch=0
    with ExitStack() as stack:
        sources=open_sources(paths,stack)
        with sqlite3.connect(f"file:{Path(batches[0]['mbtiles']).resolve()}?mode=ro",uri=True) as west,sqlite3.connect(f"file:{Path(batches[1]['mbtiles']).resolve()}?mode=ro",uri=True) as east:
            for z in range(minzoom,maxzoom+1):
                rows=[]
                for a,b in boundary_pairs(z):
                    left=get_png(west,a)
                    right=get_png(east,b)
                    if a[2]!=b[2] or b[1]!=a[1]+1:
                        raise AssertionError("Tiles are not adjacent")
                    west_bounds=mercantile.xy_bounds(a[1],a[2],z)
                    east_bounds=mercantile.xy_bounds(b[1],b[2],z)
                    if abs(west_bounds.right-east_bounds.left)>1e-6:
                        raise AssertionError("Mercator tile boundary mismatch")
                    w,wp,wo,wd=warp_sources(sources,a)
                    e,ep,eo,ed=warp_sources(sources,b)
                    if np.any(wp==0) or np.any(ep==0):
                        raise AssertionError("Missing source pixels in independent seam reference")
                    err=float(max(np.max(np.abs(w-left)),np.max(np.abs(e-right))))
                    max_reference=max(max_reference,err)
                    if err>ACCEPTANCE_M:
                        raise AssertionError(f"Cross-batch reference mismatch {a}->{b}: {err:.3f} m")
                    gradients=np.abs(left[:,-1]-right[:,0])
                    rows.append({
                        "west_tile":list(a),"east_tile":list(b),
                        "max_reference_error_m":round(err,4),
                        "max_natural_pixel_gradient_m":round(float(gradients.max()),3),
                        "mean_natural_pixel_gradient_m":round(float(gradients.mean()),3),
                    })
                    total_cross_batch+=1
                metrics[str(z)]=rows
        # Verify source border has been encountered and output reproduces a
        # tile directly straddling -75 longitude (not only batch boundary).
        crossing_tiles=[]
        for z in range(minzoom,maxzoom+1):
            for name,xs in BATCH_BASE_X.items():
                for tile in tiles_for(xs,BASE_Y,z):
                    bb=mercantile.bounds(tile[1],tile[2],z)
                    if not bb.west < SOURCE_BORDER_LON < bb.east:
                        continue
                    dem,owners,overlap,delta=warp_sources(sources,tile)
                    s=source_boundary_stats(dem,owners)
                    transition_count+=s["cross_source_adjacent_pixel_pairs"]
                    crossing_tiles.append({
                        "tile":list(tile),"batch":name,
                        "different_cogs_present":len(set(int(v) for v in np.unique(owners) if v)),
                        **s,
                    })
        if not crossing_tiles:
            raise AssertionError("Test misses -75 degree native COG border")
        if transition_count==0:
            raise AssertionError("No direct source transitions across -75; inspect COG indexing")
    return {
        "reference_cogs":names,
        "vertical_cross_batch_pairs":total_cross_batch,
        "max_reference_error_m":round(max_reference,4),
        "within_acceptance":max_reference<=ACCEPTANCE_M,
        "source_boundary_lon":SOURCE_BORDER_LON,
        "cross_source_adjacent_pixel_pairs":transition_count,
        "crossing_tiles":crossing_tiles,
        "cross_batch_seams_by_zoom":metrics,
        "note":"Native source discontinuities are reported as terrain gradients, not fabricated zero-height joins.",
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,default=Path("output/two-cog-seams"))
    p.add_argument("--maxzoom",type=int,choices=(12,13),default=13)
    a=p.parse_args()
    root=a.output
    root.mkdir(parents=True,exist_ok=True)
    batches=[render_batch(root,n,BASE_Z,a.maxzoom) for n in ("west","east")]
    merged=root/"two-cog-merged.mbtiles"
    merged.unlink(missing_ok=True)
    summary=merge_mbtiles([b["mbtiles"] for b in batches],merged)
    expected=sum(sum(b["tile_counts"].values()) for b in batches)
    if summary["tiles"]!=expected:
        raise AssertionError("Merged tile count mismatch")
    qa=check_all_sources(root,batches,BASE_Z,a.maxzoom)
    with sqlite3.connect(merged) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise AssertionError("Merged MBTiles corrupted")
        if db.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]!=expected:
            raise AssertionError("Merged duplicate/missing keys")
    report={
        "status":"two_cog_regional_test_passed",
        "created_but_not_released":True,
        "source_boundary_lon":SOURCE_BORDER_LON,
        "minzoom":BASE_Z,"maxzoom":a.maxzoom,
        "batches":batches,"merged":summary,"qa":qa,
        "limitations":[
            "This validates a longitude border between two specific native Copernicus COGs near Antioquia; other borders still require QA",
            "Cross-source pixel-to-pixel gradients are not zero by definition",
            "Independent reference reopens the same source files, but shares the warp algorithm",
            "Coast/ocean/official island masking not tested in this inland pilot",
        ],
    }
    (root/"two-cog-seam-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("qa","batches")},indent=2),flush=True)
    print(json.dumps({k:v for k,v in qa.items() if k not in ("crossing_tiles","cross_batch_seams_by_zoom")},indent=2),flush=True)

if __name__=="__main__":
    main()
