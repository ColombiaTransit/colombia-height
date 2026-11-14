#!/usr/bin/env python3
"""Validate proposed Santa Catalina and Gorgonilla OSM island probe corrections.

Fetch only small direct OSM API map windows around source-cited candidate
coordinates. Polygonize exact closed natural=coastline ways. Unknown/out-of-
scope geometry is never converted into land or synthetic DEM heights.
Use existing original 137 source COGs for native z13 coverage only after a
closed island polygon actually contains the proposed candidate probe.
"""
import argparse
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import numpy as np
import requests
from shapely import contains_xy
from shapely.geometry import Point, Polygon, LineString, box
from shapely.ops import polygonize, unary_union

from national_tile_plan import parse_manifest
from source_scope_comparison import render_valid
from island_native_recovery_qa import xyz_centers

OSM_API = "https://api.openstreetmap.org/api/0.6/map"
ISLANDS = ("santa_catalina", "gorgonilla")
MAX_OSM_XML_BYTES = 12_000_000
MAX_MAP_EXTENT_DEGREES = .04


def bbox_for_probes(probes, pad=.007):
    lons = [float(p["lon"]) for p in probes]
    lats = [float(p["lat"]) for p in probes]
    bbox = [min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad]
    if bbox[2] - bbox[0] > MAX_MAP_EXTENT_DEGREES or bbox[3] - bbox[1] > MAX_MAP_EXTENT_DEGREES:
        raise ValueError("OSM map request would cover too broad a region")
    return bbox


def parse_osm_coastline_xml(xml_bytes, study_bbox):
    """Only polygonize actual coastline ways, not map labels or island names."""
    if len(xml_bytes) > MAX_OSM_XML_BYTES:
        raise ValueError("OSM response too large for bounded island research")
    root = ET.fromstring(xml_bytes)
    if root.tag != "osm":
        raise ValueError("Unexpected XML root: not an OSM API map response")
    nodes = {}
    for node in root.iter("node"):
        nodes[node.attrib["id"]] = (
            float(node.attrib["lon"]), float(node.attrib["lat"]))
    lines = []
    coastline_ids = []
    for way in root.iter("way"):
        tags = {t.attrib.get("k"): t.attrib.get("v")
                for t in way.findall("tag")}
        if tags.get("natural") != "coastline":
            continue
        refs = [nd.attrib["ref"] for nd in way.findall("nd")]
        if len(refs) < 4 or any(ref not in nodes for ref in refs):
            # This way is incomplete, so it cannot be converted to land.
            continue
        coords = [nodes[ref] for ref in refs]
        if len(set(coords)) < 3:
            continue
        lines.append(LineString(coords))
        coastline_ids.append(way.attrib["id"])
    if not lines:
        return [], coastline_ids
    candidates = polygonize(unary_union(lines))
    study = box(*study_bbox)
    polygons = []
    for item in candidates:
        if item.is_empty or not item.is_valid or item.area <= 0:
            continue
        # An unexpectedly massive enclosing continent/open coastline is
        # not an island even if it encloses a candidate point.
        if item.area > .02:
            continue
        if item.intersects(study):
            polygons.append(item)
    return polygons, coastline_ids


def check_candidate(polygons, lon, lat):
    point = Point(float(lon), float(lat))
    hits = [g for g in polygons if g.contains(point)]
    if not hits:
        return None
    # A coastline polygon may be split by adjacent overlapping rings.
    # The smallest enclosing polygon is the most conservative candidate.
    return min(hits, key=lambda g: g.area)


def native_polygon_coverage(sources, polygon, cache):
    bbox = polygon.bounds
    tiles = [(13, t.x, t.y) for t in mercantile.tiles(
        bbox[0] + 1e-9, bbox[1] + 1e-9,
        bbox[2] - 1e-9, bbox[3] - 1e-9, zooms=[13])]
    if not tiles or len(tiles) > 20:
        raise AssertionError("Island polygon has unreasonable z13 XYZ extent")
    opened = {}
    count_land = count_missing = 0
    records = []
    try:
        for tile in tiles:
            lon, lat = xyz_centers(tile)
            inside = np.asarray(
                contains_xy(polygon, lon.ravel(), lat.ravel()),
                dtype=bool).reshape((256, 256))
            if not inside.any():
                continue
            valid, heights = render_valid(sources, opened, cache, tile)
            if not valid.shape == inside.shape:
                raise AssertionError("Native DEM and OSM masks not aligned")
            missing = inside & ~valid
            count_land += int(inside.sum())
            count_missing += int(missing.sum())
            records.append({
                "zxy": list(tile),
                "OSM_polygon_land_pixel_centers": int(inside.sum()),
                "real_native_DEM_missing_on_OSM_polygon": int(missing.sum()),
            })
    finally:
        for dataset in opened.values():
            dataset.close()
    return {
        "tiles_with_OSM_land_centers": len(records),
        "OSM_land_pixel_centers": count_land,
        "original_137_COG_native_NoData_island_pixels": count_missing,
        "original_valid_native_pixels": count_land - count_missing,
        "tile_records": records,
        "native_source_only_no_synthetic_elevations": True,
    }


def fetch_osm_map(session, bbox):
    response = session.get(OSM_API, params={
        "bbox": ",".join(str(x) for x in bbox),
    }, headers={"User-Agent": "ColombiaTransit-OSM-island-coordinate-audit/1.0"},
        timeout=(15, 60))
    response.raise_for_status()
    if len(response.content) > MAX_OSM_XML_BYTES:
        raise ValueError("OSM map window exceeded XML size limit")
    return response.content


def run(manifest, candidates_file, output):
    sources = parse_manifest(manifest)
    if len(sources) != 137:
        raise AssertionError("Native selected DEM source count changed")
    config = json.loads(Path(candidates_file).read_text())
    candidates = config["candidates"]
    if set(x["id"] for x in candidates) != set(ISLANDS):
        raise AssertionError("Expected exactly two named island-coordinate studies")
    session = requests.Session()
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    cache = out.parent / "source-cache"
    cache.mkdir(parents=True, exist_ok=True)
    results = {}
    for entry in candidates:
        site = entry["id"]
        probes = [{"lon": p["lon"], "lat": p["lat"]}
                  for p in entry["research_probes"]]
        bbox = bbox_for_probes(probes)
        item = {
            "reference_point_candidates": entry["research_probes"],
            "old_probe": entry["old_probe"],
            "OSM_API_bbox": bbox,
            "upstream_OSM_API": OSM_API,
            "land_polygon_approval": False,
            "country_or_island_identity_verified_by_OSM_coastline_only": False,
            "probe_classification": [],
            "coastline_way_ids_in_OSM_response": [],
            "native_DEM_coverage_on_provisional_polygon": None,
        }
        try:
            xml = fetch_osm_map(session, bbox)
            polygons, way_ids = parse_osm_coastline_xml(xml, bbox)
            item["coastline_way_ids_in_OSM_response"] = way_ids[:90]
            item["closed_OSM_coastline_polygons_found"] = len(polygons)
            valid = None
            for probe in entry["research_probes"]:
                candidate = check_candidate(polygons, probe["lon"], probe["lat"])
                point_status = (
                    "point_inside_closed_OSM_coastline_polygon"
                    if candidate is not None else "no_closed_OSM_coastline_polygon_containing_point")
                result = {
                    "lat": probe["lat"], "lon": probe["lon"],
                    "evidence_type": probe["type"],
                    "point_status": point_status,
                    "polygon_bounds_lonlat": (list(candidate.bounds) if candidate is not None else None),
                    "polygon_area_square_degrees": (
                        float(candidate.area) if candidate is not None else None),
                    "identity_remains_to_be_reviewed": True,
                }
                item["probe_classification"].append(result)
                if valid is None and candidate is not None and "island" in probe["type"].lower():
                    valid = candidate
            if valid is not None:
                item["native_DEM_coverage_on_provisional_polygon"] = native_polygon_coverage(
                    sources, valid, cache)
                item["status"] = "native_DEM_coverage_measured_on_unverified_OSM_island_outline"
            else:
                item["status"] = "OSM_closed_coastline_polygon_unresolved"
        except (requests.RequestException, ValueError, ET.ParseError) as error:
            item["status"] = "OSM_API_unavailable_or_geometry_unusable_NULL"
            item["error"] = str(error)[:300]
        results[site] = item
        print("OSM_ISLAND_PROBE", site, item["status"],
              "probe statuses", [x["point_status"] for x in item["probe_classification"]],
              flush=True)
    report = {
        "status": "two_corrected_named_island_OSM_coastline_and_original_COG_scope_audit",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_probes": str(candidates_file),
        "original_selected_COG_count": 137,
        "islands": results,
        "unknown_OSM_land_not_water": True,
        "OSM_coastlines_not_legal_colombia_jurisdiction": True,
        "quitasueno_excluded": True,
        "no_COGs_approved_or_added": True,
        "no_heights_fabricated": True,
        "national_publication_allowed": False,
        "osm_license": "© OpenStreetMap contributors; ODbL 1.0; https://www.openstreetmap.org/copyright",
    }
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=Path("output/colombia_dem_manifest_extended.csv"))
    p.add_argument("--candidate-probes", type=Path, default=Path(
        "data/island-probe-candidate-corrections-2026-11-14.json"))
    p.add_argument("--output", type=Path, default=Path(
        "output/updated-island-probes/updated-island-probe-validation.json"))
    a = p.parse_args()
    run(a.manifest, a.candidate_probes, a.output)


if __name__ == "__main__":
    main()
