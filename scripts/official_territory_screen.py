#!/usr/bin/env python3
"""Evidence-only screening of 52 additional GLO-30 COG cells against IGAC land.

Source: IGAC Limites/limites MapServer layer 2 (department polygons).
Administrative polygons are NOT a high-resolution shoreline or proof of
maritime/island sovereignty. Never promote sources or fill DEM nodata here.
"""
import argparse
import gzip
import json
import math
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import requests
from shapely.geometry import Point, box, shape
from shapely.strtree import STRtree

IGAC_SERVICE = "https://mapas2.igac.gov.co/server/rest/services/limites/limites/MapServer/2"
SOURCE_RE = re.compile(r"^Copernicus_DSM_COG_10_([NS])(\d{2})_00_([EW])(\d{3})_00_DEM$")
BASELINE_RUN = 43490555676
BASELINE_CANDIDATES = 52
BASELINE_Z13_INCOMPLETE = 1917
BASELINE_Z13_NATURAL_EARTH_LAND_GAP = 1004


def cell_geometry(name):
    match = SOURCE_RE.fullmatch(name)
    if not match:
        raise ValueError(f"Unexpected public COG identifier {name}")
    ns, latstr, ew, lonstr = match.groups()
    lat = int(latstr) * (1 if ns == "N" else -1)
    lon = int(lonstr) * (1 if ew == "E" else -1)
    return box(lon, lat, lon + 1, lat + 1)


def xyz_geometry(z, x, y):
    if not (0 <= z <= 13 and 0 <= x < 2**z and 0 <= y < 2**z):
        raise ValueError("Invalid XYZ tile")
    n = 1 << z
    west = x / n * 360. - 180.
    east = (x + 1) / n * 360. - 180.
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2*y/n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2*(y+1)/n))))
    return box(west, south, east, north)


def load_incomplete_rows(root):
    root = Path(root)
    files = sorted(root.glob("land-shard-*.ndjson.gz"))
    summaries = sorted(root.glob("land-summary-*.json"))
    if len(files) != 32 or len(summaries) != 32:
        raise AssertionError(f"Require all 32 prior land study artifacts, got {len(files)} records and {len(summaries)} summaries")
    seen, rows = set(), []
    for shard in range(32):
        p = root / f"land-shard-{shard:02d}.ndjson.gz"
        summary = json.loads((root / f"land-summary-{shard:02d}.json").read_text())
        if not summary["complete"] or summary["shard"] != shard or summary["mode"] != "full" or summary["source_cog_count"] != 137:
            raise AssertionError(f"Invalid national baseline shard {shard}")
        with gzip.open(p, "rt", encoding="utf-8") as stream:
            for line in stream:
                item = json.loads(line)
                key = (item["z"], item["x"], item["y"])
                if key in seen:
                    raise AssertionError(f"Duplicate XYZ {key}")
                seen.add(key)
                if item["dem_coverage"] == "full_dem_coverage":
                    raise AssertionError(f"Full DEM record in incomplete register {key}")
                if sum(item[k] for k in ("missing_both_land_references",
                        "missing_geoboundaries_only", "missing_natural_earth_only",
                        "missing_outside_both_references")) != item["missing_dem_pixels"]:
                    raise AssertionError(f"Pixel count mismatch {key}")
                rows.append(item)
    if len(rows) != 3778:
        raise AssertionError(f"National incomplete baseline changed: {len(rows)} != 3778")
    focus = [r for r in rows if r["z"] == 13]
    ne_gaps = [r for r in focus if r["missing_natural_earth_only"]]
    names = sorted({n for r in rows for n in r["unselected_public_cogs_at_missing_pixels"]})
    if (len(focus), len(ne_gaps), len(names)) != (BASELINE_Z13_INCOMPLETE, BASELINE_Z13_NATURAL_EARTH_LAND_GAP, BASELINE_CANDIDATES):
        raise AssertionError(f"Unexpected z13 or catalog candidate baseline {(len(focus),len(ne_gaps),len(names))}")
    return rows, focus, ne_gaps, names


IGAC_ALTERNATES = [
    (IGAC_SERVICE, "official_IGAC_primary"),
    ("https://mapas2.igac.gov.co/server/rest/services/carto/departamentos/MapServer/0",
     "official_IGAC_alternate"),
    ("https://services3.arcgis.com/87J8ieBcJTwm5kkV/ArcGIS/rest/services/IGAC_Colombia_Departamentos/FeatureServer/31",
     "public_IGAC_labelled_hosted_copy_UNVERIFIED"),
]


def request_json(url, params, timeout=90):
    resp = requests.get(url, params=params, timeout=(20, timeout),
                        headers={"User-Agent": "ColombiaTransit-terrain-source-scope-research/1.0"})
    resp.raise_for_status()
    result = resp.json()
    if "error" in result:
        raise RuntimeError(f"ArcGIS service error: {str(result['error'])[:250]}")
    return result, resp.url


def get_service_features(url):
    """Try one GET for all features, then ID-based subrequests on failure."""
    query = url + "/query"
    fields = "OBJECTID,DeCodigo,DeNombre"
    bulk = {
        "where": "1=1", "outFields": fields, "outSR": "4326",
        "returnGeometry": "true", "f": "geojson",
    }
    try:
        result, fetched_url = request_json(query, bulk, 90)
        if result.get("type") == "FeatureCollection" and 25 <= len(result.get("features", [])) <= 50 and not result.get("exceededTransferLimit"):
            return result["features"], fetched_url
        raise RuntimeError("Bulk query returned incomplete polygon set")
    except (requests.RequestException, ValueError, RuntimeError) as bulk_error:
        print(f"IGAC bulk unavailable {url}: {str(bulk_error)[:220]}; trying object-ID queries", flush=True)

    ids, ids_url = request_json(query, {"where": "1=1", "returnIdsOnly": "true", "f": "json"}, 35)
    object_ids = ids.get("objectIds")
    if not isinstance(object_ids, list) or not 25 <= len(object_ids) <= 50:
        raise RuntimeError(f"Unexpected object ID count from {url}: {len(object_ids or [])}")
    out = []
    for obj in sorted(object_ids):
        record, record_url = request_json(query, {
            "objectIds": str(obj), "outFields": fields, "outSR": "4326",
            "returnGeometry": "true", "f": "geojson",
        }, 75)
        if record.get("type") != "FeatureCollection" or len(record.get("features", [])) != 1:
            raise RuntimeError(f"Invalid/empty feature response for ID {obj} in {url}")
        out.extend(record["features"])
    return out, ids_url


def get_igac_features():
    """Official primary IGAC preferred, unverified mirror is explicit fallback.

    No fallback changes the release gate: these are administrative polygons,
    NOT certified shoreline or small-island territory boundaries.
    """
    failures = []
    for service_url, source_class in IGAC_ALTERNATES:
        try:
            features, metadata_url = get_service_features(service_url)
            if not 25 <= len(features) <= 50:
                raise RuntimeError("Missing department polygons")
            shapes, names = [], []
            for feature in features:
                geometry = feature.get("geometry")
                if not geometry:
                    raise RuntimeError("Department without geometry")
                g = shape(geometry)
                if g.is_empty or g.geom_type not in ("Polygon", "MultiPolygon") or not g.is_valid:
                    raise RuntimeError(f"Invalid polygon: {feature.get('properties')}")
                if not (-90 < g.bounds[0] < -60 and -90 < g.bounds[2] < -60
                        and -7 < g.bounds[1] < 20 and -7 < g.bounds[3] < 20):
                    raise RuntimeError(f"Suspicious projection or coordinates: {g.bounds}")
                shapes.append(g)
                props = feature.get("properties") or {}
                names.append(str(props.get("DeNombre") or "unknown"))
            if not any(g.covers(Point(-74.072, 4.711)) for g in shapes):
                raise RuntimeError("Country EPSG:4326 sanity check failed at Bogota")
            print(f"Accepted {len(shapes)} departmental polygons from {source_class}; "
                  "geometry does NOT authorize coastline decisions", flush=True)
            return shapes, names, metadata_url, source_class, failures
        except (requests.RequestException, ValueError, RuntimeError) as error:
            failures.append({"service_url": service_url, "error": str(error)[:400]})
            print(f"IGAC source unavailable: {service_url}: {str(error)[:240]}", flush=True)
    raise RuntimeError(
        "No usable official administrative polygon or fallback mirror; fail closed: "
        + json.dumps(failures))


def positive_polygon_overlap(a, b):
    """Touching along a shared border is not interior land evidence."""
    return a.intersects(b) and a.intersection(b).area > 0.


def screen(z13, gaps, all_names, polygons, dept_names):
    tree = STRtree(polygons)
    enriched = {}
    for name in all_names:
        cell = cell_geometry(name)
        hits = [int(i) for i in tree.query(cell)]
        contact = sorted({dept_names[i] for i in hits if positive_polygon_overlap(polygons[i], cell)})
        enriched[name] = {
            "name": name,
            "cog_degree_cell": [round(v, 6) for v in cell.bounds],
            "igac_department_polygon_contact": bool(contact),
            "igac_departments": contact,
            "z13_incomplete_tile_hints": 0,
            "z13_natural_earth_land_gap_tile_hints": 0,
            "z13_tiles_with_igac_polygon_contact": 0,
            "z13_tiles_with_igac_and_candidate_cell_contact": 0,
            "cooccurring_natural_earth_gap_pixels_NOT_verified_cog_recovery": 0,
            "possible_island_or_coast_review": True,
            "approval_status": "NOT_APPROVED_geometric_candidate_only",
        }
    near_counts = Counter()
    for row in z13:
        t = xyz_geometry(row["z"], row["x"], row["y"])
        ids = [int(i) for i in tree.query(t)]
        tile_igac = [polygons[i] for i in ids if positive_polygon_overlap(polygons[i], t)]
        intersects_igac = bool(tile_igac)
        ne = row["missing_natural_earth_only"]
        if ne:
            near_counts["suspect_z13_tiles"] += 1
            if intersects_igac:
                near_counts["suspect_z13_tiles_with_igac_polygon_contact"] += 1
            else:
                near_counts["suspect_z13_tiles_without_igac_polygon_contact"] += 1
        for name in row["unselected_public_cogs_at_missing_pixels"]:
            summary = enriched[name]
            summary["z13_incomplete_tile_hints"] += 1
            summary["z13_natural_earth_land_gap_tile_hints"] += int(bool(ne))
            summary["cooccurring_natural_earth_gap_pixels_NOT_verified_cog_recovery"] += ne
            if intersects_igac:
                summary["z13_tiles_with_igac_polygon_contact"] += 1
                partial = t.intersection(cell_geometry(name))
                if not partial.is_empty and any(positive_polygon_overlap(g, partial) for g in tile_igac):
                    summary["z13_tiles_with_igac_and_candidate_cell_contact"] += 1
    for s in enriched.values():
        if s["z13_tiles_with_igac_and_candidate_cell_contact"]:
            s["screening_tier"] = "A_IGAC_land_and_candidate_cell_overlap_needs_native_DEM_QA"
        elif s["igac_department_polygon_contact"]:
            s["screening_tier"] = "B_IGAC_contact_but_no_confirmed_z13_gap_contact"
        else:
            s["screening_tier"] = "C_no_IGAC_department_polygon_overlap_islands_or_neighbors_need_review"
    return enriched, dict(near_counts)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=Path("output/national-land"))
    p.add_argument("--output", type=Path, default=Path("output/official-territory"))
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    all_rows, z13, gaps, names = load_incomplete_rows(args.input)
    polygons, dept_names, metadata_url, source_class, failed_sources = get_igac_features()
    rankings, counts = screen(z13, gaps, names, polygons, dept_names)
    sorted_rank = sorted(rankings.values(), key=lambda a: (
        a["screening_tier"], -a["z13_tiles_with_igac_and_candidate_cell_contact"],
        -a["z13_natural_earth_land_gap_tile_hints"], a["name"]))
    tiers = dict(Counter(r["screening_tier"] for r in sorted_rank))
    report = {
        "status": "official_IGAC_department_polygon_geometric_screen_only",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "national_source_run": BASELINE_RUN,
        "selected_source_cog_count": 137,
        "source_candidates_considered": len(names),
        "national_incomplete_tile_count": len(all_rows),
        "z13_incomplete_tiles": len(z13),
        "z13_ne_only_land_gap_tiles": len(gaps),
        "igac_source": metadata_url,
        "igac_layer": IGAC_SERVICE,
        "polygon_service_class": source_class,
        "polygon_service_is_direct_official_IGAC": source_class.startswith("official_IGAC"),
        "failed_preferred_sources": failed_sources,
        "igac_polygon_count": len(polygons),
        "igac_department_names": sorted(set(dept_names)),
        "screening_tiers": tiers,
        "z13_reference_crosscheck": counts,
        "candidate_source_rankings": sorted_rank,
        "national_publication_allowed": False,
        "source_manifest_changes": 0,
        "interpretation": (
            "IGAC departments are official administrative polygons, not a certified "
            "sub-pixel coastline/sea mask; candidates ranked by spatial contact, "
            "NOT by proven missing Colombian pixels or actual native DEM recovery."),
        "pending": [
            "DIMAR/IGAC detailed island and shoreline geometry including minor cays",
            "Native DEM pixel recovery check for tier A candidate COGs",
            "Exact match of missing native DEM pixels to official land mask",
            "Exclude Quitasueño according to maintainer-selected scope",
            "Never fill ocean or DEM NoData with synthetic 0m or trenches",
        ],
    }
    (args.output / "igac-source-scope-screen.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "candidate_source_rankings"},indent=2),flush=True)
    for item in sorted_rank:
        print(item["screening_tier"], item["name"],
              "z13_suspect_tiles", item["z13_natural_earth_land_gap_tile_hints"],
              "igac_cell_tile_hits", item["z13_tiles_with_igac_and_candidate_cell_contact"],
              flush=True)


if __name__ == "__main__":
    main()
