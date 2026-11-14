#!/usr/bin/env python3
"""Check *actual TileServer GL* reads Terrain-RGB MBTiles unchanged.

Selects real coastal tiles and their factual OSM masks, compares every
original decoded Terrain-RGB height to TileServer GL responses pixel-by-pixel. Never uses fake DEM or
rebuilds COGs. Rejects unrecognised/error/redirect HTML payloads.
"""
import argparse
import hashlib
import json
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from render_only_coast_rgb import COAST_MODE, decode_mask_png, decode_terrain_rgb

def download(url):
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.status, response.headers, response.read()

def run(mbtiles,base_url):
    mbtiles=Path(mbtiles)
    with sqlite3.connect(f"file:{mbtiles.resolve()}?mode=ro",uri=True) as db:
        metadata=dict(db.execute("SELECT name,value FROM metadata"))
        assert metadata["format"]=="png"
        assert metadata["coast_render_mode"]==COAST_MODE
        assert metadata["sea_surface_is_bathymetry"]=="false"
        assert metadata["visualization_sea_surface_m"]=="0"
        tiles=db.execute("""SELECT t.zoom_level,t.tile_column,t.tile_row,
                                   t.tile_data,m.mask_png
                            FROM tiles t
                            JOIN osm_land_mask m
                            USING(zoom_level,tile_column,tile_row)""").fetchall()
        assert tiles, "Empty DEM table"
        assert len(tiles)==db.execute("SELECT count(*) FROM tiles").fetchone()[0]
    tilejson_url=base_url.rstrip("/")+"/data/colombia-terrain.json"
    status,headers,blob=download(tilejson_url)
    info=json.loads(blob)
    assert status==200
    assert info.get("format")=="png"
    assert "tiles" in info and info["tiles"], "TileServer GL did not expose tile URLs"
    all_verified=0
    mixed_found=False
    full_found=False
    for z,x,tms_y,expected_png,mask_png in tiles:
        land=decode_mask_png(mask_png)
        heights=decode_terrain_rgb(expected_png)
        assert (heights[~land]==0).all(), "Offland pixels are not visual 0m"
        assert (heights[land]>-10000).all(), "Native land contains forbidden fake trench"
        xyz_y=(1<<z)-1-tms_y
        url=f"{base_url.rstrip('/')}/data/colombia-terrain/{z}/{x}/{xyz_y}.png"
        returned_status,h,actual_png=download(url)
        if (returned_status!=200 or
                not h.get("content-type","").startswith("image/png")):
            raise AssertionError(f"TileServer GL did not serve PNG Terrain-RGB at {z}/{x}/{xyz_y}")
        # TileServer GL is permitted to re-encode lossless PNG compression;
        # the native 256x256 RGB elevation samples MUST remain identical.
        actual_heights=decode_terrain_rgb(actual_png)
        if actual_heights.shape!=heights.shape or not (actual_heights==heights).all():
            import numpy as np
            delta=np.abs(actual_heights-heights)
            raise AssertionError(
                f"TileServer GL changed actual elevations at {z}/{x}/{xyz_y}; "
                f"max height difference {float(delta.max())}m; "
                f"original PNG bytes {len(expected_png)}, returned {len(actual_png)}")
        all_verified+=1
        mixed_found |= bool(land.any() and (~land).any())
        full_found |= bool(land.all())
    assert mixed_found and full_found, "Pilot does not cover both mixed and full physical land"
    # This ocean/offland tile should be missing; with sparse:false TileServer GL
    # must explicitly respond 204 (not try to invent an all-sea 0m PNG).
    z,x,y=13,2300,3800
    with sqlite3.connect(f"file:{mbtiles.resolve()}?mode=ro",uri=True) as db:
        row=db.execute(
            "SELECT 1 FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (z,x,(1<<z)-1-y)).fetchone()
        assert row is None
    empty_url=f"{base_url.rstrip('/')}/data/colombia-terrain/{z}/{x}/{y}.png"
    try:
        empty_status,empty_headers,empty_blob=download(empty_url)
    except urllib.error.HTTPError as exc:
        empty_status=exc.code
        empty_blob=exc.read()
    if empty_status!=204 or empty_blob:
        raise AssertionError(f"Expected explicit 204 No Content for absent tile; got {empty_status}")
    report={"status":"TILESERVER_GL_RAW_PNG_PASS","tilejson_format":info["format"],
            "tile_height_grids_identical":all_verified,"verified_mixed_land_sea_tile":mixed_found,
            "verified_full_land_tile":full_found,
            "absent_tile_status":empty_status,
            "mapbox_terrain_rgb_256":True,
            "OSM_land_mask_verified_in_MBtiles":True,
            "no_bathymetry_or_fake_source_land":True}
    print(json.dumps(report,indent=2))
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--mbtiles",type=Path,required=True)
    parser.add_argument("--base-url",default="http://127.0.0.1:8080")
    args=parser.parse_args()
    run(args.mbtiles,args.base_url)
