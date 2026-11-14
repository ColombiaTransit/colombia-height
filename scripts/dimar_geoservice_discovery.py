#!/usr/bin/env python3
"""Discover DIMAR-operated coastline/island GIS layers without authorizing a land mask.

Read-only discovery. Coastal polylines are not land polygons; offshore/EEZ
polygons are not land. No public COG promotion, no downloads of full datasets,
no DEM encoding and no release.
"""
import argparse
import json
import re
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import requests

DIMAR_ROOT = "https://ide.dimar.mil.co/serveridem/rest/services"
PORTAL = "https://www.dimar.mil.co/ide"
STUDY_COG_REGISTRY = Path("data/official-igac-source-review-2026-11-13.json")
SITE_PROBES = {
    "tumaco": (-78.76, 1.81),
    "malpelo": (-81.606, 4.005),
    "san_andres": (-81.70, 12.57),
    "providencia": (-81.37, 13.35),
}
# Metadata-only search is intentional: not proof of coastline or land.
INCLUDE = (
    "linea costa", "linea de costa", "isla", "insular", "litoral",
    "costa", "playa", "bajamar", "marea", "terreno emergido",
    "costa pacifico", "geomorfologia",
)
MARINE = (
    "zona economica exclusiva", "mar territorial", "aguas marinas",
    "area marina", "areas marinas", "jurisdiccion maritima",
    "zona maritima", "delimitacion maritima",
    "carta nautica", "batimetria",
)


def normalize(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[\W_]+", " ", text.lower()).strip()


def signals(title, description="", geometry=None):
    """Classify *candidate evidence type*, not land or territorial status."""
    name = normalize(title)
    desc = normalize(description)
    matched = [term for term in INCLUDE if term in name]
    if not matched and "costa" in desc and any(k in name for k in ("linea", "geomorf", "isla", "litoral")):
        matched.append("coastline metadata")
    marine = [term for term in MARINE if term in name]
    geometry = geometry or "unverified"
    if geometry == "esriGeometryPolyline":
        purpose = "coastline_line_evidence_only_not_a_land_polygon"
    elif geometry == "esriGeometryPolygon":
        purpose = "polygon_semantics_unverified_not_a_land_mask"
    elif geometry == "esriGeometryPoint":
        purpose = "island_or_coast_point_only_not_a_land_mask"
    else:
        purpose = "unknown_geometry_no_mask"
    if marine:
        purpose = "marine_or_bathymetry_layer_forbid_land_mask"
    return {
        "matched_coastal_keywords": matched,
        "marine_or_bathymetry_keywords": marine,
        "geometry_type": geometry,
        "land_mask_status": "NOT_VALIDATED",
        "classification": purpose,
        "coastline_relevant": bool(matched),
    }


def source_cell(name):
    match = re.fullmatch(
        r"Copernicus_DSM_COG_10_([NS])(\d{2})_00_([EW])(\d{3})_00_DEM", name)
    if not match:
        raise ValueError(f"Invalid national candidate COG {name}")
    ns, lat, ew, lon = match.groups()
    lat = int(lat) * (1 if ns == "N" else -1)
    lon = int(lon) * (1 if ew == "E" else -1)
    return [lon, lat, lon + 1, lat + 1]


def boxes_overlap(a, b):
    """Strict area overlap; a point touching an extent is not polygon evidence."""
    if a is None or len(a) != 4 or b is None or len(b) != 4:
        return False
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def extent_hint(layer, candidate_cells):
    """ArcGIS fullExtent is a bounding box hint ONLY, not positive land contact."""
    extent = layer.get("extent") or layer.get("fullExtent") or {}
    sr = extent.get("spatialReference") or {}
    epsg = sr.get("latestWkid", sr.get("wkid"))
    if epsg not in (4326, "4326"):
        return {"comparable": False, "reason": "extent_not_epsg4326"}
    bb = [extent.get(k) for k in ("xmin", "ymin", "xmax", "ymax")]
    if any(not isinstance(x, (float, int)) for x in bb):
        return {"comparable": False, "reason": "invalid_extent"}
    matched = [n for n, cell in candidate_cells.items() if boxes_overlap(bb, cell)]
    return {
        "comparable": True, "epsg": 4326, "extent_bbox": bb,
        "candidate_cog_bbox_hints": sorted(matched),
        "bbox_hints_are_not_polygon_or_land_intersections": True,
    }


def api_json(session, url, params=None, timeout=18):
    params = {**(params or {}), "f": "pjson"}
    resp = session.get(url, params=params, timeout=(8, timeout))
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict) or "error" in data:
        raise ValueError(f"ArcGIS service JSON error at {url}: {str(data)[:240]}")
    return data


def list_official_services(session, root=DIMAR_ROOT, max_folders=35, max_services=200):
    errors = []
    folders = []
    services = []
    try:
        obj = api_json(session, root)
    except (requests.RequestException, ValueError) as e:
        return [], [], [{"url": root, "error": str(e)[:400]}]
    folders = sorted(set(obj.get("folders") or []))[:max_folders]
    services += obj.get("services") or []
    for folder in folders:
        path = root + "/" + quote(str(folder), safe="")
        try:
            item = api_json(session, path)
            services.extend(item.get("services") or [])
        except (requests.RequestException, ValueError) as e:
            errors.append({"url": path, "error": str(e)[:300]})
    uniq = {(s.get("name"), s.get("type")): s for s in services
            if s.get("name") and s.get("type") in ("MapServer", "FeatureServer")}
    sorted_services = sorted(uniq.values(), key=lambda x: (
        not signals(x["name"])["coastline_relevant"],
        normalize(x["name"]), x["type"]))
    if len(sorted_services) > max_services:
        errors.append({"reason": "service_list_truncated", "found": len(sorted_services),
                       "inspected": max_services})
    return sorted_services[:max_services], folders, errors


def service_url(root, service):
    return root + "/" + quote(service["name"], safe="/") + "/" + service["type"]


def scan_services(session, services, root, candidate_cells, max_layers=110):
    discovered = []
    errors = []
    inspected = 0
    for svc in services:
        url = service_url(root, svc)
        try:
            meta = api_json(session, url)
        except (requests.RequestException, ValueError) as e:
            errors.append({"service": url, "error": str(e)[:300]})
            continue
        group = (meta.get("layers") or [])
        for layer in group:
            title = layer.get("name") or ""
            service_rank = signals(svc["name"])
            layer_rank = signals(title)
            if not (layer_rank["coastline_relevant"] or service_rank["coastline_relevant"]):
                continue
            if inspected >= max_layers:
                errors.append({"reason": "layer_metadata_truncated", "limit": max_layers})
                return discovered, errors
            inspected += 1
            lid = layer.get("id")
            if not isinstance(lid, int):
                errors.append({"service": url, "error": "layer_without_integer_id"})
                continue
            layer_url = url + "/" + str(lid)
            try:
                detail = api_json(session, layer_url)
            except (requests.RequestException, ValueError) as e:
                errors.append({"layer": layer_url, "error": str(e)[:300]})
                continue
            desc = detail.get("description", "")
            ranked = signals(title, desc, detail.get("geometryType"))
            discovered.append({
                "service": svc["name"], "service_type": svc["type"],
                "name": title, "layer_id": lid, "layer_metadata_url": layer_url,
                "geometry_type": ranked["geometry_type"],
                "classification": ranked["classification"],
                "land_mask_status": ranked["land_mask_status"],
                "coastline_relevant": ranked["coastline_relevant"] or service_rank["coastline_relevant"],
                "metadata_matched_terms": ranked["matched_coastal_keywords"],
                "service_matched_terms": service_rank["matched_coastal_keywords"],
                "description_excerpt": str(desc)[:550],
                "copyright_text": str(detail.get("copyrightText") or meta.get("copyrightText") or "")[:400],
                "supported_query_formats": detail.get("supportedQueryFormats", ""),
                "capabilities": detail.get("capabilities", ""),
                "extent_candidate_cell_hints_only": extent_hint(detail, candidate_cells),
                "no_geometry_downloaded": True,
            })
    return discovered, errors


def load_study_candidates(path):
    j = json.loads(Path(path).read_text())
    entries = j["cog_candidates"]["identifiers"]
    if len(entries) != 52 or len(set(entries)) != 52:
        raise AssertionError("Expected frozen 52 candidate sources from official IGAC study")
    if j.get("selected_source_cogs_still") != 137:
        raise AssertionError("Selected original COG inventory changed")
    return {n: source_cell(n) for n in entries}


def run(output, root=DIMAR_ROOT, candidate_registry=STUDY_COG_REGISTRY,
        max_services=200, max_layers=110):
    candidates = load_study_candidates(candidate_registry)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "ColombiaTransit-DIMAR-geoservices-research/1.0 (read-only)",
        "Accept": "application/json",
    })
    services, folders, list_errors = list_official_services(
        session, root=root, max_services=max_services)
    layers, service_errors = scan_services(
        session, services, root, candidates, max_layers=max_layers)
    type_counts = dict(Counter(x["classification"] for x in layers))
    summary = {
        "status": ("official_DIMAR_ArcGIS_catalog_inspected_no_land_mask_approved"
                   if services else "official_DIMAR_service_catalog_unavailable"),
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "official_portal": PORTAL,
        "source_root": root,
        "direct_official_service_catalog_reachable": bool(services),
        "folders_inspected": folders,
        "service_descriptors_examined": len(services),
        "candidate_coastal_layers": len(layers),
        "layer_type_counts": type_counts,
        "discovery_errors": (list_errors + service_errors)[:85],
        "cog_source_candidates_referenced": len(candidates),
        "coastline_or_island_metadata_candidates": layers,
        "quitasueno_excluded": True,
        "production_source_count_unchanged": 137,
        "official_land_polygon_certified": False,
        "national_publication_allowed": False,
        "limitations": [
            "ArcGIS service names and bounds are only metadata, not coastline/land pixel validity",
            "Coastline POLYLINE geometries cannot by themselves produce closed land polygons",
            "Marine jurisdiction or tidal-water POLYGON is not an emerged land mask",
            "ArcGIS layer metadata alone does not establish all Colombian islands or small cays",
            "An inaccessible official catalog cannot be treated as absence of DIMAR data",
            "Do not download protected services or request access tokens; record metadata only",
        ],
    }
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k not in
                      ("coastline_or_island_metadata_candidates", "discovery_errors")},
                     ensure_ascii=False, indent=2), flush=True)
    for layer in layers:
        print(layer["classification"], layer["geometry_type"], layer["layer_metadata_url"],
              "COG extent hints", len(layer["extent_candidate_cell_hints_only"].get("candidate_cog_bbox_hints", [])),
              flush=True)
    for error in summary["discovery_errors"][:10]:
        print("CATALOG_WARNING:", json.dumps(error, ensure_ascii=False), flush=True)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path,
                    default=Path("output/dimar-catalog/dimar-catalog-report.json"))
    ap.add_argument("--root", default=DIMAR_ROOT)
    ap.add_argument("--candidate-registry", type=Path, default=STUDY_COG_REGISTRY)
    ap.add_argument("--max-services", type=int, default=200)
    ap.add_argument("--max-layers", type=int, default=110)
    args = ap.parse_args()
    if not args.root.startswith("https://ide.dimar.mil.co/serveridem/rest/services"):
        ap.error("Discovery root must be on the official DIMAR ArcGIS Server")
    if not (1 <= args.max_services <= 400 and 1 <= args.max_layers <= 300):
        ap.error("Study caps must be within 1..400 services, 1..300 layers")
    run(args.output, root=args.root, candidate_registry=args.candidate_registry,
        max_services=args.max_services, max_layers=args.max_layers)


if __name__ == "__main__":
    main()
