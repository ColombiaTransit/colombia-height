#!/usr/bin/env python3
"""Independent, bounded-memory national QA on the RELEASED-DRAFT MBTiles bytes.

No COG / OSM re-download or new terrain generation. Check ALL stored Terrain-RGB
and factual 256x256 OSM mask PNGs plus a geographically stratified exact sample
of the previously verified OSM physical-land and Colombia-relation geometry.
Fail closed: leave the published release unchanged; write auditable JSON.
"""
import argparse
import hashlib
import io
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

import mercantile
import numpy as np
from PIL import Image

from consolidated_terrain_pipeline import load_plan, sha256_file
from generate_osm_land_only_terrain import (
    classify_tile_osm_masks, load_osm_coastline_land, load_osm_country)
from render_only_coast_rgb import COUNTRY_CLIP_MODE

def json_numpy_scalar(value):
    """Explicitly serialize NumPy scalar counters without hiding bad report types."""
    if isinstance(value,np.generic):
        return value.item()
    raise TypeError(f"Unsupported QA report JSON type: {type(value).__name__}")


SCALE = 100000  # Mapbox Terrain-RGB encoded integer at 0 m
REGIONS = {
    "Bogota": (-74.0721, 4.7110),
    "Medellin": (-75.5812, 6.2442),
    "Cali": (-76.5320, 3.4516),
    "Cartagena": (-75.5110, 10.4240),
    "Barranquilla": (-74.7964, 10.9685),
    "Buenaventura": (-77.0260, 3.8810),
    "Tumaco": (-78.7655, 1.8067),
    "La_Guajira": (-72.5650, 12.1660),
    "Leticia": (-69.9406, -4.2153),
    "San_Andres": (-81.7006, 12.5847),
    "Providencia": (-81.3750, 13.3490),
    "Pasto": (-77.2811, 1.2136),
    "Quibdo": (-76.6589, 5.6919),
    "Santa_Marta": (-74.1990, 11.2419),
}


def unpack_png(terrain_png, mask_png):
    with Image.open(io.BytesIO(terrain_png)) as im:
        if im.format != "PNG" or im.mode not in ("RGB", "RGBA") or im.size != (256, 256):
            raise AssertionError("Terrain-RGB must be a 256x256 RGB PNG")
        rgb = np.asarray(im.convert("RGB"), dtype=np.uint32)
    with Image.open(io.BytesIO(mask_png)) as im:
        if im.format != "PNG" or im.mode != "L" or im.size != (256, 256):
            raise AssertionError("Exact OSM factual land-mask must be a 256x256 grayscale PNG")
        value = np.asarray(im,dtype=np.uint8)
    if np.any((value != 255) & (value != 0)):
        raise AssertionError("Factual OSM mask must have only 255 true / 0 false pixels")
    packed = (rgb[:,:,0]*65536 + rgb[:,:,1]*256 + rgb[:,:,2])
    return packed, value == 255


def _assert(condition, message):
    if not condition:
        raise AssertionError(message)


def validate(mbtiles, plan_path, osm_land_clip, osm_land_meta, osm_country,
             output, sample_modulus=271):
    if sample_modulus < 1:
        raise ValueError("Invalid independent reference sampling interval")
    mbtiles, plan_path, output = map(Path,(mbtiles,plan_path,output))
    plan=load_plan(plan_path)
    _assert(plan["zoom_range"]==[0,13] and plan["shards"]==32,
            "Country plan must cover all z0-13 with 32 unique owner shards")
    # Verify every immutable chunk roster SHA-256, and build exact expected candidate set.
    candidates=set()
    for c in plan["chunks"]:
        ndjson=plan_path.parent/c["filename"]
        _assert(ndjson.is_file() and sha256_file(ndjson)==c["sha256"],
                f"Modified or missing immutable chunk roster {c['id']}")
        lines=ndjson.read_text().splitlines()
        _assert(len(lines)==c["tiles"],f"Chunk row count changed {c['id']}")
        for line in lines:
            t=json.loads(line)
            z,x,y=t["z"],t["x"],t["y"]
            _assert(t["tms_y"]==(1<<z)-y-1 and (z,x,y) not in candidates,
                    "Non-unique planned tile or invalid TMS")
            candidates.add((z,x,y))
    _assert(len(candidates)==plan["candidate_tiles"],"Incomplete or duplicate planned tile roster")
    per_zoom=Counter()
    pixel_counts=Counter()
    height_min, height_max = float("inf"),float("-inf")
    examples={}
    unexpected=[]
    # Deterministic samples span interior, coasts, islands and every zoom.
    requested={}
    for name,(lon,lat) in REGIONS.items():
        for z in (5,7,9,11,13):
            tile=mercantile.tile(lon,lat,z)
            requested[(tile.z,tile.x,tile.y)]=name
    sampled_by_zoom=defaultdict(list)
    unique_heights_count=0
    with sqlite3.connect(f"file:{mbtiles.resolve()}?mode=ro",uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        _assert(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok",
                "Full national SQLite integrity_check failed")
        metadata=dict(db.execute("SELECT name,value FROM metadata"))
        for k,expected in (
            ("format","png"),("minzoom","0"),("maxzoom","13"),
            ("coast_render_mode",COUNTRY_CLIP_MODE),
            ("sea_surface_is_bathymetry","false"),
            ("foreign_land_is_sea","false"),
            ("foreign_land_visual_background_m","0"),
        ):
            _assert(metadata.get(k)==expected,f"Invalid national MBTiles metadata {k}")
        _assert("OpenStreetMap" in metadata.get("attribution","") and
                "Copernicus" in metadata.get("attribution",""),
                "Missing original Copernicus or OSM attribution")
        _assert(db.execute("SELECT count(*) FROM tiles").fetchone()[0]==
                db.execute("SELECT count(*) FROM osm_land_mask").fetchone()[0],
                "Native Terrain-RGB and factual mask table counts differ")
        _assert(db.execute("""SELECT COUNT(*) FROM tiles t
                    LEFT JOIN osm_land_mask m
                    USING(zoom_level,tile_column,tile_row)
                    WHERE m.zoom_level IS NULL""").fetchone()[0]==0,
                "Terrain PNG missing factual OSM mask")
        _assert(db.execute("""SELECT COUNT(*) FROM osm_land_mask m
                    LEFT JOIN tiles t
                    USING(zoom_level,tile_column,tile_row)
                    WHERE t.zoom_level IS NULL""").fetchone()[0]==0,
                "Orphan OSM mask without Terrain PNG")
        # SQL streaming: never fetch 4+ GiB of BLOBs into memory.
        cur=db.execute("""SELECT t.zoom_level,t.tile_column,t.tile_row,t.tile_data,m.mask_png
                        FROM tiles t JOIN osm_land_mask m
                        USING(zoom_level,tile_column,tile_row)
                        ORDER BY t.zoom_level,t.tile_column,t.tile_row""")
        for z,x,tms,terrain,mask_blob in cur:
            y=(1<<z)-tms-1
            tile=(z,x,y)
            _assert(0<=z<=13 and 0<=x<(1<<z) and 0<=y<(1<<z),
                    f"Invalid tile XYZ/TMS coordinate {tile}")
            _assert(tile in candidates,f"Unexpected/unplanned geographic tile {tile}")
            candidates.remove(tile)
            packed,land=unpack_png(terrain,mask_blob)
            _assert(bool(land.any()),f"Emitted empty land/background-only tile {tile}")
            _assert(np.all(packed[~land] == SCALE),
                    f"Offland visual-only pixels not exact zero {tile}")
            _assert(not np.any(packed[land] == 0),
                    f"RGB(0,0,0) -10000 m fake trench in factual Colombian land {tile}")
            onland=packed[land].astype(np.float64)/10.0-10000.0
            _assert(bool(np.isfinite(onland).all()),f"Non-finite DEM land pixels {tile}")
            # Negative coastal land can exist; do not invent a zero floor.
            height_min=min(height_min,float(onland.min()))
            height_max=max(height_max,float(onland.max()))
            unique_heights_count+=int(onland.min()==onland.max())
            per_zoom[z]+=1
            nland=int(land.sum())
            pixel_counts["land"]+=nland
            pixel_counts["flat_visual_only"]+=65536-nland
            pixel_counts["full_land_tiles"]+=nland==65536
            pixel_counts["mixed_tiles"]+=nland<65536
            # ~ 0.4% of tiles + named landmarks, spread across every zoom.
            chosen=((z*2654435761 ^ x*2246822519 ^ y) % sample_modulus == 0 or
                    tile in requested or (z<7 and per_zoom[z]<=2))
            if chosen:
                sampled_by_zoom[z].append((tile,mask_blob,land.copy()))
            if tile in requested:
                examples[requested[tile]]={"zxy":list(tile),
                                          "land_pixels":nland,
                                          "land_height_range_m":[float(onland.min()),float(onland.max())]}
            if per_zoom[z]%10000==0:
                print(f"Decoded {per_zoom[z]} native Terrain-RGB+mask tiles at zoom {z}",flush=True)
        _assert(sum(per_zoom.values())>0,"Missing all national terrain tiles")
        _assert(set(per_zoom)==set(range(14)),f"Not every zoom 0-13 contains terrain: {dict(per_zoom)}")
        _assert(height_min>=-500 and height_max<=7000,
                f"Unexpected native Colombian land height extent {height_min:.1f}..{height_max:.1f}m; investigate source, do not clip")
        # Verify not just existing tiles: missing plan candidates must be
        # real all-offland OSM candidates, never silently lost islands.
        omitted_by_zoom=Counter(z for z,x,y in candidates)
        omitted_reference_samples=[tile for tile in sorted(candidates)
                                   if tile[0]<=8 or
                                   ((tile[0]*2654435761 ^ tile[1]*2246822519 ^ tile[2]) % sample_modulus==0)]
        # Validate true physical OSM land from PREVIOUS immutable snapshot at samples.
        physical,osm_meta=load_osm_coastline_land(osm_land_clip,osm_land_meta)
        country=load_osm_country(osm_country)
        reference_count=0
        for z in range(14):
            rows=sampled_by_zoom[z]
            _assert(rows,f"Sampling plan missed entire zoom {z}")
            for tile,mask_blob,mask in rows:
                source_mask,status,nland=classify_tile_osm_masks(tile,physical,country)
                if not np.array_equal(source_mask,mask):
                    unexpected.append({"zxy":list(tile),
                                       "different_pixels":int(np.count_nonzero(source_mask!=mask))})
                reference_count+=1
        _assert(not unexpected,f"Stored original OSM mask differs from expected physical land+R120027: {unexpected[:5]}")
        incorrect_skips=[]
        for tile in omitted_reference_samples:
            source_mask,status,nland=classify_tile_osm_masks(tile,physical,country)
            if nland:
                incorrect_skips.append({"zxy":list(tile),"unpublished_real_OSM_land_pixels":nland})
        _assert(not incorrect_skips,
                f"Missing output tiles contain factual OSM Colombia land: {incorrect_skips[:10]}")
        _assert(osm_meta["reference_wkb_sha256"] and len(osm_meta["reference_wkb_sha256"])==64,
                "Original OSM mask provenance absent")
        # Do not compare coarser and finer native elevations as equal: independent
        # warp sampling changes their pixel centers; that is NOT a seam defect.
        # Adjacent native land-only edge gradients are a quality diagnostic
        # requiring visual review rather than invented universal terrain thresholds.
        seam_differences=[]
        seam_pairs=0
        sample_tiles=[item[0] for z in (10,11,12,13) for item in sampled_by_zoom[z]]
        for z,x,y in sample_tiles[:1000]:
            row=db.execute("""SELECT t.tile_data,m.mask_png FROM tiles t JOIN osm_land_mask m
                USING(zoom_level,tile_column,tile_row)
                WHERE t.zoom_level=? AND t.tile_column=? AND t.tile_row=?""",
                (z,x,(1<<z)-1-y)).fetchone()
            if row is None:
                continue
            a,la=unpack_png(*row)
            for nx,ny,axis in ((x+1,y,"east"),(x,y+1,"south")):
                if nx>=(1<<z) or ny>=(1<<z):
                    continue
                row2=db.execute("""SELECT t.tile_data,m.mask_png FROM tiles t JOIN osm_land_mask m
                    USING(zoom_level,tile_column,tile_row)
                    WHERE t.zoom_level=? AND t.tile_column=? AND t.tile_row=?""",
                    (z,nx,(1<<z)-1-ny)).fetchone()
                if row2 is None:
                    continue
                b,lb=unpack_png(*row2)
                if axis=="east":
                    overlap=la[:,-1] & lb[:,0]
                    diffs=np.abs(a[:,-1].astype(np.int64)-b[:,0].astype(np.int64))[overlap]/10.0
                else:
                    overlap=la[-1,:] & lb[0,:]
                    diffs=np.abs(a[-1,:].astype(np.int64)-b[0,:].astype(np.int64))[overlap]/10.0
                if len(diffs):
                    seam_pairs+=1
                    seam_differences.extend(diffs.tolist())
    # Pixel validity is strict; seam elevations reported with transparent geographic variability.
    quantiles=np.percentile(seam_differences,[50,95,99,100]).tolist() if seam_differences else []
    result={
        "schema":"colombia-national-real-terrain-QA-v1",
        "status":"PASS_full_product_structural_pixels_and_OSM_samples" if not unexpected else "FAIL",
        "national_release_authorized":False,
        "input_mbtiles_sha256":sha256_file(mbtiles),
        "input_mbtiles_size_bytes":mbtiles.stat().st_size,
        "candidate_tiles_checked":plan["candidate_tiles"],
        "source_COG_inventory_count":plan["source_COGs"],
        "planned_chunk_count":len(plan["chunks"]),
        "original_OSM_reference_sha256":osm_meta["reference_wkb_sha256"],
        "native_tiles_checked":sum(per_zoom.values()),
        "decoded_native_Terrain_RGB_PNGs":sum(per_zoom.values()),
        "factual_OSM_mask_PNGs":sum(per_zoom.values()),
        "tiles_by_zoom":{str(z):per_zoom[z] for z in range(14)},
        "valid_original_OSM_Colombia_land_pixels":pixel_counts["land"],
        "flat_visual_only_background_pixels":pixel_counts["flat_visual_only"],
        "full_land_tiles":pixel_counts["full_land_tiles"],
        "mixed_tiles":pixel_counts["mixed_tiles"],
        "original_land_height_range_m":[height_min,height_max],
        "single_height_land_tiles":unique_heights_count,
        "original_reference_masks_independently_recomputed":reference_count,
        "omitted_candidate_tiles":len(candidates),
        "omitted_candidate_tiles_by_zoom":{str(z):omitted_by_zoom[z] for z in range(14)},
        "omitted_candidate_tiles_checked_against_original_OSM":len(omitted_reference_samples),
        "omitted_candidate_tiles_with_real_land_detected":len(incorrect_skips),
        "reference_mask_mismatch_tiles":len(unexpected),
        "reference_mask_mismatch_examples":unexpected[:20],
        "sampled_adjacent_land_edge_pairs":seam_pairs,
        "sampled_adjacent_land_edge_height_diff_percentiles_m":dict(zip(
            ("p50","p95","p99","max"), quantiles)),
        "geographic_landmark_examples":examples,
        "visual_QA_required":True,
        "full_native_COG_rewarping_repeated":False,
        "osm_or_COG_download_repeated":False,
        "notes":[
            "Native heights are validated as decoded Terrain-RGB with a factual 256x256 OSM mask per tile.",
            "0m outside OSM Colombia land is ONLY a flat visualization background; foreign land is NOT sea and this is NOT bathymetry.",
            "Cross-tile gradients can reflect natural relief. They are statistics, not proof of an interpolation seam.",
            "Separate actual TileServer GL HTTP + MapLibre 6.8 browser checks are required before publication.",
        ],
    }
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,sort_keys=True,default=json_numpy_scalar)+"\n")
    print(json.dumps({k:v for k,v in result.items()
                      if k in ("status","native_tiles_checked","input_mbtiles_size_bytes",
                               "valid_original_OSM_Colombia_land_pixels",
                               "flat_visual_only_background_pixels",
                               "original_land_height_range_m",
                               "original_reference_masks_independently_recomputed",
                               "sampled_adjacent_land_edge_height_diff_percentiles_m")},indent=2),flush=True)
    return result


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--mbtiles",type=Path,required=True)
    ap.add_argument("--plan",type=Path,required=True)
    ap.add_argument("--osm-land-clip",type=Path,required=True)
    ap.add_argument("--osm-land-meta",type=Path,required=True)
    ap.add_argument("--osm-country-geojson",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--sample-modulus",type=int,default=271)
    a=ap.parse_args()
    validate(a.mbtiles,a.plan,a.osm_land_clip,a.osm_land_meta,
             a.osm_country_geojson,a.output,a.sample_modulus)
