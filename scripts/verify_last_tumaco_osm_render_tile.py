#!/usr/bin/env python3
"""Finish precisely ONE offshore Tumaco z13 OSM tile, never DEM or global OSM.

Uses only the previously verified bounded OSM coastline+islet evidence and
a pair of OpenStreetMap Standard rendered raster PNGs:
  * target z13/2297/4050, partial OSM Colombia administrative overlap;
  * control z13/2290/4050, an ocean-only reference far west of the coast.

OSM standard water background must be visually uniform and IDENTICAL in both
raster tiles, with no OSM coastline/islet geometry intersecting the target.
This is a *render-resolution* OSM-land negative control, not a replacement
for the authoritative assembled OSMCoastline vector masks in the generator.
No marine bathymetry, zero-height interpolation, or DEM sample is modified.
"""
import argparse
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import requests
from PIL import Image

TARGET=(13,2297,4050)
REFERENCE=(13,2290,4050)
OSM_STANDARD="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
UA="ColombiaTransit/colombia-height OSM-only single-tile DEM land QA (github.com/ColombiaTransit/colombia-height)"
MAX_SIZE=500_000


def fetch_single_osm_render(session,zxy):
    z,x,y=zxy
    url=OSM_STANDARD.format(z=z,x=x,y=y)
    response=session.get(url,headers={"User-Agent":UA,"Accept":"image/png"},timeout=(15,60))
    response.raise_for_status()
    if response.headers.get("Content-Type","").split(";")[0].lower()!="image/png":
        raise RuntimeError("OSM Standard did not return a real PNG")
    if len(response.content)>MAX_SIZE:
        raise AssertionError("Unexpected OSM tile size; tile not plain map raster")
    with Image.open(io.BytesIO(response.content)) as im:
        image=np.asarray(im.convert("RGB"),dtype=np.uint8)
    if image.shape!=(256,256,3):
        raise AssertionError("Unexpected OSM Standard 256x256 map tile resolution")
    colours,counts=np.unique(image.reshape((-1,3)),axis=0,return_counts=True)
    i=int(np.argmax(counts))
    return {
        "tile_url":url,
        "png_sha256":hashlib.sha256(response.content).hexdigest(),
        "ocean_candidate_colour_RGB":colours[i].astype(int).tolist(),
        "dominant_colour_pixels":int(counts[i]),
        "unique_rgb_colour_count":len(colours),
        "all_pixels_identical":bool(len(colours)==1),
        "pixel_rgb":image,
    }


def check_against_existing_osm_coast_evidence(original,target,reference):
    if (original.get("country_relation",{}).get("osm_relation")!=120027
            or original.get("national_release_approved") is not False
            or len(original.get("new_140_only_68_tiles",[]))!=68):
        raise AssertionError("Original verified localized OSM shoreline/country evidence changed")
    candidate=[r for r in original["new_140_only_68_tiles"] if r["zxy"]==list(TARGET)]
    if len(candidate)!=1:
        raise AssertionError("Exactly one original Tumaco offshore Colombia-boundary tile expected")
    row=candidate[0]
    if (row["old_140_native_missing_pixels"]!=31232
            or row["OSM_COL_country_relation_tile_context"]!="partial_OSM_Colombia_relation_tile"
            or row["OSM_direct_coastline_way_ids_in_tile"]
            or row["OSM_closed_CCW_coastline_land_poly_hits"]!=0
            or row["OSM_named_island_area_hint_hits"]!=0):
        raise AssertionError("Original exact 140 and local OSM coastline evidence inconsistent")
    if not reference["all_pixels_identical"]:
        raise AssertionError("Offshore control OSM Standard tile has colours other than ocean background")
    colour=reference["ocean_candidate_colour_RGB"]
    if target["ocean_candidate_colour_RGB"]!=colour:
        raise AssertionError("OSM target has different dominant map colour from verified ocean control")
    target_ocean_mask=np.all(target["pixel_rgb"]==np.array(colour,dtype=np.uint8),axis=2)
    count=int(np.count_nonzero(target_ocean_mask))
    return {
        "source_native_140_missing_DEM_pixel_centers":31232,
        "OSM_standard_target_pixels_matching_offshore_reference_colour":count,
        "OSM_standard_target_pixels_not_matching_offshore_reference_colour":65536-count,
        "OSM_standard_target_uniform_ocean_background":bool(count==65536),
        "local_OSM_natural_coastline_way_intersections":0,
        "local_OSM_closed_CCW_land_island_polygon_intersections":0,
        "local_OSM_named_island_area_intersections":0,
        "native_DEM_values_recomputed":0,
        "global_OSM_coastline_archive_downloaded":False,
        "OSM_standard_render_is_not_certified_vector_pixel_land_mask":True,
        "OSM_source_scope_land_at_z13_render_resolution_not_demonstrated":bool(count==65536),
        "render_level_offshore_exception_resolved":bool(count==65536),
        "release_status":"generator_native_land_mask_and_renderer_validation_still_pending",
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original-osm",type=Path,default=Path("output/previous-osm/osm-colombia-land-scope.json"))
    p.add_argument("--output",type=Path,default=Path("output/tumaco-last-offshore-tile/osm-render-ocean-reference.json"))
    args=p.parse_args()
    evidence=json.loads(args.original_osm.read_text())
    with requests.Session() as session:
        target=fetch_single_osm_render(session,TARGET)
        control=fetch_single_osm_render(session,REFERENCE)
    checks=check_against_existing_osm_coast_evidence(evidence,target,control)
    if not checks["render_level_offshore_exception_resolved"]:
        raise AssertionError("OSM Standard imagery still has a non-ocean pixel; investigate exactly this tile further")
    report={
        "status":"targeted_offshore_Tumaco_13_2297_4050_OSM_render_and_local_coast_negative_control",
        "checked_utc":datetime.now(timezone.utc).isoformat(),
        "target_tile_zxy":list(TARGET),
        "ocean_control_tile_zxy":list(REFERENCE),
        "osm_standard_target":{
            k:v for k,v in target.items() if k!="pixel_rgb"},
        "osm_standard_ocean_control":{
            k:v for k,v in control.items() if k!="pixel_rgb"},
        **checks,
        "Colombia_OSM_relation_used_only_for_geographic_scope":120027,
        "physical_land_rule":"Only assembled OSM natural=coastline land polygons require GLO-30 heights; marine/ocean DEM is unnecessary",
        "the_tile_does_not_authorize_national_publication":True,
        "osm_attribution":"© OpenStreetMap contributors (ODbL 1.0), https://www.openstreetmap.org/copyright",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(report,indent=2,ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
