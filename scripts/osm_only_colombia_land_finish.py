#!/usr/bin/env python3
"""OSM-ONLY Colombia LAND gate for 140 staged Copernicus DEM sources.

Uses ALREADY VERIFIED native NoData counts for 27 old-scope and 68 NEW
z13 tiles. Never recomputes a native DEM, regenerates the 139 or 140 COG
manifest, downloads global osmcoastline, or creates bathymetry.

Reference A: OpenStreetMap's *Colombia admin_level=2 relation 120027*
provided directly by Nominatim OSM lookup. This is a project-scope
reference, NOT a coastline mask and not a legal boundary certification.
Reference B: bounded original OSM natural=coastline ways and island/islet
hints from Overpass, covering only the newly added Tumaco region.
A closed CCW coastline is positive OSM land. An open segment or named
node does not establish land polygons or ocean.

Report never claims unknown pixel centers are ocean. It eliminates
tiles only where the OSM Colombia country relation does not INTERSECT
the tile; otherwise old exact OSM-land deficits remain pending precise
pixel-level Colombia boundary intersection. At a z13 new tile, actual
missing OSM-land pixels are unknown until a local closed land polygon
is available; coastline/land and boundary are two separate dimensions.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import requests
from shapely.geometry import LineString, Point, Polygon, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

from official_territory_screen import xyz_geometry

OSM_COL_RELATION=120027
NOMINATIM="https://nominatim.openstreetmap.org/lookup"
OVERPASS="https://overpass-api.de/api/interpreter"
ALT_OVERPASS="https://overpass.kumi.systems/api/interpreter"
PAD=.08
MAX_OSM_COUNTRY_BYTES=65_000_000
MAX_OVERPASS_BYTES=14_000_000
EXPECTED_OLD_TILES=27
EXPECTED_OLD_LAND_MISSING=394622
EXPECTED_NEW_TILES=68
EXPECTED_NEW_NATIVE_MISSING=2688103
HEADERS={"User-Agent":"ColombiaTransit-OSM-only-Colombia-land-DEM-audit/1.0 (github.com/ColombiaTransit/colombia-height)",
         "Accept":"application/json"}


def candidate_tiles(old_register,new_register):
    old=old_register["remaining_140_ambiguous_tile_priorities"]
    if (len(old)!=EXPECTED_OLD_TILES
            or sum(int(v["missing_native_pixels_inside_OSM_land"]) for v in old)!=EXPECTED_OLD_LAND_MISSING
            or old_register["remaining_known_IGAC_department_and_OSM_land_missing_pixels"]!=0
            or old_register["national_publication_allowed"] is not False):
        raise AssertionError("Original previously OSM-positive unresolved 27-tile worklist mutated")
    old_tiles=[{
        "zxy":[r["z"],r["x"],r["y"]],
        "old_140_OSM_land_native_missing_pixels":r["missing_native_pixels_inside_OSM_land"],
        "study_group":"previously_OSM_land_confirmed",
    } for r in old]
    other=new_register["groups"]
    if (new_register["studied_scope"]["new_140_only_z13_incomplete_tiles"]!=68
            or new_register["studied_scope"]["original_native_NoData_pixel_centers"]!=EXPECTED_NEW_NATIVE_MISSING
            or new_register["source_inventory"]["staged_COGs"]!=140
            or new_register["conclusions"]["national_Terrain_RGB_publication_allowed"] is not False):
        raise AssertionError("140 new-study worklist does not match native verified COG results")
    groups=other["no_COL_or_ECU_ADM0_polygon_contact_unknown_not_ocean"]["compressed_tile_roster"]
    groups+=([
        {"z":13,"y":4073,"x_min":2281,"x_max":2286,"NoData_each":49920},
        {"z":13,"y":4073,"x_min":2287,"x_max":2297,"NoData_each":49920},
    ])
    new_tiles=[]
    for g in groups:
        if "x" in g and "y" in g:
            new_tiles.append({"zxy":[g["z"],g["x"],g["y"]],
                              "old_140_native_missing_pixels":g["NoData"],
                              "study_group":"new_140_no_exact_OSM_land_mask"})
        elif "x_min" in g:
            for x in range(g["x_min"],g["x_max"]+1):
                new_tiles.append({"zxy":[g["z"],x,g["y"]],
                                  "old_140_native_missing_pixels":g["NoData_each"],
                                  "study_group":"new_140_no_exact_OSM_land_mask"})
        elif "y_min" in g:
            for y in range(g["y_min"],g["y_max"]+1):
                new_tiles.append({"zxy":[g["z"],g["x"],y],
                                  "old_140_native_missing_pixels":g["NoData_each"],
                                  "study_group":"new_140_no_exact_OSM_land_mask"})
        else:
            raise AssertionError("Malformed compressed 68-tile native source roster")
    if (len(new_tiles)!=EXPECTED_NEW_TILES
            or len({tuple(t["zxy"]) for t in new_tiles})!=EXPECTED_NEW_TILES
            or sum(t["old_140_native_missing_pixels"] for t in new_tiles)!=EXPECTED_NEW_NATIVE_MISSING
            or {tuple(x["zxy"]) for x in old_tiles}&{tuple(x["zxy"]) for x in new_tiles}):
        raise AssertionError("OSM study new native tile roster not exactly 68 or totals mismatch")
    return old_tiles,new_tiles


def get_osm_col_boundary(session):
    r=session.get(NOMINATIM,params={
        "osm_ids":f"R{OSM_COL_RELATION}","format":"json",
        "polygon_geojson":1,"polygon_threshold":0
    },timeout=(20,150),headers=HEADERS)
    r.raise_for_status()
    if len(r.content)>MAX_OSM_COUNTRY_BYTES:
        raise RuntimeError("OSM Colombia relation exceeds bounded research size")
    items=r.json()
    if len(items)!=1 or int(items[0].get("osm_id",0))!=OSM_COL_RELATION:
        raise ValueError("Wrong OSM Colombia relation ID returned")
    geojson=items[0].get("geojson")
    if not geojson:
        raise ValueError("Country boundary lacks polygon geometry")
    geom=shape(geojson)
    if not geom.is_valid:
        geom=make_valid(geom)
    if geom.is_empty or geom.geom_type not in ("Polygon","MultiPolygon"):
        raise ValueError("OSM Colombia returned no valid polygon")
    # OSM relation 120027 should contain Bogotá, Antioquia, etc.
    if not geom.covers(Point(-74.072,4.711)):
        raise AssertionError("OSM Colombia relation geometry does not contain Bogotá")
    return geom,{
        "endpoint":r.url,
        "osm_relation":OSM_COL_RELATION,
        "osm_type":items[0].get("osm_type"),
        "display_name":items[0].get("display_name"),
        "geometry_type":geom.geom_type,
        "coordinate_outline_bounds":list(geom.bounds),
        "geometry_provenance":"OSM Nominatim admin_level=2 relation, country scope NOT coastline",
    }


def region_bbox(rows):
    boxes=[xyz_geometry(*x["zxy"]).bounds for x in rows]
    bounds=[min(x[0] for x in boxes)-PAD,min(x[1] for x in boxes)-PAD,
            max(x[2] for x in boxes)+PAD,max(x[3] for x in boxes)+PAD]
    if bounds[2]-bounds[0]>2 or bounds[3]-bounds[1]>2:
        raise AssertionError("OSM local coastline request exceeds tiny Tumaco region")
    return bounds


def get_tumaco_osm_coast(session,bounds):
    w,s,e,n=bounds
    query=(f'[out:json][timeout:100];('
           f'way["natural"="coastline"]({s},{w},{n},{e});'
           f'way["place"~"^(island|islet)$"]({s},{w},{n},{e});'
           f'relation["place"~"^(island|islet)$"]({s},{w},{n},{e});'
           f'node["place"~"^(island|islet)$"]({s},{w},{n},{e});'
           ');out body geom;')
    last=None
    for api in (OVERPASS,ALT_OVERPASS):
        try:
            r=session.post(api,data={"data":query},headers=HEADERS,timeout=(20,125))
            r.raise_for_status()
            if len(r.content)>MAX_OVERPASS_BYTES:
                raise RuntimeError("Overpass OSM coast study response too large")
            j=r.json()
            if "remark" in j:
                raise ValueError("Overpass gave incomplete response: "+str(j["remark"])[:150])
            elements=j.get("elements")
            if not isinstance(elements,list):
                raise ValueError("Overpass has no OSM elements")
            return elements,{"api":api,"bbox_lonlat":bounds,
                             "OSM_objects_returned":len(elements),
                             "query":"natural=coastline and OSM place=island/islet in bounded Tumaco box"}
        except (requests.RequestException,ValueError,RuntimeError) as error:
            last=error
            print("OSM_COASTLINE_ENDPOINT_FAILED",api,str(error)[:160],flush=True)
    raise RuntimeError("Neither bounded OSM coastline endpoint available: "+str(last))


def geometry_candidates(elements):
    """Closed CCW coast is land; OSM island nodes are hints only."""
    coastlines=[]
    island_closed=[]
    island_hints=[]
    land_polys=[]
    for e in elements:
        typ=e.get("type")
        tags=e.get("tags") or {}
        if typ=="node":
            if tags.get("place") in ("island","islet"):
                island_hints.append({"osm_type":typ,"osm_id":e["id"],
                                     "lon":e["lon"],"lat":e["lat"],
                                     "name":tags.get("name")})
            continue
        geo=e.get("geometry") or []
        coords=[(p["lon"],p["lat"]) for p in geo if "lon" in p and "lat" in p]
        if tags.get("natural")=="coastline" and typ=="way":
            if len(coords)<2:
                raise ValueError("OSM coastline way has no geometry; query incomplete")
            line=LineString(coords)
            coastlines.append({"line":line,"id":e["id"],"closed":line.is_ring})
            if line.is_ring and len(set(coords))>=3:
                ring=Polygon(coords)
                # OSM shoreline has land to the left of the digitized way,
                # i.e. closed CCW ring is a candidate land island.
                from shapely.geometry import LinearRing
                if ring.is_valid and ring.area>0 and LinearRing(coords).is_ccw:
                    land_polys.append(ring)
        if tags.get("place") in ("island","islet"):
            island_hints.append({"osm_type":typ,"osm_id":e["id"],"name":tags.get("name")})
            if typ=="way" and len(coords)>3 and coords[0]==coords[-1]:
                polygon=Polygon(coords)
                if polygon.is_valid and polygon.area>0:
                    island_closed.append(polygon)
    return coastlines,land_polys,island_closed,island_hints


def tile_osm_context(tile,country,coasts,land_polygons,island_polys):
    rect=xyz_geometry(*tile)
    if country.covers(rect):
        col_context="complete_OSM_Colombia_relation_coverage_tile"
    elif country.disjoint(rect):
        col_context="disjoint_OSM_Colombia_relation"
    else:
        col_context="partial_OSM_Colombia_relation_tile"
    direct=[x for x in coasts if x["line"].intersects(rect)]
    shore=[x["id"] for x in direct]
    island_land=[p for p in land_polygons if p.intersects(rect)]
    named_island=[p for p in island_polys if p.intersects(rect)]
    return {
        "OSM_COL_country_relation_tile_context":col_context,
        "OSM_direct_coastline_way_ids_in_tile":shore[:100],
        "OSM_closed_CCW_coastline_land_poly_hits":len(island_land),
        "OSM_named_island_area_hint_hits":len(named_island),
        "actual_missing_pixels_inside_OSM_land_proven":False,
        "no_coastline_or_named_island_in_tile_does_NOT_certify_ocean":True,
        "must_not_fill_ocean_height_zero":True,
    }


def categorize(existing,new,country,coasts,polygons,island_polys):
    old_categories=Counter()
    new_categories=Counter()
    old_counts=Counter()
    new_counts=Counter()
    old_out=[]
    new_out=[]
    for row in existing:
        info=tile_osm_context(row["zxy"],country,[],[],[])
        category=info["OSM_COL_country_relation_tile_context"]
        old_categories[category]+=1
        old_counts[category]+=row["old_140_OSM_land_native_missing_pixels"]
        old_out.append({**row,**info})
    for row in new:
        info=tile_osm_context(row["zxy"],country,coasts,polygons,island_polys)
        category=info["OSM_COL_country_relation_tile_context"]
        new_categories[category]+=1
        new_counts[category]+=row["old_140_native_missing_pixels"]
        new_out.append({**row,**info})
    if (sum(old_categories.values())!=EXPECTED_OLD_TILES
            or sum(old_counts.values())!=EXPECTED_OLD_LAND_MISSING
            or sum(new_categories.values())!=EXPECTED_NEW_TILES
            or sum(new_counts.values())!=EXPECTED_NEW_NATIVE_MISSING):
        raise AssertionError("OSM country-only scope category ledger doesn't reconcile")
    return {
        "old_known_OSM_land_country_reference_groups":dict(old_categories),
        "old_known_OSM_land_missing_pixels_by_country_scope":dict(old_counts),
        "new_140_only_native_NoData_OSM_country_reference_groups":dict(new_categories),
        "new_140_only_native_NoData_by_country_scope":dict(new_counts),
        "old_known_OSM_land_27_tiles":old_out,
        "new_140_only_68_tiles":new_out,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--old-register",type=Path,default=Path(
        "data/staged140-residual-geography-2026-11-14.json"))
    p.add_argument("--new-register",type=Path,default=Path(
        "data/tumaco140-new-tiles-geo-reference-2026-11-14.json"))
    p.add_argument("--output",type=Path,default=Path(
        "output/osm-only-land-finish/osm-colombia-land-scope.json"))
    a=p.parse_args()
    old=json.loads(a.old_register.read_text())
    new=json.loads(a.new_register.read_text())
    existing,added=candidate_tiles(old,new)
    session=requests.Session()
    col,meta=get_osm_col_boundary(session)
    bounds=region_bbox(added)
    data,coast_meta=get_tumaco_osm_coast(session,bounds)
    coasts,land,island_hints,point_hints=geometry_candidates(data)
    result=categorize(existing,added,col,coasts,land,island_hints)
    summary={
        "status":"OSM_only_bounded_Colombia_land_scope_coast_and_border_reconciliation",
        "date_utc":datetime.now(timezone.utc).isoformat(),
        "land_reference":"OpenStreetMap country relation 120027 and OSM natural=coastline, not geoBoundaries, not IGAC",
        "project_scope_land_only":True,
        "sea_bathymetry_not_relevant":True,
        "ocean_tiles_do_not_require_a_DEM_elevation":True,
        "country_relation":meta,
        "coastline_data":coast_meta,
        "OSM_bounded_coastline_way_count":len(coasts),
        "OSM_bounded_closed_CCW_land_island_polygons":len(land),
        "OSM_bounded_named_island_closed_way_hints":len(island_hints),
        "OSM_bounded_named_island_node_or_way_hints":len(point_hints),
        "previous_139_source_27_known_OSM_land_tile_and_new_140_68_tile_studies_only":True,
        **result,
        "previous_27_OSM_landed_pixels_are_frozen_exact":True,
        "new_140_only_land_mask_per_pixel_still_requires_osm_coast_polygon_where_border_intersects":True,
        "no_GLO30_original_native_data_redownloaded":True,
        "no_OSM_global_land_polygon_archive_repeated":True,
        "no_national_137_139_140_source_coverage_rerun":True,
        "no_source_manifest_mutation":True,
        "quitasueno_excluded":True,
        "no_ocean_bathymetry_or_synthetic_height_added":True,
        "national_release_approved":False,
        "interpretation":"OSM admin relation is not physical land. Only previously OSM-land-positive pixels (27 tiles) are exact land deficits. New 68 tiles require land from coastline polygons if their OSM country boundary overlaps; no shoreline alone does not prove sea.",
        "OSM_attribution":"© OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright",
    }
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
    condensed={k:v for k,v in summary.items() if k not in (
        "old_known_OSM_land_27_tiles","new_140_only_68_tiles")}
    print(json.dumps(condensed,ensure_ascii=False,indent=2),flush=True)


if __name__=="__main__":
    main()
