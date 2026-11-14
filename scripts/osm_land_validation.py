#!/usr/bin/env python3
"""OSM land-polygon reference pilot for existing native Copernicus DEM masks.

OSM land polygons are physical land, not sovereign Colombian territory.
Never use a missing OSM polygon to invent an ocean height. Never change
the 137 selected COGs or authorize publication. All outputs diagnostic.
"""
import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import numpy as np
import requests
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from shapely.geometry import box, shape, mapping
from shapely.ops import transform as geom_transform, unary_union
from shapely.strtree import STRtree
from pyproj import Transformer

from national_land_coverage import SITES, missing_categories, site_tiles, load_references
from national_tile_plan import parse_manifest
from national_dem_coverage import intersecting_source_indices, local_cogs
from two_cog_seam_pilot import warp_sources

OSM_URL="https://osmdata.openstreetmap.de/download/land-polygons-split-4326.zip"
STUDY_BBOX=(-84.0,-5.0,-66.0,17.0)
# This is only a research envelope; do not use as Colombia jurisdiction.
OSM_LICENSE="ODbL 1.0 © OpenStreetMap contributors"
CATS=("missing_osm_and_geoboundaries_land","missing_osm_only_land",
      "missing_geoboundaries_only_land","missing_outside_both_unknown")


def download_zip(dest, url=OSM_URL):
    """Stream to temporary file; bounded size; do not persist full global dataset."""
    if url != OSM_URL:
        raise ValueError("Only the documented OSM land polygon source is allowed")
    dest=Path(dest)
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=dest.with_suffix(".part")
    digest=hashlib.sha256()
    total=0
    try:
        with requests.get(url,stream=True,timeout=(25,180),headers={
            "User-Agent":"ColombiaTransit-OSM-land-audit/1.0"}) as response:
            response.raise_for_status()
            with temp.open("wb") as out:
                for block in response.iter_content(chunk_size=2**20):
                    if not block:
                        continue
                    total+=len(block)
                    if total>1_500_000_000:
                        raise RuntimeError("Global OSM archive exceeds 1.5GB safety limit")
                    digest.update(block)
                    out.write(block)
        if not zipfile.is_zipfile(temp):
            raise RuntimeError("OSM archive is not a ZIP")
        temp.replace(dest)
    finally:
        temp.unlink(missing_ok=True)
    return {"download_url":url,"downloaded_bytes":total,"sha256":digest.hexdigest()}


def clip_osm_land(archive, destination):
    """Extract only shapefile components; read bbox-filtered shapes via Fiona.

    This does not load or union the whole planet. Shapefile is indexed using
    GDAL spatial filtering; the Colombia study envelope also contains foreign
    land, which must be separated later.
    """
    import fiona
    archive=Path(archive)
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        names=[n for n in z.namelist() if n.lower().endswith(
            (".shp",".shx",".dbf",".prj",".cpg")) and not n.startswith("__MACOSX")]
        if len(names)>15 or not any(n.endswith(".shp") for n in names):
            raise RuntimeError("Unexpected OSM polygon shapefile members")
        for name in names:
            if ".." in Path(name).parts or Path(name).is_absolute():
                raise RuntimeError("Unsafe ZIP member")
            z.extract(name,destination)
    shp=next(destination.rglob("land_polygons.shp"),None)
    if shp is None:
        raise RuntimeError("OSM archive missing land_polygons.shp")
    geometries=[]
    with fiona.open(shp) as source:
        if not source.crs or "4326" not in str(source.crs):
            raise RuntimeError(f"Expected EPSG:4326 land polygons, got {source.crs}")
        for feature in source.filter(bbox=STUDY_BBOX):
            geom=shape(feature["geometry"])
            if geom.is_empty:
                continue
            if not geom.is_valid:
                geom=geom.buffer(0)
            clipped=geom.intersection(box(*STUDY_BBOX))
            if not clipped.is_empty:
                geometries.append(clipped)
    if not geometries:
        raise RuntimeError("No OSM land polygons intersect Colombia study area")
    return geometries


def mask_osm(geometries,tile):
    z,x,y=tile
    bounds=mercantile.xy_bounds(x,y,z)
    west,south,east,north=bounds.left,bounds.bottom,bounds.right,bounds.top
    t=Transformer.from_crs("EPSG:4326","EPSG:3857",always_xy=True)
    shapes=[]
    for geom in geometries:
        if not geom.is_empty:
            shapes.append((mapping(geom_transform(t.transform,geom)),1))
    return rasterize(shapes,out_shape=(256,256),
                     transform=from_bounds(west,south,east,north,256,256),
                     fill=0,dtype="uint8",all_touched=False).astype(bool)


def partition(valid,osm,gb):
    if any(a.shape!=(256,256) for a in (valid,osm,gb)):
        raise ValueError("Masks must be pixel-aligned 256x256")
    m=~valid
    counts={
        CATS[0]:int(np.count_nonzero(m&osm&gb)),
        CATS[1]:int(np.count_nonzero(m&osm&~gb)),
        CATS[2]:int(np.count_nonzero(m&~osm&gb)),
        CATS[3]:int(np.count_nonzero(m&~osm&~gb)),
    }
    if sum(counts.values())!=int(np.count_nonzero(m)):
        raise AssertionError("OSM pixel partition did not reconcile")
    return counts


def inspect_tile(sources,opened,cache,refs,land,index,tile,site):
    z,x,y=tile
    ids=intersecting_source_indices(sources,z,x,y)
    cogs=local_cogs(sources,ids,cache,opened) if ids else []
    if cogs:
        height,prov,_,_=warp_sources(cogs,tile)
        valid=(prov>0)&np.isfinite(height)&(height!=-9999.)
    else:
        valid=np.zeros((256,256),bool)
    bb=mercantile.bounds(x,y,z)
    matched=index.query(box(bb.west,bb.south,bb.east,bb.north))
    osm=mask_osm([land[int(i)] for i in matched],tile)
    gb,ne,_,_=refs.masks(tile)
    counts=partition(valid,osm,gb)
    missing=~valid
    return {"site":site,"z":z,"x":x,"y":y,
        "missing_native_dem_pixels":int(missing.sum()),
        "osm_land_pixels":int(osm.sum()),
        "osm_and_geoboundaries_land_pixels":int(np.count_nonzero(osm&gb)),
        "missing_osm_and_natural_earth_land_pixels":int(np.count_nonzero(missing&osm&ne)),
        "missing_osm_not_natural_earth_land_pixels":int(np.count_nonzero(missing&osm&~ne)),
        **counts,
        "outside_osm_land_is_not_proof_of_ocean":True,
        "osm_is_not_colombian_jurisdiction":True}


def run(manifest,archive,output,mode="pilot"):
    if mode!="pilot":
        raise ValueError("Only bounded four-site pilot implemented; full scan requires reviewed scope")
    sources=parse_manifest(manifest)
    if len(sources)!=137:
        raise AssertionError("137-source baseline changed")
    refs=load_references()
    land=clip_osm_land(archive,Path(output).parent/"osm-shape")
    index=STRtree(land)
    cache=Path(output).parent/"native-source-cache"
    cache.mkdir(parents=True,exist_ok=True)
    opened={}
    rows=[]
    try:
        for site,tile in site_tiles():
            rows.append(inspect_tile(sources,opened,cache,refs,land,index,tile,site))
    finally:
        for source in opened.values():
            source.close()
    if len(rows)!=36 or {r["site"] for r in rows}!=set(SITES):
        raise AssertionError("Four-site 36-tile pilot incomplete")
    totals={key:sum(r[key] for r in rows) for key in CATS}
    per_site={name:{"tiles":sum(r["site"]==name for r in rows),
                    "missing_dem_pixels":sum(r["missing_native_dem_pixels"] for r in rows if r["site"]==name),
                    "missing_osm_land_pixels":sum(r[CATS[0]]+r[CATS[1]] for r in rows if r["site"]==name)}
              for name in SITES}
    report={"status":"OSM_land_polygon_pilot_unapproved_reference",
            "timestamp_utc":datetime.now(timezone.utc).isoformat(),
            "source_url":OSM_URL,"source_license":OSM_LICENSE,
            "study_bbox_lonlat":list(STUDY_BBOX),
            "selected_native_cogs_unchanged":137,
            "pilot_sites":per_site,"tiles_checked":36,
            "missing_pixel_categories":totals,"tiles":rows,
            "osm_land_is_not_colombia_territory":True,
            "unknown_offshore_pixels_not_assumed_ocean":True,
            "quitasueno_excluded_from_colombia_scope":True,
            "national_publication_allowed":False,
            "no_height_values_fabricated":True}
    out=Path(output)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k!="tiles"},indent=2),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    p.add_argument("--archive",type=Path,default=Path("output/osm/land-polygons-split-4326.zip"))
    p.add_argument("--output",type=Path,default=Path("output/osm/osm-land-pilot.json"))
    p.add_argument("--download",action="store_true")
    a=p.parse_args()
    if a.download:
        info=download_zip(a.archive)
        print("OSM source provenance:",json.dumps(info),flush=True)
    run(a.manifest,a.archive,a.output)


if __name__=="__main__":
    main()
