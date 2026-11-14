#!/usr/bin/env python3
"""Territory-aware TRIAGE of existing OSM/native-DEM evidence, not a land mask.

Use existing audited z13 OSM pixel counts, directly official IGAC overlap
counts, and independent neighbor-country ADM0 geometry *for context*.
Island probe coordinates are approximate study clues, not island outlines.
Never reattribute OSM land pixels to Colombia by nearest country or cell.
No sources are added or heights generated. All undecided pixels stay unknown.
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import requests
from shapely.geometry import Point, box, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

from official_territory_screen import cell_geometry, xyz_geometry

NEIGHBORS = ("VEN", "BRA", "PER", "ECU", "PAN", "NIC", "CRI", "HND")
GEOBOUNDARIES = "https://www.geoboundaries.org/api/current/gbOpen/{code}/ADM0/"
EXPECTED_OSM_RUN = 43573144549
KNOWN_NATIVE_RUN = 43497684367
OSM_PIXEL_FIELDS = (
    "native_missing_dem_pixels", "missing_inside_osm_land",
    "missing_outside_osm_land_UNKNOWN_not_confirmed_ocean",
    "missing_osm_land_and_igac_department",
)
MAX_ISLAND_PROXIMITY_DEG = .06  # study vicinity only (~6 km north/south)


def load_existing_report(path, official_path, probes_path):
    report = json.loads(Path(path).read_text())
    official = json.loads(Path(official_path).read_text())
    probes = json.loads(Path(probes_path).read_text())["locations"]
    if (report.get("mode") != "national" or report.get("tiles_checked") != 1917
            or report.get("selected_source_cogs") != 137
            or report.get("source_candidate_total") != 52
            or report.get("previously_identified_1004_tile_subset", {}).get("tiles") != 1004
            or report.get("candidate_sources_promoted") != 0
            or report.get("national_publication_allowed") is not False
            or report.get("osm_outside_land_is_NOT_confirmed_ocean") is not True):
        raise AssertionError("Frozen OSM z13 audit not validated")
    if report.get("official_IGAC_context_mask_status") != "evaluated":
        raise AssertionError("Require actual official IGAC pixel mask, not unavailable/null")
    if (official.get("selected_source_cogs_still") != 137
            or official.get("evidence_runs", {}).get("native_z13_igac_and_natural_earth_recovery") != KNOWN_NATIVE_RUN
            or not official.get("native_z13_pixel_recovery", {}).get("unchanged_original_valid_elevations")
            or official.get("national_publication_allowed") is not False):
        raise AssertionError("Missing frozen native-recovery evidence")
    rows = report["per_tile"]
    names = [r["name"] for r in report["all_52_omitted_public_cog_candidates"]]
    if len(rows) != 1917 or len(set((r["z"],r["x"],r["y"]) for r in rows)) != 1917:
        raise AssertionError("Missing or duplicated z13 rows")
    if len(names) != 52 or len(set(names)) != 52:
        raise AssertionError("Incomplete 52 source list")
    if len(set(p["id"] for p in probes)) != len(probes) or not probes:
        raise AssertionError("Invalid named-island study probes")
    if "quitasueno" in json.dumps(probes).lower():
        raise AssertionError("Deliberately excluded Quitasueño in island input")
    return report, official, probes


def get_border_geometries(session, iso_codes=NEIGHBORS):
    """Collect advisory foreign ADM0 geometries; NEVER a Colombian pixel mask."""
    outlines = {}
    meta = {}
    errors = {}
    for code in iso_codes:
        try:
            endpoint = GEOBOUNDARIES.format(code=code)
            res = session.get(endpoint, timeout=(10,35))
            res.raise_for_status()
            item = res.json()
            if not isinstance(item, dict) or not item.get("gjDownloadURL"):
                raise ValueError("No geoBoundaries ADM0 GeoJSON URL")
            geom_res = session.get(item["gjDownloadURL"],timeout=(15,80))
            geom_res.raise_for_status()
            gjson = geom_res.json()
            features = gjson.get("features") or []
            if not features:
                raise ValueError("Empty foreign ADM0 geometry")
            geoms = []
            for f in features:
                g = shape(f["geometry"])
                if not g.is_valid:
                    g = make_valid(g)
                if not g.is_empty:
                    geoms.append(g)
            geom = unary_union(geoms)
            if geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
                raise ValueError("Non-polygon country reference")
            outlines[code] = geom
            meta[code] = {
                "metadata_url": endpoint,
                "geojson_url": item["gjDownloadURL"],
                "boundary_id": item.get("boundaryID"),
                "source_license": item.get("boundaryLicense"),
                "reference_type": "non_authoritative_foreign_adm0_CONTEXT_only",
            }
            print("FOREIGN_REFERENCE",code,"loaded",flush=True)
        except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
            errors[code] = str(exc)[:350]
            print("FOREIGN_REFERENCE_UNAVAILABLE",code,str(exc)[:180],flush=True)
    return outlines,meta,errors


def approximate_island_neighbors(cell, probes, threshold=MAX_ISLAND_PROXIMITY_DEG):
    """A point near a 1° cell is NOT evidence of territorial land in that cell."""
    hits=[]
    for probe in probes:
        pid = str(probe["id"]).lower()
        if "quitasueno" in pid:
            continue
        point=Point(float(probe["lon"]),float(probe["lat"]))
        if cell.distance(point) <= threshold:
            hits.append(probe["id"])
    return sorted(hits)


def foreign_cell_context(cell, neighbors):
    """Return an *approximate degree-square* fraction of foreign ADM0 overlap.

    Fractions are in planar degree units, not square km or OSM missing pixels.
    'Foreign-dominant' never certifies a Colombian absence or excludes a COG.
    """
    fractions={}
    for country,polygon in neighbors.items():
        if cell.intersects(polygon):
            frac=float(cell.intersection(polygon).area/cell.area)
            if frac>0:
                fractions[country]=round(min(frac,1.),6)
    return dict(sorted(fractions.items(),key=lambda item:(-item[1],item[0])))


def rank_source(row, official, probes, foreign):
    name=row["name"]
    cell=cell_geometry(name)
    context=foreign_cell_context(cell,foreign)
    nearby=approximate_island_neighbors(cell,probes)
    osm=int(row["osm_land_missing_pixel_cell_hits"])
    igac=row["osm_land_and_igac_missing_pixel_cell_hits"]
    if igac is None:
        raise AssertionError("IGAC missing values must not be coerced to zero")
    igac=int(igac)
    native=None
    if name==official["native_z13_pixel_recovery"]["tumaco"]["source"]:
        native={"site":"tumaco","source_run":KNOWN_NATIVE_RUN,
                "native_z13_recovered_pixels":int(official["native_z13_pixel_recovery"]["tumaco"]["real_native_dem_pixels_recovered"]),
                "native_recovered_inside_IGAC_pixels":int(official["native_z13_pixel_recovery"]["tumaco"]["recovered_inside_igac_departments"])}
    elif name==official["native_z13_pixel_recovery"]["malpelo"]["source"]:
        native={"site":"malpelo","source_run":KNOWN_NATIVE_RUN,
                "native_z13_recovered_pixels":int(official["native_z13_pixel_recovery"]["malpelo"]["real_native_dem_pixels_recovered"]),
                "native_recovered_inside_IGAC_pixels":int(official["native_z13_pixel_recovery"]["malpelo"]["recovered_inside_igac_departments"])}
    if igac>0 and native:
        tier="1_OSM_IGAC_native_recovery_measured_mainland"
    elif native and "malpelo" in nearby:
        tier="2_known_Malpelo_study_native_recovery_measured_island_review"
    elif igac>0:
        tier="3_OSM_IGAC_pixel_evidence_needs_native_recovery"
    elif nearby:
        tier="4_named_island_study_vicinity_NOT_territory_certification"
    elif osm>0 and any(v>=.8 for v in context.values()):
        tier="5_foreign_ADM0_dominant_cell_REFERENCE_only"
    elif osm>0 and context:
        tier="6_cross_border_foreign_ADM0_overlap_REVIEW"
    elif osm>0:
        tier="7_OSM_land_only_no_national_scope_established"
    else:
        tier="8_no_matching_OSM_land_missing_pixels_no_conclusion"
    return {
        "name":name,"one_degree_source_cell_lonlat":list(cell.bounds),
        "native_missing_pixel_cell_hits":int(row["native_missing_pixel_cell_hits"]),
        "osm_land_missing_pixel_cell_hits":osm,
        "osm_land_and_official_IGAC_missing_pixel_cell_hits":igac,
        "z13_tiles_with_missing_pixel_in_cog_degree_cell":int(row["z13_tiles_with_missing_pixel_in_this_cog_degree_cell"]),
        "foreign_ADM0_degree_cell_overlap_CONTEXT_NOT_pixel_allocation":context,
        "island_probe_ids_within_0p06_degrees_context_only":nearby,
        "prior_native_recovery":native,
        "review_tier":tier,
        "territorial_land_authorized":False,
        "source_approved_for_manifest":False,
        "foreign_reference_contact_is_not_proof_of_foreign_pixel":True,
    }


def classify_tile(tile, probes, foreign):
    """Tile flags are not mutually exclusive national land decisions."""
    geom=xyz_geometry(tile["z"],tile["x"],tile["y"])
    osm=int(tile["missing_inside_osm_land"])
    igac=tile["missing_osm_land_and_igac_department"]
    if igac is None:
        raise AssertionError("Official IGAC pixel evidence unavailable")
    near=approximate_island_neighbors(geom,probes,.035)
    context=foreign_cell_context(geom,foreign)
    if igac>0:
        tier="1_OSM_and_IGAC_missing_DEM_pixel_evidence"
    elif near and osm:
        tier="2_island_probe_nearby_OSM_missing_land_pixels_context_only"
    elif osm and any(v>=.8 for v in context.values()):
        tier="3_foreign_ADM0_dominant_tile_context_only"
    elif osm and context:
        tier="4_foreign_ADM0_intersects_tile_context_only"
    elif osm:
        tier="5_OSM_land_only_territory_unknown"
    else:
        tier="6_no_OSM_missing_land_pixels_other_NoData_unknown"
    return {
        "z":tile["z"],"x":tile["x"],"y":tile["y"],
        "tier":tier,"native_missing_pixels":int(tile["native_missing_dem_pixels"]),
        "missing_inside_osm_land":osm,
        "missing_osm_land_and_igac":int(igac),
        "named_island_probe_near_tile":near,
        "foreign_boundary_overlapping_tile_reference_only":context,
        "candidate_cog_names":sorted(tile["per_candidate_omitted_cog"]),
        "automatic_country_attribution":False,
    }


def run(osm_report, official_review, probes_file, output):
    report,official,probes=load_existing_report(osm_report,official_review,probes_file)
    session=requests.Session()
    session.headers.update({"User-Agent":"ColombiaTransit-OSM-country-source-triage/1.0"})
    foreign,foreign_meta,foreign_errors=get_border_geometries(session)
    sources=[rank_source(x,official,probes,foreign)
             for x in report["all_52_omitted_public_cog_candidates"]]
    tiles=[classify_tile(x,probes,foreign) for x in report["per_tile"]]
    source_tiers=dict(Counter(x["review_tier"] for x in sources))
    tile_tiers=dict(Counter(x["tier"] for x in tiles))
    sources.sort(key=lambda x:(x["review_tier"],-x["osm_land_and_official_IGAC_missing_pixel_cell_hits"],
                               -x["osm_land_missing_pixel_cell_hits"],x["name"]))
    priority=sorted(
        (x for x in tiles if x["missing_inside_osm_land"]),
        key=lambda x:(x["tier"],-x["missing_osm_land_and_igac"],
                      -x["missing_inside_osm_land"],x["x"],x["y"]))
    result={
        "status":"OSM_IGAC_foreign_ADM0_and_offshore_probe_candidate_triage",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "frozen_OSM_evidence_run":EXPECTED_OSM_RUN,
        "native_recovery_evidence_run":KNOWN_NATIVE_RUN,
        "source_cog_candidates":len(sources),
        "z13_incomplete_baseline_tiles":len(tiles),
        "OSM_missing_land_tiles":sum(x["missing_inside_osm_land"]>0 for x in tiles),
        "sources_by_evidence_tier":source_tiers,
        "tiles_by_non_authoritative_reference_tier":tile_tiers,
        "foreign_country_references_loaded":foreign_meta,
        "foreign_country_references_unavailable":foreign_errors,
        "island_proximity_is_not_official_boundary":True,
        "foreign_overlap_is_not_per_pixel_country_allocation":True,
        "official_IGAC_is_administrative_not_coastline_certification":True,
        "countrywide_exact_native_recovery_for_all_52_performed":False,
        "frozen_selected_COG_count":137,
        "new_selected_COGs":0,
        "quitasueno_explicitly_excluded":True,
        "synthetic_ocean_heights_added":0,
        "national_publication_allowed":False,
        "sources":sources,
        "priority_OSM_missing_land_tiles_first_35":priority[:35],
        "review_notes":[
            "Original OSM report includes foreign land in the -84..-66 / -5..17 study rectangle",
            "Only a positive intersect of OSM+IGAC pixels is joint Colombian administrative land evidence",
            "The OSM-referenced country boundary and foreign borders do not establish territorial sovereignty",
            "Named island points are approximate; an island cell touch is NOT proof that its whole cell is Colombian land",
            "Malpelo is a required separately reviewed island even though IGAC departmental polygons omit it",
            "A foreign administrative polygon's degree-cell or tile overlap does not locate the actual missing native DEM pixel",
            "Prior native DEM COG recovery evidence is reused, not inferred from missing pixel count or rerun",
            "No data outside OSM polygon is labelled confirmed sea",
        ],
    }
    if (sum(source_tiers.values())!=52 or sum(tile_tiers.values())!=1917
            or result["new_selected_COGs"]!=0
            or not result["national_publication_allowed"] is False):
        raise AssertionError("Source triage failed strict reconciliation")
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in (
        "sources","priority_OSM_missing_land_tiles_first_35",
        "foreign_country_references_loaded")},indent=2),flush=True)
    for src in sources:
        print("SOURCE_TRIAGE",src["review_tier"],src["name"],"osm_land",
              src["osm_land_missing_pixel_cell_hits"],"igac",
              src["osm_land_and_official_IGAC_missing_pixel_cell_hits"],
              "native",src["prior_native_recovery"]["native_z13_recovered_pixels"]
              if src["prior_native_recovery"] else "NOT_TESTED",
              "foreign",list(src["foreign_ADM0_degree_cell_overlap_CONTEXT_NOT_pixel_allocation"]),
              flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--osm-report",type=Path,default=Path("output/osm-audit/osm-national-native-land-report.json"))
    p.add_argument("--official-review",type=Path,default=Path("data/official-igac-source-review-2026-11-13.json"))
    p.add_argument("--island-probes",type=Path,default=Path("data/colombia-island-probes.json"))
    p.add_argument("--output",type=Path,default=Path("output/osm-territorial-triage/source-scope-triage.json"))
    args=p.parse_args()
    run(args.osm_report,args.official_review,args.island_probes,args.output)


if __name__=="__main__":
    main()
