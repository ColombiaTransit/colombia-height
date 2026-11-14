#!/usr/bin/env python3
"""Append exactly the verified Tumaco native COG to the existing 139 study CSV.

The previous staging CSV and the 137-source production inventory are never
rewritten. Any height seams respect all existing source precedence. This is
NOT a national DEM production manifest nor a Terrain-RGB release.
"""
import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from coastal_audit import index_sources
from inventory import inspect_size
from national_tile_plan import parse_manifest
from extend_inventory import FIELDS

TUMACO="Copernicus_DSM_COG_10_N01_00_W080_00_DEM"
ISLANDS={
    "Copernicus_DSM_COG_10_N03_00_W082_00_DEM",
    "Copernicus_DSM_COG_10_N03_00_W079_00_DEM",
}
STAGING_RUN_139=43604399337
COVERAGE_RUN_139=43605294875
IGAC_NATIVE_RUN=43497684367
NATIVE_SEAM_RUN=43608660364


def review_decision(data):
    if (data.get("decision")!="approve_Tumaco_N01_W080_as_third_Copernicus_source_in_separate_140_source_staging_only"
            or data.get("original_verified_production_source_count")!=137
            or data.get("prior_island_staged_source_count")!=139
            or data.get("new_staged_source_count")!=140
            or data.get("baseline_139_staging_run")!=STAGING_RUN_139
            or data.get("baseline_139_national_coverage_run")!=COVERAGE_RUN_139
            or data.get("original_139_manifest_mutation_forbidden") is not True
            or data.get("original_137_manifest_mutation_forbidden") is not True
            or data.get("national_Terrain_RGB_publication_allowed") is not False
            or data.get("no_synthetic_water_or_bathymetry") is not True
            or data.get("quitasueno_excluded") is not True):
        raise AssertionError("Tumaco third-source staging safety decision invalid")
    x=data.get("candidate",{})
    if (x.get("name")!=TUMACO
            or x.get("source_cell")!={"latitude":1,"longitude":-80}
            or x.get("native_original_COG_z13_test_run")!=IGAC_NATIVE_RUN
            or x.get("native_30m_79W_border_qa_run")!=NATIVE_SEAM_RUN
            or x.get("native_original_COG_24tile_valid_height_samples_recovered")!=460333
            or x.get("native_original_COG_recovered_samples_inside_IGAC_departments")!=6602
            or x.get("staged139_residual_IGAC_positive_z13_source_gap_pixels")!=5865
            or x.get("native_30m_79W_border_disproportionate_flag_count")!=0
            or x.get("georeferenced_original_COG_border_gap_m")!=0
            or x.get("native_30m_79W_border_valid_samples",0)<300
            or x.get("approval")!="staging_140_research_only"):
        raise AssertionError("Tumaco geographic/native source evidence not verified")


def validate_staged_baseline(baseline):
    if (len(baseline)!=139 or len({s["name"] for s in baseline})!=139
            or any(s["status"]!="ok" for s in baseline)):
        raise AssertionError("Expected exactly 139 original+two-island audited COGs")
    if {s["name"] for s in baseline[137:]}!=ISLANDS:
        raise AssertionError("139-stage island tail differs from reviewed two COGs")
    if any(s["name"] in ISLANDS for s in baseline[:137]):
        raise AssertionError("Original 137-source study inventory changed")
    if TUMACO in {s["name"] for s in baseline}:
        raise AssertionError("Tumaco already selected; prevent duplicate staging")
    return [dict(x) for x in baseline]


def append_reviewed_COG(baseline,candidate):
    old=validate_staged_baseline(baseline)
    if (candidate.get("name")!=TUMACO
            or int(candidate.get("latitude"))!=1
            or int(candidate.get("longitude"))!=-80
            or candidate.get("status")!="ok"
            or int(candidate.get("size_bytes") or 0)<=0
            or not candidate.get("url","").endswith(TUMACO+".tif")):
        raise AssertionError("Tumaco original public COG metadata invalid")
    result=old+[dict(candidate)]
    if len(result)!=140 or [x["name"] for x in result[:139]]!=[x["name"] for x in baseline]:
        raise AssertionError("Original 139 source priority changed")
    return result


def run(previous,decision,output):
    previous=Path(previous)
    old_bytes=previous.read_bytes()
    rows=parse_manifest(previous)
    decision_path=Path(decision)
    review=json.loads(decision_path.read_text())
    review_decision(review)
    index={x["name"]:x for x in index_sources().values()}
    if TUMACO not in index:
        raise AssertionError("Public Copernicus source catalog missing Tumaco")
    source=inspect_size(index[TUMACO])
    source["selection_reasons"]="only_140_source_Tumaco_staging_native_IGAC_and_79W_seam_verified"
    staged=append_reviewed_COG(rows,source)
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    csv_path=output/"colombia_dem_manifest_tumaco_staging_140.csv"
    with csv_path.open("w",newline="",encoding="utf-8") as out:
        writer=csv.DictWriter(out,fieldnames=FIELDS,extrasaction="ignore")
        writer.writeheader()
        writer.writerows(staged)
    if previous.read_bytes()!=old_bytes:
        raise AssertionError("Immutable previous 139-source input changed")
    if len(parse_manifest(csv_path))!=140:
        raise AssertionError("Staging CSV invalid to actual GLO-30 source reader")
    report={
        "status":"only_Tumaco_staged_to_140_native_COGs_NOT_production",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "baseline_139_artifact_workflow_run":STAGING_RUN_139,
        "baseline_139_allzoom_coverage_run_not_rerun":COVERAGE_RUN_139,
        "baseline_139_sha256_unchanged":hashlib.sha256(old_bytes).hexdigest(),
        "new_140_staging_sha256":hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "production_original_COG_count_unchanged":137,
        "old_staging_COG_count":139,
        "new_staging_COG_count":140,
        "old_139_source_names_in_original_order":True,
        "new_staging_COG":{"name":source["name"],"status":source["status"],
                           "size_bytes":int(source["size_bytes"]),"url":source["url"]},
        "native_IGAC_pixel_evidence_run":IGAC_NATIVE_RUN,
        "native_79W_COG_boundary_evidence_run":NATIVE_SEAM_RUN,
        "old_137_native_COGs_unchanged":True,
        "old_139_staging_COGs_unchanged":True,
        "remaining_omitted_original_candidates":49,
        "no_artificial_DEM_ocean_or_bathymetry":True,
        "quitasueno_excluded":True,
        "national_Terrain_RGB_publication_allowed":False,
    }
    (output/"140-source-tumaco-stage-report.json").write_text(
        json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(report,indent=2,ensure_ascii=False),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--previous",type=Path,default=Path("output/stage139/colombia_dem_manifest_island_staging_139.csv"))
    p.add_argument("--decision",type=Path,default=Path("data/staged-tumaco-third-source-2026-11-14.json"))
    p.add_argument("--output",type=Path,default=Path("output/stage140"))
    a=p.parse_args()
    run(a.previous,a.decision,a.output)


if __name__=="__main__":
    main()
