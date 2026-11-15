#!/usr/bin/env python3
"""Investigate the exact most-negative *land* pixel in the immutable national MBTiles.

Reads the existing 4.16 GiB national draft, then reuses the SAME audited OSM
polygon and native bilinear warper on only the single most relevant z13 tile.
Never changes or regenerates the national output. No second country inventory.
"""
import argparse
import io
import json
import sqlite3
from collections import Counter
from pathlib import Path

import mercantile
import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import transform
from rasterio.windows import Window

from generate_osm_land_only_terrain import (
    classify_tile_osm_masks, load_osm_coastline_land, load_osm_country)
from national_dem_coverage import intersecting_source_indices, local_cogs
from national_tile_plan import parse_manifest
from two_cog_seam_pilot import warp_sources
from render_only_coast_rgb import decode_mask_png

THRESHOLDS = (0, -1, -10, -50, -100, -200)
EXPLICIT_OUTLIER_BELOW_M = -100.0


def lonlat(tile, row, col):
    z,x,y=tile
    b=mercantile.xy_bounds(x,y,z)
    east=b.left+(col+0.5)*(b.right-b.left)/256.
    north=b.top-(row+0.5)*(b.top-b.bottom)/256.
    longitude,latitude=transform("EPSG:3857","EPSG:4326",[east],[north])
    lon,lat=longitude[0],latitude[0]
    return [float(lon),float(lat)]


def unpack(terrain,mask):
    with Image.open(io.BytesIO(terrain)) as im:
        if im.format!="PNG" or im.size!=(256,256):
            raise ValueError("Original terrain tile is not 256x256 PNG")
        rgb=np.asarray(im.convert("RGB"),dtype=np.uint32)
    land=decode_mask_png(mask)
    packed=rgb[:,:,0]*65536+rgb[:,:,1]*256+rgb[:,:,2]
    return packed,land


def sample_tile(db,tile):
    z,x,y=tile
    return db.execute("""SELECT t.tile_data,m.mask_png
        FROM tiles t JOIN osm_land_mask m
        USING(zoom_level,tile_column,tile_row)
        WHERE t.zoom_level=? AND t.tile_column=? AND t.tile_row=?""",
        (z,x,(1<<z)-1-y)).fetchone()


def native_source_inspection(tile,row,col,png_encoded,land,sources,cache):
    candidates=intersecting_source_indices(sources,*tile)
    if not candidates:
        raise AssertionError(f"No original source COG covers MINIMUM tile {tile}")
    cache.mkdir(parents=True,exist_ok=True)
    opened={}
    try:
        natives=local_cogs(sources,candidates,cache,opened)
        elevations,provenance,overlaps,overlap_delta=warp_sources(natives,tile)
        genuine=np.isfinite(elevations)&(elevations!=-9999.)&(provenance>0)
        if not np.all(genuine[land]):
            raise AssertionError("Original GLO-30 source unexpectedly misses stored OSM Colombian land")
        decoded=png_encoded.astype(np.float64)/10.-10000.
        delta=np.abs(elevations[land].astype(np.float64)-decoded[land])
        if delta.size==0 or float(delta.max())>0.051:
            raise AssertionError(f"One-tile original native COG rewarp differs from existing immutable MBTiles: max {float(delta.max())}")
        idx=int(provenance[row,col])
        if idx<=0:
            raise AssertionError("Minimum original pixel has no genuine Copernicus source provenance")
        item=sources[candidates[idx-1]]
        lon,lat=lonlat(tile,row,col)
        ds=opened[candidates[idx-1]]
        src_row,src_col=ds.index(lon,lat)
        window=Window(max(0,src_col-5),max(0,src_row-5),11,11)
        patch=ds.read(1,window=window,masked=True)
        raw_valid=patch.compressed().astype(np.float64)
        if raw_valid.size==0:
            raise AssertionError("Native source patch at exact minimum is entirely missing")
        raw_value=list(ds.sample([(lon,lat)],masked=True))[0][0]
        if np.ma.is_masked(raw_value):
            raise AssertionError("Native original COG center pixel is nodata")
        raw_value=float(raw_value)
        encoded=float(decoded[row,col])
        rewarped=float(elevations[row,col])
        if abs(rewarped-encoded)>0.051:
            raise AssertionError("Original native COG rewarp disagrees with stored minimum")
        return {
            "original_source_name":item["name"],
            "original_source_url":item["url"],
            "original_source_cell_latlon":[int(item["latitude"]),int(item["longitude"])],
            "native_source_pixel_row_col":[int(src_row),int(src_col)],
            "raw_native_source_COG_nearest_pixel_m":raw_value,
            "native_COG_11x11_window_min_m":float(np.min(raw_valid)),
            "native_COG_11x11_window_max_m":float(np.max(raw_valid)),
            "native_COG_11x11_window_negative_count":int(np.sum(raw_valid<0)),
            "native_COG_11x11_window_valid_count":int(raw_valid.size),
            "native_bilinear_rewarp_m":rewarped,
            "stored_TerrainRGB_decoded_m":encoded,
            "native_rewarp_vs_stored_max_abs_error_m":float(delta.max()),
            "native_tile_valid_source_land_pixels":int(np.count_nonzero(land)),
            "overlap_valid_native_pixels":int(overlaps),
            "max_overlap_delta_m":float(overlap_delta),
            "original_source_count_fetched":len(opened),
            "source_COG_download_scope":"Only original COG(s) intersecting this single MINIMUM z13 XYZ tile",
        }
    finally:
        for ds in opened.values():
            ds.close()


def investigate(mbtiles,manifest,osm_land,osm_meta,osm_country,cache,output):
    mbtiles,output=Path(mbtiles),Path(output)
    threshold_values={t:int(round((10000+t)*10)) for t in THRESHOLDS}
    count_by_zoom=Counter()
    negatives_by_zoom=Counter()
    severe_by_zoom=Counter()
    per_zoom_min={}
    lowest_candidates=[]
    total_land=0
    with sqlite3.connect(f"file:{mbtiles.resolve()}?mode=ro",uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        meta=dict(db.execute("SELECT name,value FROM metadata"))
        if meta.get("coast_render_mode")!="surface_zero_visual_only_osm_country_clip_v1":
            raise AssertionError("This is not original Colombia-only height MBTiles")
        query="""SELECT t.zoom_level,t.tile_column,t.tile_row,t.tile_data,m.mask_png
                FROM tiles t JOIN osm_land_mask m USING(zoom_level,tile_column,tile_row)
                ORDER BY t.zoom_level DESC,t.tile_column,t.tile_row"""
        for z,x,tms,terrain,mask in db.execute(query):
            tile=(z,x,(1<<z)-1-tms)
            packed,land=unpack(terrain,mask)
            if not land.any():
                raise AssertionError(f"Unexpected all-offland emitted tile {tile}")
            heights=packed[land]
            count_by_zoom[z]+=1
            total_land+=int(len(heights))
            min_height_packed=int(heights.min())
            min_height=round(min_height_packed/10.-10000.,1)
            if z not in per_zoom_min or min_height<per_zoom_min[z]:
                per_zoom_min[z]=min_height
            nneg=int(np.count_nonzero(heights<threshold_values[0]))
            negatives_by_zoom[z]+=nneg
            severe_by_zoom[z]+=int(np.count_nonzero(heights<threshold_values[-100]))
            if min_height<-10:
                positions=np.argwhere(land & (packed==min_height_packed))
                row,col=(int(v) for v in positions[0])
                lowest_candidates.append({
                    "zxy":list(tile),
                    "pixel_row_col":[row,col],
                    "lonlat":lonlat(tile,row,col),
                    "min_elevation_m":min_height,
                    "pixels_below_0m":nneg,
                    "pixels_below_minus_100m":int(np.count_nonzero(heights<threshold_values[-100])),
                    "land_pixels_in_tile":int(len(heights)),
                })
            if sum(count_by_zoom.values())%15000==0:
                print(f"Decoded {sum(count_by_zoom.values())} real national tiles; z{z}, {len(lowest_candidates)} negative-location candidates",flush=True)
        worst=sorted(lowest_candidates,key=lambda r:(r["min_elevation_m"],-r["zxy"][0]))
        if not worst:
            raise RuntimeError("Original national QA had a negative land minimum but none found")
        exact=worst[0]
        tile=tuple(exact["zxy"])
        row,col=exact["pixel_row_col"]
        blob=sample_tile(db,tile)
        if not blob:
            raise AssertionError("Minimum tile missing while recomputing")
        packed,land=unpack(*blob)
        physical,osm_info=load_osm_coastline_land(osm_land,osm_meta)
        country=load_osm_country(osm_country)
        derived,stat,num,physical_mask=classify_tile_osm_masks(tile,physical,country,True)
        if not np.array_equal(derived,land) or not bool(derived[row,col]) or not bool(physical_mask[row,col]):
            raise AssertionError("Min pixel NOT independently proven OSM physical land+Colombia relation")
        offland=np.argwhere(~land)
        dist_px=(float(np.sqrt(np.min(np.sum((offland-np.array([row,col]))**2,axis=1))))
                 if len(offland) else None)
        # Record local 9x9 encoded heights and land masks to detect an isolated
        # -239m pit versus a real gradual valley/depression. No smoothing.
        rr0,rr1=max(0,row-4),min(256,row+5)
        cc0,cc1=max(0,col-4),min(256,col+5)
        neighbourhood=[
          [round(float(packed[r,c]/10.-10000.),1) if bool(land[r,c]) else None
           for c in range(cc0,cc1)] for r in range(rr0,rr1)
        ]
        mask_lonlat=lonlat(tile,row,col)
    # Native source is selectively re-read: ONLY the z13 outlier tile's
    # intersecting original COG(s) are downloaded, never the country again.
    native=None
    if tile[0]==13:
        sources=parse_manifest(manifest)
        native=native_source_inspection(tile,row,col,packed,land,sources,Path(cache))
    result={
        "schema":"colombia-height-actual-minimum-original-source-investigation-v1",
        "status":"SOURCE_VERIFIED" if native is not None else "SOURCE_PENDING_Z13_ONLY",
        "national_mbtiles_bytes":mbtiles.stat().st_size,
        "zoom_minima_m":{str(k):per_zoom_min[k] for k in sorted(per_zoom_min)},
        "full_tiles_scanned":sum(count_by_zoom.values()),
        "real_land_pixels_examined":total_land,
        "negative_pixels_by_zoom":{str(k):negatives_by_zoom[k] for k in sorted(negatives_by_zoom)},
        "below_minus_100_pixels_by_zoom":{str(k):severe_by_zoom[k] for k in sorted(severe_by_zoom)},
        "most_negative_exact_location":exact,
        "lowest_20_distinct_tiles":worst[:20],
        "number_of_tiles_with_min_below_minus_10m":len(lowest_candidates),
        "osm_independent_physical_land":True,
        "osm_independent_colombia_R120027":True,
        "osm_minimum_tile_land_pixels":num,
        "minimum_distance_to_offland_in_tile_pixels":dist_px,
        "minimum_9x9_original_heights_m_None_means_offland":neighbourhood,
        "native_source_recheck":native,
        "original_MBtiles_modified":False,
        "original_national_generator_rerun":False,
        "no_national_COG_download":True,
        "accepted_border_flat_background_is_not_bathymetry":True,
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("SOURCE CHECK REPORT:",json.dumps({
        "status":result["status"],
        "tile":exact["zxy"],
        "lonlat":exact["lonlat"],
        "elevation_m":exact["min_elevation_m"],
        "raw_COG":native and native["raw_native_source_COG_nearest_pixel_m"],
        "native_rewarp":native and native["native_bilinear_rewarp_m"],
        "negative_tiles":len(lowest_candidates),
    },indent=2),flush=True)
    return result


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mbtiles",required=True)
    ap.add_argument("--manifest",required=True)
    ap.add_argument("--osm-land",required=True)
    ap.add_argument("--osm-meta",required=True)
    ap.add_argument("--osm-country",required=True)
    ap.add_argument("--cache",required=True)
    ap.add_argument("--output",required=True)
    a=ap.parse_args()
    investigate(a.mbtiles,a.manifest,a.osm_land,a.osm_meta,a.osm_country,a.cache,a.output)
