#!/usr/bin/env python3
"""First SAFE OSM physical-land-only Colombia Terrain-RGB MBTiles generator.

Consumes the existing 140 native Copernicus source inventory in its verified
priority order, an already-prepared OSMCoastline land WKB clip, and the OSM
Colombia relation's GeoJSON (R120027). No new DEM research or worldwide OSM
downloads.

The exact 256x256 Web Mercator center mask is:
  OSMCoastline assembled LAND polygons INTERSECT OSM COL administrative area.
Only these pixels require valid native GLO-30 heights.

RELEASE GATE: standard MapLibre raster-dem decodes RGB and IGNORES PNG alpha.
A mixed land/sea RGB tile cannot safely represent off-land NoData. Thus this
initial generator REFUSES COAST tiles outright, rather than encoding them as
fake -10000 m trenches or ocean elevations. It can generate verified fully
inland MBTiles; do NOT call this a complete national generator.

To finish coastal tiles, an explicitly reviewed renderer/offland convention
must be implemented separately and integration-tested in MapLibre/TileServer.
"""
import argparse
import hashlib
import io
import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import numpy as np
from PIL import Image
from shapely import contains_xy
from shapely.geometry import Point, shape
from shapely.validation import make_valid

from island_native_recovery_qa import xyz_centers
from national_tile_plan import parse_manifest
from osm_land_only_dem_policy import verify_osm_land_only_native_dem
from osm_land_reference import load_clip
from osm_national_land_audit import PolygonMask
from national_dem_coverage import intersecting_source_indices,local_cogs
from two_cog_seam_pilot import warp_sources
from medellin_terrain import rgb_encode

TILE_PX=256
NATIVE_NODATA=-9999.
STAGING_COUNT=140
EXPECTED_STAGING_TAIL={
    "Copernicus_DSM_COG_10_N03_00_W079_00_DEM",
    "Copernicus_DSM_COG_10_N03_00_W082_00_DEM",
    "Copernicus_DSM_COG_10_N01_00_W080_00_DEM",
}
COL_OSM_RELATION=120027
MAX_ALLOWED_NATIONAL_Z13=13


def require_verified_staging(sources):
    if len(sources)!=STAGING_COUNT or len({s["name"] for s in sources})!=STAGING_COUNT:
        raise AssertionError("Expected 140 validated source COGs, not all available catalog cells")
    if {s["name"] for s in sources[137:]}!=EXPECTED_STAGING_TAIL:
        raise AssertionError("Last three source COGs must be reviewed islands and Tumaco")
    if any(s["name"] in EXPECTED_STAGING_TAIL for s in sources[:137]):
        raise AssertionError("Original 137 source inventory was mutated")
    if any(s["status"]!="ok" for s in sources):
        raise AssertionError("An original Copernicus COG was not verified")


def load_osm_country(geojson_path):
    data=json.loads(Path(geojson_path).read_text())
    if (data.get("OSM_relation_id")!=COL_OSM_RELATION
            or data.get("source")!="OpenStreetMap"
            or data.get("geometry") is None):
        raise AssertionError("Country must be OSM Colombia relation R120027, no alternative ADM0 layer")
    geom=shape(data["geometry"])
    if not geom.is_valid:
        geom=make_valid(geom)
    if geom.geom_type not in ("Polygon","MultiPolygon") or geom.is_empty:
        raise AssertionError("OSM Colombia country relation geometry unavailable")
    if not geom.contains(Point(-74.072,4.711)):
        raise AssertionError("Bogotá is not contained in OSM Colombia relation")
    return geom


def load_osm_coastline_land(clip_path,metadata_path):
    meta=json.loads(Path(metadata_path).read_text())
    if (meta.get("source")!="https://osmdata.openstreetmap.de/data/land-polygons.html"
            or meta.get("status")!="OSMCoastline_WGS84_split_land_clipped_study_reference"
            or meta.get("source_geometry_type")!="polygon"
            or meta.get("source_projection")!="EPSG:4326"
            or not meta.get("reference_wkb_sha256")
            or meta.get("national_publication_allowed") is not False):
        raise AssertionError("Physical land must come from recorded OSMCoastline assembled polygons")
    geoms=load_clip(clip_path,meta["reference_wkb_sha256"])
    return PolygonMask(geoms),meta


def classify_tile_osm_masks(tile,osm_land,col_geom):
    lon,lat=xyz_centers(tile)
    physical_land=osm_land.mask(tile,lon,lat)
    col=np.asarray(contains_xy(col_geom,lon.ravel(),lat.ravel()),
                   dtype=bool).reshape((256,256))
    mask=physical_land&col
    count=int(mask.sum())
    status=("skip_no_physical_OSM_Colombia_land" if count==0
            else "fully_OSM_Colombia_land" if count==65536
            else "mixed_coastal_OSM_Colombia_land_and_offland")
    return mask,status,count


def plan_bounded_tiles(bbox,minzoom,maxzoom,max_tiles):
    if (not 0<=minzoom<=maxzoom<=MAX_ALLOWED_NATIONAL_Z13
            or not 1<=max_tiles<=50000):
        raise ValueError("Invalid zoom range or max tile limit")
    if not (len(bbox)==4 and -180<=bbox[0]<bbox[2]<=180 and
            -85<=bbox[1]<bbox[3]<=85):
        raise ValueError("Expected lonlat west,south,east,north bounding box")
    unique=set()
    for zoom in range(minzoom,maxzoom+1):
        for tile in mercantile.tiles(*bbox,zooms=[zoom]):
            unique.add((tile.z,tile.x,tile.y))
            if len(unique)>max_tiles:
                raise RuntimeError("OSM land-only pilot bbox exceeds bounded tile count")
    return sorted(unique)


def prepare_plan(tiles,osm_land,col_geom):
    statuses=Counter()
    detailed=[]
    for tile in tiles:
        mask,status,num=classify_tile_osm_masks(tile,osm_land,col_geom)
        statuses[status]+=1
        detailed.append({"tile":tile,"mask":mask,
                         "status":status,"land_pixels":num})
    return statuses,detailed


def validated_terrain_rgb(heights,required):
    """ONLY all-OSM-land, truly valid native source samples are encoded."""
    if heights.shape!=(256,256) or required.shape!=(256,256) or not np.all(required):
        raise ValueError("Cannot encode a mixed coast tile as unmasked MapLibre raster-dem")
    valid=np.isfinite(heights)&(heights!=NATIVE_NODATA)
    if not np.all(valid):
        raise ValueError(f"Missing {int(np.count_nonzero(~valid))} true OSM Colombian land elevations")
    if np.any(heights < -10000) or np.any(heights > 1667721.5):
        raise ValueError("DEM out of representable Mapbox Terrain-RGB range; do not clip")
    pngbuf=io.BytesIO()
    Image.fromarray(rgb_encode(heights)).save(pngbuf,format="PNG",optimize=True)
    blob=pngbuf.getvalue()
    with Image.open(io.BytesIO(blob)) as im:
        rgb=np.asarray(im.convert("RGB"),np.int64)
    decoded=-10000+(rgb[:,:,0]*65536+rgb[:,:,1]*256+rgb[:,:,2])*.1
    maxerr=float(np.max(np.abs(decoded-heights)))
    if maxerr>0.051:
        raise AssertionError(f"Terrain-RGB encode/decode height error {maxerr}m")
    if np.any(np.all(rgb==0,axis=2)):
        raise AssertionError("Forbidden RGB zero encoded false terrain trench")
    return blob,maxerr


def write_inland_mbtiles(target,rows,source,cache,bbox,zooms):
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp=target.with_name(target.name+".incomplete")
    tmp.unlink(missing_ok=True)
    opened={}
    report=Counter()
    max_error=0.
    connection=None
    try:
        connection=sqlite3.connect(tmp)
        connection.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY, value TEXT)")
        connection.execute("""CREATE TABLE tiles(
            zoom_level INTEGER,
            tile_column INTEGER,
            tile_row INTEGER,
            tile_data BLOB,
            PRIMARY KEY(zoom_level,tile_column,tile_row)
        )""")
        metadata={
            "name":"ColombiaTransit native GLO-30 OSM FULL-LAND only pilot",
            "format":"png","type":"baselayer","version":"1.0",
            "minzoom":str(zooms[0]),"maxzoom":str(zooms[1]),
            "bounds":",".join(map(str,bbox)),
            "description":"Mapbox Terrain-RGB true Copernicus elevations ONLY on fully Colombian physical OSM land tiles; mixed coast excluded",
            "attribution":"Contains modified Copernicus DEM data; © OpenStreetMap contributors (ODbL 1.0)",
        }
        connection.executemany("INSERT INTO metadata VALUES(?,?)",metadata.items())
        for row in rows:
            if row["status"]=="skip_no_physical_OSM_Colombia_land":
                report["skipped_all_offland"]+=1
                continue
            if row["status"]!="fully_OSM_Colombia_land":
                raise AssertionError("Coast tiles may not enter full-land DEM writer")
            tile=row["tile"]
            ids=intersecting_source_indices(source,*tile)
            if not ids:
                raise ValueError(f"No Copernicus source for OSM full-land {tile}")
            src=local_cogs(source,ids,cache,opened)
            heights,provenance,overlap,difference=warp_sources(src,tile)
            gate,_=verify_osm_land_only_native_dem(
                heights,row["mask"],row["mask"])
            if gate["OSM_Colombia_land_pixels_missing_real_native_elevation"]:
                raise ValueError(f"Missing native Colombian OSM land DEM at {tile}")
            png,error=validated_terrain_rgb(heights,row["mask"])
            max_error=max(max_error,error)
            z,x,y=tile
            connection.execute(
                "INSERT INTO tiles VALUES (?,?,?,?)",
                (z,x,(1<<z)-y-1,png))
            report["full_land_tiles_written"]+=1
            report["original_source_intersected_tile_valid_pixels"]+=65536
        if report["full_land_tiles_written"]==0:
            raise RuntimeError("All study tiles are offland; no MBTiles output to publish")
        if connection.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise AssertionError("MBTiles SQLite integrity failed")
        connection.commit()
        connection.close()
        connection=None
        tmp.replace(target)
    finally:
        if connection is not None:
            connection.close()
        for handle in opened.values():
            handle.close()
        tmp.unlink(missing_ok=True)
    return {**dict(report),"max_Terrain_RGB_roundtrip_elevation_error_m":max_error}


def run(source_manifest,land_clip,land_meta,country_json,output,
        bbox,minzoom,maxzoom,max_tiles,cache):
    sources=parse_manifest(source_manifest)
    require_verified_staging(sources)
    physical,meta=load_osm_coastline_land(land_clip,land_meta)
    country=load_osm_country(country_json)
    tiles=plan_bounded_tiles(bbox,minzoom,maxzoom,max_tiles)
    statuses,rows=prepare_plan(tiles,physical,country)
    # FAIL CLOSED: do not generate a superficially 'successful' national
    # MBTiles file with omitted coastal/island land pixels. No source
    # downloads or SQLite writes occur before this invariant.
    if statuses["mixed_coastal_OSM_Colombia_land_and_offland"]:
        blocked=[list(r["tile"]) for r in rows
                 if r["status"]=="mixed_coastal_OSM_Colombia_land_and_offland"]
        raise RuntimeError(
            f"{len(blocked)} mixed OSM land/coast tiles require reviewed "
            "MapLibre raster-dem offland encoding; no MBTiles generated. "
            "First few zxy: "+str(blocked[:8]))
    cache=Path(cache)
    cache.mkdir(parents=True,exist_ok=True)
    result=write_inland_mbtiles(output,rows,sources,cache,bbox,(minzoom,maxzoom))
    evidence={
        "status":"OSM_land_only_INLAND_ONLY_native_GLO30_MBtiles_pilot_not_national_release",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "source_manifest":str(source_manifest),
        "original_COG_count":137,"staging_COG_count":140,
        "OSM_physical_land_source":meta["source"],
        "OSM_physical_land_SHA256":meta["reference_wkb_sha256"],
        "OSM_country_relation_id":120027,
        "bbox":list(bbox),"zoom_range":[minzoom,maxzoom],
        "tiles_checked":len(tiles),"mask_summary":dict(statuses),
        "generated_mbtiles_file":str(output),
        "generated_mbtiles_SHA256":hashlib.sha256(Path(output).read_bytes()).hexdigest(),
        **result,
        "no_ocean_RGB_pixel_generated":True,
        "no_coastal_mixed_tile_generated":True,
        "no_synthetic_elevations":True,
        "original_source_precedence_preserved":True,
        "quitasueno_excluded":True,
        "national_Terrain_RGB_release_authorized":False,
    }
    report=Path(output).with_suffix(".report.json")
    report.write_text(json.dumps(evidence,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(evidence,indent=2,ensure_ascii=False),flush=True)
    return evidence


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-manifest",type=Path,required=True)
    p.add_argument("--osm-land-clip",type=Path,required=True)
    p.add_argument("--osm-land-meta",type=Path,required=True)
    p.add_argument("--osm-country-geojson",type=Path,required=True)
    p.add_argument("--bbox",type=float,nargs=4,required=True,
                   metavar=("WEST","SOUTH","EAST","NORTH"))
    p.add_argument("--minzoom",type=int,default=11)
    p.add_argument("--maxzoom",type=int,default=13)
    p.add_argument("--max-tiles",type=int,default=500)
    p.add_argument("--cache",type=Path,default=Path("output/native-cog-cache"))
    p.add_argument("--output",type=Path,default=Path("output/osm-land-only-pilot.mbtiles"))
    a=p.parse_args()
    run(a.source_manifest,a.osm_land_clip,a.osm_land_meta,
        a.osm_country_geojson,a.output,a.bbox,a.minzoom,
        a.maxzoom,a.max_tiles,a.cache)


if __name__=="__main__":
    main()
