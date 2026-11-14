#!/usr/bin/env python3
"""Build an ephemeral *139-source* island COG staging manifest, not a release.

A reviewed source allowlist chooses precisely Malpelo N03 W082 and Gorgona
N03 W079 after strict evidence checks. Original 137-source CSV is NEVER edited.
All COGs are original Copernicus; no ocean DEM or synthetic sample is added.
"""
import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from coastal_audit import index_sources
from extend_inventory import FIELDS
from inventory import inspect_size
from national_tile_plan import parse_manifest

ALLOWLIST={
    "Copernicus_DSM_COG_10_N03_00_W082_00_DEM":(3,-82,"malpelo"),
    "Copernicus_DSM_COG_10_N03_00_W079_00_DEM":(3,-79,"gorgona"),
}
REQUIRED_EVIDENCE={
    "island_exact_osm_pixel_recovery":43594868906,
    "minor_islands_and_multi_zoom_cog_seams":43596436204,
    "original_native_30m_source_border":43596823989,
}


def approved_sources(decision):
    if (decision.get("decision") != "allow_exactly_two_verified_COGs_in_separate_reproducible_staging_manifest_only"
            or decision.get("original_source_count")!=137
            or decision.get("staging_source_count")!=139
            or decision.get("selected_production_source_count_unchanged")!=137
            or decision.get("staged_added_source_count")!=2):
        raise AssertionError("Missing reviewed two-source staging approval")
    if decision.get("evidence_runs") is None or any(
        decision["evidence_runs"].get(k)!=v for k,v in REQUIRED_EVIDENCE.items()
    ):
        raise AssertionError("Native DEM and exact island QA run provenance changed")
    controls=decision.get("staging_constraints") or {}
    if (controls.get("national_terrain_rgb_publication_allowed") is not False
            or controls.get("quitasueno_explicitly_excluded") is not True
            or controls.get("only_sources_in_explicit_allowlist") is not True
            or controls.get("no_synthetic_ocean_or_height_fill") is not True):
        raise AssertionError("Land/ocean source staging release gates not enforced")
    items=decision.get("sources") or []
    if {s["name"] for s in items}!=set(ALLOWLIST) or len(items)!=2:
        raise AssertionError("Staging sources changed from the explicit 2-Cog allowlist")
    for item in items:
        lat,lon,site=ALLOWLIST[item["name"]]
        if (item.get("site")!=site or item.get("source_cell")!={"latitude":lat,"longitude":lon}
                or item.get("decision_status")!="staging_only_approved_not_production"
                or not item.get("geographic_identity_primary_official","").startswith("https://www.parquesnacionales.gov.co/")
                or item.get("native_30m_disproportionate_gt40m_flags")!=0
                or item.get("source_transition_missing_adjacent_pairs")!=0
                or item.get("previously_valid_dem_height_max_change_m")!=0
                or item.get("original_exact_OSM_island_gap_pixels")!=item.get("real_native_COG_pixel_gaps_restored")):
            raise AssertionError(f"Geographic/native-Copernicus staging gate not satisfied: {item['name']}")
        if item.get("native_30m_boundary_samples",0)<300:
            raise AssertionError("Native border not adequately sampled")
    return sorted(items,key=lambda x:x["name"])


def construct_staging_rows(original, additions):
    if len(original)!=137 or len({r["name"] for r in original})!=137:
        raise AssertionError("Expected unique original 137 COGs")
    if any(x["status"]!="ok" for x in original):
        raise AssertionError("Original native selected sources not all verified")
    if len(additions)!=2 or {r["name"] for r in additions}!=set(ALLOWLIST):
        raise AssertionError("Exactly two reviewed source additions required")
    names={r["name"] for r in original}
    if any(r["name"] in names for r in additions):
        raise AssertionError("An additional source is already present in frozen manifest")
    for s in additions:
        lat,lon,site=ALLOWLIST[s["name"]]
        if (int(s["latitude"])!=lat or int(s["longitude"])!=lon
                or s.get("status")!="ok" or int(s.get("size_bytes") or 0)<=0
                or not s.get("url","").endswith(s["name"]+".tif")):
            raise AssertionError("Source COG identity, provenance or content size not verified")
    # Preserve precedence for every original 137-source COG, including native
    # bilinear overlap at adjacent degree-cell borders. A sorted 139-source
    # list could place a new COG ahead of an original source and overwrite
    # preexisting valid elevation pixels. Only append staged extras.
    staged=[dict(x) for x in original]+sorted(
        [dict(x) for x in additions], key=lambda s:s["name"])
    if len(staged)!=139 or len({s["name"] for s in staged})!=139:
        raise AssertionError("Unexpected staging inventory size")
    return staged


def build(manifest,review,output):
    path=Path(manifest)
    original_bytes=path.read_bytes()
    selected=parse_manifest(path)
    decision=json.loads(Path(review).read_text())
    approved=approved_sources(decision)
    index={s["name"]:s for s in index_sources().values()}
    proposed=[]
    for item in approved:
        name=item["name"]
        if name not in index:
            raise RuntimeError(f"Public Copernicus catalog missing reviewed source {name}")
        source=inspect_size(index[name])
        source["selection_reasons"]="strict_island_staging_only:"+item["site"]
        proposed.append(source)
    staged=construct_staging_rows(selected,proposed)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    staged_path=output/"colombia_dem_manifest_island_staging_139.csv"
    with staged_path.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=FIELDS,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(staged)
    if path.read_bytes()!=original_bytes:
        raise AssertionError("Original 137-source input manifest was mutated")
    if len(parse_manifest(staged_path))!=139:
        raise AssertionError("New staging CSV is not loadable by native DEM source parser")
    evidence={
        "status":"two_island_sources_staged_ONLY_not_national_release",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "source_review":str(review),
        "evidence_runs":decision["evidence_runs"],
        "baseline_manifest":str(manifest),
        "baseline_manifest_sha256_unchanged":hashlib.sha256(original_bytes).hexdigest(),
        "staging_manifest_sha256":hashlib.sha256(staged_path.read_bytes()).hexdigest(),
        "baseline_source_count":137,
        "staging_source_count":139,
        "approved_temporary_extra_sources":[
            {"name":s["name"],"size_bytes":int(s["size_bytes"]),
             "status":s["status"],"url":s["url"]}
            for s in proposed],
        "additional_verified_native_COG_download_bytes":sum(int(s["size_bytes"]) for s in proposed),
        "quitasueno_excluded":True,
        "all_other_50_omitted_sources_still_outside_staging":True,
        "artificial_heights_added":0,
        "permanent_137_source_manifest_changed":False,
        "national_publication_allowed":False,
        "note":"Staged COGs add genuine native heights for exactly reviewed islands; no jurisdiction-pixel coastline or nationwide release is authorized.",
    }
    (output/"island-staging-139-report.json").write_text(
        json.dumps(evidence,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(evidence,indent=2,ensure_ascii=False),flush=True)
    return evidence


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    p.add_argument("--review",type=Path,default=Path("data/staged-island-source-selection-2026-11-14.json"))
    p.add_argument("--output",type=Path,default=Path("output/island-stage"))
    a=p.parse_args()
    build(a.manifest,a.review,a.output)


if __name__=="__main__":
    main()
