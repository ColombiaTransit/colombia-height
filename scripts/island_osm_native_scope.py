#!/usr/bin/env python3
"""Locate exact OSM island polygons around named probes and audit z13 native gaps.

The probes select *research geometries*, not legal Colombian territory.
Only OSM polygons containing the given probe are selected; no buffer is
treated as land. A candidate COG is never approved by this test.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from shapely import contains_xy
from shapely.geometry import Point
from shapely.ops import unary_union

from osm_land_reference import load_clip
from osm_national_land_audit import native_dem_mask
from national_land_coverage import load_references
from national_tile_plan import parse_manifest
from official_territory_screen import cell_geometry, xyz_geometry

ISLAND_IDS=("malpelo","gorgona","gorgonilla","san_andres","providencia","santa_catalina")
MAX_ISLAND_AREA_DEG2=.35


def choose_island_polygons(polygons, probes):
    """Point-in-polygon only, no buffered land or mainland inference."""
    out={}
    for p in probes:
        if p["id"] not in ISLAND_IDS:
            continue
        pt=Point(float(p["lon"]),float(p["lat"]))
        hits=[g for g in polygons if g.covers(pt)]
        if len(hits)>1:
            # OSM split polygons may overlap; merge only pieces actually
            # containing the point, not all polygons within a radius.
            geom=unary_union(hits)
        elif hits:
            geom=hits[0]
        else:
            out[p["id"]]={"status":"probe_not_in_osm_land_polygon","geometry":None}
            continue
        if geom.area>MAX_ISLAND_AREA_DEG2:
            out[p["id"]]={"status":"polygon_too_large_for_island_provenance","geometry":None,
                           "area_degrees_squared":float(geom.area)}
            continue
        out[p["id"]]={"status":"point_contained_in_OSM_land_polygon",
                       "geometry":geom,"area_degrees_squared":float(geom.area),
                       "bounds":list(geom.bounds)}
    if set(out)!=set(ISLAND_IDS):
        raise AssertionError("Named-island probe registry incomplete")
    return out


def count_island_pixel_gaps(missing, lon, lat, polygon, candidate_cells):
    if any(np.asarray(a).shape!=(256,256) for a in (missing,lon,lat)):
        raise ValueError("Pixel alignment must be 256x256")
    mask=np.asarray(contains_xy(polygon,lon.ravel(),lat.ravel()),dtype=bool).reshape((256,256))
    missing_island=mask & missing
    by_candidate={}
    for name in candidate_cells:
        cell=cell_geometry(name)
        west,south,_,_=cell.bounds
        inside=(np.floor(lon)==west)&(np.floor(lat)==south)
        by_candidate[name]=int(np.count_nonzero(missing_island&inside))
    return int(mask.sum()),int(missing_island.sum()),by_candidate


def run(osm_clip,osm_metadata,osm_report,probes_path,manifest,output):
    metadata=json.loads(Path(osm_metadata).read_text())
    report=json.loads(Path(osm_report).read_text())
    probes=json.loads(Path(probes_path).read_text())["locations"]
    sources=parse_manifest(manifest)
    if (len(sources)!=137 or report.get("tiles_checked")!=1917
            or report.get("source_candidate_total")!=52
            or report.get("national_publication_allowed") is not False
            or metadata.get("national_publication_allowed") is not False):
        raise AssertionError("Baseline source inventory or evidence not verified")
    polygons=load_clip(osm_clip,metadata["reference_wkb_sha256"])
    islands=choose_island_polygons(polygons,probes)
    refs=load_references()
    opened={}
    cache=Path(output).parent/"source-cache"
    cache.mkdir(parents=True,exist_ok=True)
    rows=[]
    stats={}
    try:
        for name,record in islands.items():
            geom=record["geometry"]
            if geom is None:
                stats[name]={"status":record["status"],"z13_tiles":0,
                             "missing_native_island_pixels":None,
                             "source_candidate_hits":{}}
                continue
            tiles=[r for r in report["per_tile"] if
                   xyz_geometry(r["z"],r["x"],r["y"]).intersects(geom)]
            total=Counter()
            candidate_hits=Counter()
            for r in tiles:
                tile=(r["z"],r["x"],r["y"])
                valid=native_dem_mask(sources,opened,cache,tile)
                if int((~valid).sum())!=r["native_missing_dem_pixels"]:
                    raise AssertionError(f"Frozen native DEM mask changed at {tile}")
                _,_,lon,lat=refs.masks(tile)
                island_pixels,missing_pixels,by_cog=count_island_pixel_gaps(
                    ~valid,lon,lat,geom,r["per_candidate_omitted_cog"].keys())
                if missing_pixels>island_pixels:
                    raise AssertionError("Missing exceeds island land")
                total["tiles"]+=1
                total["OSM_island_pixel_centers"]+=island_pixels
                total["missing_native_island_pixels"]+=missing_pixels
                for cog,n in by_cog.items():
                    candidate_hits[cog]+=n
                rows.append({"island":name,"zxy":list(tile),
                             "OSM_island_pixels":island_pixels,
                             "missing_native_island_pixels":missing_pixels,
                             "missing_inside_unselected_source_cells":by_cog,
                             "no_country_ownership_inferred":True})
            stats[name]={"status":record["status"],"bounds":record["bounds"],
                         "area_degrees_squared":record["area_degrees_squared"],
                         "z13_tiles":total["tiles"],
                         "OSM_island_pixel_centers":total["OSM_island_pixel_centers"],
                         "missing_native_island_pixels":total["missing_native_island_pixels"],
                         "source_candidate_hits":dict(candidate_hits),
                         "polygon_is_not_official_territory":True}
    finally:
        for dataset in opened.values():
            dataset.close()
    result={"status":"named_island_OSM_polygon_native_DEM_z13_diagnostic",
            "created_utc":datetime.now(timezone.utc).isoformat(),
            "selected_COG_count_unchanged":137,
            "named_island_probes_checked":len(ISLAND_IDS),
            "islands":stats,"per_tile":rows,
            "quitasueno_excluded":True,
            "named_island_probe_does_not_certify_jurisdiction":True,
            "outside_OSM_land_not_ocean":True,
            "no_synthetic_elevations":True,
            "COGs_promoted":0,
            "national_publication_allowed":False,
            "source_attribution":metadata.get("odbl_attribution")}
    path=Path(output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="per_tile"},indent=2,ensure_ascii=False),flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--osm-clip",type=Path,default=Path("output/osm-reference/osm-land-study.wkb.gz"))
    p.add_argument("--osm-metadata",type=Path,default=Path("output/osm-reference/osm-land-study-metadata.json"))
    p.add_argument("--osm-report",type=Path,default=Path("output/osm-audit/osm-national-native-land-report.json"))
    p.add_argument("--probes",type=Path,default=Path("data/colombia-island-probes.json"))
    p.add_argument("--manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    p.add_argument("--output",type=Path,default=Path("output/island-osm/native-island-polygon-qa.json"))
    a=p.parse_args()
    run(a.osm_clip,a.osm_metadata,a.osm_report,a.probes,a.manifest,a.output)


if __name__=="__main__":
    main()
