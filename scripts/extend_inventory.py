#!/usr/bin/env python3
"""Extend the Colombia DEM inventory with named offshore sampling locations.

The original geoBoundaries-only inventory is retained as a baseline. Additional
1-degree DEM COGs are included for the explicitly nominated offshore samples.
Natural Earth land and minor-island geometries are *comparison only*; they
do not confer jurisdiction and cannot by themselves select Colombian land.
"""
import argparse
import csv
import io
import json
import math
from pathlib import Path
from zipfile import ZipFile

import requests
import shapefile
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from inventory import BOUNDARY_URL, TILES_URL, get_json, inspect_size, parse_tile

NE_SOURCES = {
    "ne_10m_land": "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_land.zip",
    "ne_10m_minor_islands": "https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_minor_islands.zip",
}
FIELDS = ["name","latitude","longitude","size_bytes","status","url","selection_reasons"]

def ne_shapes(url):
    response=requests.get(url,timeout=90)
    response.raise_for_status()
    with ZipFile(io.BytesIO(response.content)) as archive:
        names=archive.namelist()
        shp_name=next(n for n in names if n.endswith(".shp"))
        base=shp_name[:-4]
        reader=shapefile.Reader(
            shp=io.BytesIO(archive.read(base+".shp")),
            shx=io.BytesIO(archive.read(base+".shx")),
            dbf=io.BytesIO(archive.read(base+".dbf")),
        )
        return [shape(s.__geo_interface__) for s in reader.shapes()]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--inventory",type=Path,default=Path("output"))
    p.add_argument("--islands",type=Path,default=Path("data/colombia-island-probes.json"))
    args=p.parse_args()
    inventory=args.inventory
    baseline=inventory/"colombia_dem_manifest.csv"
    if not baseline.exists():
        raise FileNotFoundError(f"Run scripts/inventory.py first: {baseline}")
    summary_file=inventory/"colombia_dem_summary.json"
    summary=json.loads(summary_file.read_text())
    registry=json.loads(args.islands.read_text())
    entries=registry["locations"]
    if len({a["id"] for a in entries})!=len(entries):
        raise ValueError("Duplicate island registry IDs")

    source=requests.get(TILES_URL,timeout=90)
    source.raise_for_status()
    index={}
    for line in source.text.splitlines():
        item=parse_tile(line)
        if item:
            index[(item["latitude"],item["longitude"])]=item

    previous={}
    with baseline.open(newline="",encoding="utf-8") as f:
        for row in csv.DictReader(f):
            previous[row["name"]]=dict(row)
    original_names=set(previous)
    if not previous:
        raise ValueError("Existing inventory is empty")
    for item in previous.values():
        item["selection_reasons"]="geoBoundaries_ADM0"

    metadata=get_json(BOUNDARY_URL)
    gj=get_json(metadata["gjDownloadURL"])
    country=unary_union([shape(f["geometry"]) for f in gj["features"]])
    ne_layers={}
    for key,url in NE_SOURCES.items():
        print("Fetching coastline reference", key,flush=True)
        ne_layers[key]=ne_shapes(url)

    details=[]
    for location in entries:
        lon=float(location["lon"]);lat=float(location["lat"])
        if not (-90<=lat<=90 and -180<=lon<=180):
            raise ValueError(f"Invalid sampling point: {location['id']}")
        cell=(math.floor(lat),math.floor(lon))
        tile=index.get(cell)
        point=Point(lon,lat)
        in_boundary=country.covers(point)
        matches={k:any(g.covers(point) for g in v) for k,v in ne_layers.items()}
        details.append({
            **location,
            "degree_cell":{"latitude":cell[0],"longitude":cell[1]},
            "copernicus_source_exists":bool(tile),
            "copernicus_source":tile["name"] if tile else None,
            "in_geoboundaries_colombia":bool(in_boundary),
            "in_natural_earth_land":bool(matches["ne_10m_land"]),
            "in_natural_earth_minor_islands":bool(matches["ne_10m_minor_islands"]),
            "caution":"Sampling point only; not a legally validated territory polygon",
        })
        if tile:
            if tile["name"] not in previous:
                inspected=inspect_size(tile)
                inspected["selection_reasons"]="island_probe:"+location["id"]
                previous[tile["name"]]=inspected
            else:
                existing=previous[tile["name"]]
                existing["selection_reasons"]+=";island_probe:"+location["id"]

    new_names=set(previous)-original_names
    values=sorted(previous.values(),key=lambda x:(int(x["latitude"]),int(x["longitude"])))
    with (inventory/"colombia_dem_manifest_extended.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(values)
    added_bytes=sum(int(previous[n]["size_bytes"]) for n in new_names if previous[n]["size_bytes"])
    final_bytes=sum(int(t["size_bytes"]) for t in values if t["size_bytes"])
    missing=[x for x in details if not x["copernicus_source_exists"]]
    unresolved_sizes=[t["name"] for t in values if t["status"]!="ok"]
    report={
        "baseline_inventory_tile_count":len(original_names),
        "extended_unique_tile_count":len(values),
        "new_unique_tiles":len(new_names),
        "new_tile_names":sorted(new_names),
        "new_download_bytes":added_bytes,
        "extended_download_bytes":final_bytes,
        "extended_download_gib":round(final_bytes/1024**3,3),
        "unresolved_source_tile_sizes":unresolved_sizes,
        "missing_probe_source_count":len(missing),
        "missing_probe_ids":[x["id"] for x in missing],
        "registry_points":len(details),
        "registry":details,
        "references":{
            "country_boundary":metadata["gjDownloadURL"],
            "natural_earth":NE_SOURCES,
            "natural_earth_usage":"independent geometry reference, not sovereign attribution",
        },
        "acceptance_warning":"This is a named-location offshore inventory, not proof that every Colombian island or cay has been identified. Verify jurisdiction and geometry with IGAC/official sources before any national release.",
    }
    out=inventory/"colombia_island_coverage_report.json"
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="registry"},indent=2),flush=True)

if __name__=="__main__":
    main()
