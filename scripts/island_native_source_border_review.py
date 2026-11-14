#!/usr/bin/env python3
"""Inspect Gorgona's five coarse z11 source-border gradients in native COGs.

The 40m threshold is advisory only: a steep true terrain pixel is not a
failed COG seam. Sample six ORIGINAL ~30m source rows on each side of each
3/4 N boundary and independently inspect the flagged z11 pixel pairs.
No fabricated heights, source approval or national Terrain-RGB release.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import mercantile
import numpy as np
import rasterio

from coastal_audit import index_sources
from island_native_recovery_qa import xyz_centers
from island_source_readiness import render_with_owner
from medellin_terrain import download
from national_tile_plan import parse_manifest
from native_source_seam_audit import sample_strips, seam_metrics

BORDERS={
    "gorgona":{
        "latitude":3.0, "lon_range":(-78.225,-78.12),
        "south":"Copernicus_DSM_COG_10_N02_00_W079_00_DEM",
        "north":"Copernicus_DSM_COG_10_N03_00_W079_00_DEM",
        "extra":"Copernicus_DSM_COG_10_N03_00_W079_00_DEM",
        "z11_flagged_tile":(11,579,1006),
        "expected_coarse_gradient_flags":5,
    },
    "malpelo":{
        "latitude":4.0, "lon_range":(-81.665,-81.55),
        "south":"Copernicus_DSM_COG_10_N03_00_W082_00_DEM",
        "north":"Copernicus_DSM_COG_10_N04_00_W082_00_DEM",
        "extra":"Copernicus_DSM_COG_10_N03_00_W082_00_DEM",
        "z11_flagged_tile":None,
        "expected_coarse_gradient_flags":0,
    },
}


def marked_source_transitions(heights,valid,owners,names,candidate,threshold=40.):
    """Detailed native-warp z11 pixel pairs; no sea/NODATA gradient claims."""
    if any(np.asarray(a).shape!=(256,256) for a in (heights,valid,owners)):
        raise ValueError("Unaligned 256x256 source grids")
    indices={i+1 for i,n in enumerate(names) if n==candidate}
    if len(indices)!=1:
        raise AssertionError("Coarse review should include exactly one candidate")
    cid=next(iter(indices))
    result=[]
    for dy,dx in ((0,1),(1,0)):
        for r in range(256-dy):
            for c in range(256-dx):
                rr,cc=r+dy,c+dx
                if not(valid[r,c] and valid[rr,cc]):
                    continue
                a=int(owners[r,c]);b=int(owners[rr,cc])
                if not ((a==cid and b!=0 and b!=cid) or
                        (b==cid and a!=0 and a!=cid)):
                    continue
                delta=abs(float(heights[r,c])-float(heights[rr,cc]))
                if delta<=threshold:
                    continue
                inner=[]
                for r0,c0,step in ((r,c,-1),(rr,cc,1)):
                    ir,ic=r0+step*dy,c0+step*dx
                    if (0<=ir<256 and 0<=ic<256 and valid[ir,ic]
                            and owners[ir,ic]==owners[r0,c0]):
                        inner.append(abs(float(heights[ir,ic])-float(heights[r0,c0])))
                    else:
                        inner.append(None)
                both=[v for v in inner if v is not None]
                max_local=max(both) if both else None
                result.append({
                    "orientation":"east_west_neighbor" if dx else "north_south_neighbor",
                    "pixel_a_row_col":[r,c],"pixel_b_row_col":[rr,cc],
                    "source_a":names[a-1],"source_b":names[b-1],
                    "height_a_m":float(heights[r,c]),
                    "height_b_m":float(heights[rr,cc]),
                    "cross_source_adjacent_delta_m":round(delta,4),
                    "same_source_inward_deltas_m":inner,
                    "max_available_inward_gradient_m":max_local,
                    "delta_over_max_inward_gradient":round(delta/max(max_local,1.),3) if max_local is not None else None,
                    "height_gradient_not_alone_evidence_of_bad_source":True,
                })
    return result


def render_tile(augmented,tile,cache,opened):
    h,v,p,n=render_with_owner(augmented,opened,cache,tile)
    return h,v,p,n


def run(manifest,output):
    sources=parse_manifest(manifest)
    if len(sources)!=137:
        raise AssertionError("Original 137 selected COG count changed")
    names={r["name"] for r in sources}
    catalog={r["name"]:r for r in index_sources().values()}
    cache=Path(output).parent/"cog-cache"
    cache.mkdir(parents=True,exist_ok=True)
    results={}
    for region,spec in BORDERS.items():
        south,north=spec["south"],spec["north"]
        extra=spec["extra"]
        if extra in names:
            raise AssertionError("An extra source has already been selected")
        if not {south,north}.issubset(set(catalog)):
            raise AssertionError(f"Native source catalog unavailable for {region}")
        old=next((n for n in (south,north) if n!=extra),None)
        if old not in names:
            raise AssertionError(f"Expected adjacent selected source {old} absent from manifest")
        if (spec["latitude"]!=int(catalog[north]["latitude"])
                or spec["latitude"]-1!=int(catalog[south]["latitude"])):
            raise AssertionError("Source DEM latitude border does not match catalog")
        downloaded={}
        for name in (south,north):
            src=catalog[name]
            path=cache/(name+".tif")
            download(src["url"],path)
            downloaded[name]=path
        with rasterio.open(downloaded[south]) as s,rasterio.open(downloaded[north]) as n:
            lon=np.linspace(*spec["lon_range"],350)
            southern,northern,res=sample_strips(s,n,lon,lat=spec["latitude"],rows=6)
            native=seam_metrics(southern,northern)
            native.update({
                "source_south":south,"source_north":north,
                "native_pixel_step_latitude_degrees":res,
                "south_upper_georeference_edge":s.bounds.top,
                "north_lower_georeference_edge":n.bounds.bottom,
                "native_strips_sampled_350_longitudes_each_side":True,
            })
        coarse=None
        if spec["z11_flagged_tile"] is not None:
            augmented=sources+[{
                "name":extra, "latitude":str(catalog[extra]["latitude"]),
                "longitude":str(catalog[extra]["longitude"]),
                "url":catalog[extra]["url"],"status":"investigation_only_not_selected"}]
            opened={}
            try:
                tile=spec["z11_flagged_tile"]
                h,v,prov,owners=render_tile(augmented,tile,cache,opened)
                flags=marked_source_transitions(h,v,prov,owners,extra)
                if len(flags)!=spec["expected_coarse_gradient_flags"]:
                    raise AssertionError(
                        f"Frozen z11 flag count changed: {len(flags)} != {spec['expected_coarse_gradient_flags']}")
                lo,la=xyz_centers(tile)
                for flag in flags:
                    a=flag["pixel_a_row_col"]
                    b=flag["pixel_b_row_col"]
                    flag["midpoint_lonlat"]=[
                        round(float((lo[a[0],a[1]]+lo[b[0],b[1]])/2),8),
                        round(float((la[a[0],a[1]]+la[b[0],b[1]])/2),8),
                    ]
                coarse={"zxy":list(tile),"flags_over_40m":flags,
                        "count_flags_over_40m":len(flags)}
            finally:
                for obj in opened.values():
                    obj.close()
        results[region]={
            "native_source_boundary":native,
            "original_z11_coarse_flag_analysis":coarse,
            "native_30m_source_test_is_not_colombian_legal_land_boundary":True,
            "approval_gate":"native_gradients_are_descriptive_require_geography_and_release_scope_decision",
        }
    report={
        "status":"gorgona_coarse_source_gradient_vs_native_30m_border_QA",
        "created_utc":datetime.now(timezone.utc).isoformat(),
        "original_selected_source_count":137,
        "islands":results,
        "copernicus_source_manifest_unchanged":True,
        "quitasueno_excluded":True,
        "no_synthetic_ocean_or_height_fill":True,
        "national_publication_allowed":False,
    }
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(report,indent=2,ensure_ascii=False),flush=True)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,default=Path("output/colombia_dem_manifest_extended.csv"))
    p.add_argument("--output",type=Path,default=Path("output/native-island-source-border/island-native-source-border.json"))
    a=p.parse_args()
    run(a.manifest,a.output)


if __name__=="__main__":
    main()
