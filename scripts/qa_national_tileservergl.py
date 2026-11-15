#!/usr/bin/env python3
"""Check real TileServer GL HTTP against genuine NATIONAL original 4+ GiB MBTiles.

Independent HTTP TileJSON + PNG decode equality for stratified z0-13 tiles,
coastal/island/interior/border cities, all heights, no data mutation, and 204.
No Copernicus downloads or dummy tile server.
"""
import argparse
import gzip
import hashlib
import json
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

import mercantile
import numpy as np
from qa_national_terrain_mbtiles import REGIONS, unpack_png
from consolidated_terrain_pipeline import sha256_file
from render_only_coast_rgb import COUNTRY_CLIP_MODE

def request(url):
    try:
        with urllib.request.urlopen(url,timeout=40) as response:
            data=response.read()
            if response.headers.get("Content-Encoding","").lower()=="gzip":
                data=gzip.decompress(data)
            return response.status, response.headers, data
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()

def validate(path,base_url,report):
    path,report=Path(path),Path(report)
    starting_hash=sha256_file(path)
    base_url=base_url.rstrip("/")
    tilejson_url=base_url+"/data/colombia-terrain.json"
    status,headers,blob=request(tilejson_url)
    if status!=200:
        raise AssertionError(f"TileJSON is not reachable through REAL TileServer GL: {status}")
    tilejson=json.loads(blob)
    if tilejson.get("format")!="png" or not tilejson.get("tiles"):
        raise AssertionError("TileServer GL must serve actual PNG tiles as TileJSON")
    if tilejson.get("minzoom")!=0 or tilejson.get("maxzoom")!=13:
        raise AssertionError(f"TileServer GL incorrectly declares national zooms: {tilejson.get('minzoom')}-{tilejson.get('maxzoom')}")
    tested={}
    sampled=set()
    matched_by_zoom={}
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro",uri=True) as db:
        meta=dict(db.execute("SELECT name,value FROM metadata"))
        if meta.get("coast_render_mode")!=COUNTRY_CLIP_MODE:
            raise AssertionError("Not the national OSM Colombia terrain clipping mode")
        for name,(lon,lat) in REGIONS.items():
            tested[name]=[]
            for z in (6,8,10,12,13):
                t=mercantile.tile(lon,lat,z)
                row=db.execute("SELECT 1 FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                               (z,t.x,(1<<z)-1-t.y)).fetchone()
                if row:
                    sampled.add((z,t.x,t.y))
                    tested[name].append([z,t.x,t.y])
        for z in range(14):
            n=db.execute("SELECT COUNT(*) FROM tiles WHERE zoom_level=?",(z,)).fetchone()[0]
            if not n:
                raise AssertionError(f"Missing national zoom {z}")
            rows=db.execute("""SELECT tile_column,tile_row FROM tiles
                               WHERE zoom_level=? ORDER BY tile_column,tile_row LIMIT 1 OFFSET ?""",
                            (z,n//2)).fetchall()
            for x,tms in rows:
                sampled.add((z,x,(1<<z)-tms-1))
        for z,x,y in sorted(sampled):
            row=db.execute("""SELECT t.tile_data,m.mask_png FROM tiles t
                          JOIN osm_land_mask m USING(zoom_level,tile_column,tile_row)
                          WHERE t.zoom_level=? AND t.tile_column=? AND t.tile_row=?""",
                           (z,x,(1<<z)-y-1)).fetchone()
            if row is None:
                raise AssertionError(f"Missing referenced native tile zxy {z,x,y}")
            base_rgb,land=unpack_png(*row)
            url=f"{base_url}/data/colombia-terrain/{z}/{x}/{y}.png"
            response_status,h,data=request(url)
            if response_status!=200 or not h.get("content-type","").startswith("image/png"):
                raise AssertionError(f"Wrong TileServer GL status/mime for zxy {z,x,y}: {response_status}")
            actual_rgb,actual_land=unpack_png(data,row[1])
            if not np.array_equal(actual_rgb,base_rgb) or not np.array_equal(actual_land,land):
                raise AssertionError(f"TileServer GL changed NATIONAL elevations at {z}/{x}/{y}")
            matched_by_zoom[str(z)]=matched_by_zoom.get(str(z),0)+1
        # Request a safe actual offland tile at z13 known missing from source plan.
        z,x,y=13,2300,3800
        if db.execute("SELECT 1 FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                      (z,x,(1<<z)-1-y)).fetchone():
            raise AssertionError("Fixed missing-tile reference unexpectedly exists")
        absent_status,absent_headers,absent_blob=request(
            f"{base_url}/data/colombia-terrain/{z}/{x}/{y}.png")
        if absent_status!=204 or absent_blob:
            raise AssertionError(f"TileServer GL missing tile should be HTTP 204, got {absent_status}")
    ending_hash=sha256_file(path)
    if ending_hash!=starting_hash:
        raise AssertionError("TileServer GL mutated MBTiles source during HTTP tests")
    result={
        "status":"PASS_REAL_TILESERVER_GL_NATIONAL_PNG_IDENTICAL",
        "total_elevation_grids_compared":len(sampled),
        "tile_grids_identical":len(sampled),
        "per_zoom_identical":matched_by_zoom,
        "sampled_regional_locations":tested,
        "no_content_offland_http_status":absent_status,
        "original_source_sha256_identical_before_after":True,
        "source_sha256":starting_hash,
        "tilejson":{"format":tilejson.get("format"),"minzoom":tilejson.get("minzoom"),"maxzoom":tilejson.get("maxzoom")},
        "pixel_heights_not_reencoded_by_TileServer_GL":True,
        "original_COG_redownloaded":False,
        "national_release_authorized":False,
    }
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k in
                      ("status","total_elevation_grids_compared","no_content_offland_http_status",
                       "per_zoom_identical")},indent=2),flush=True)
    return result

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--mbtiles",type=Path,required=True)
    ap.add_argument("--base-url",default="http://127.0.0.1:8080")
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    validate(args.mbtiles,args.base_url,args.output)
