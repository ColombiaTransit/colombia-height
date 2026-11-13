#!/usr/bin/env python3
"""Quality-gate research: native COG source seams and coast/island validity.

No source height is overwritten, no water-level fill, and no MBTiles release.
Seam discontinuities are compared to local intra-source gradients, not
arbitrarily declared defects based on their absolute metre value.
"""
import argparse
import json
from contextlib import ExitStack
from datetime import datetime,timezone
from pathlib import Path

import mercantile
import numpy as np
from shapely.geometry import box
from shapely.ops import unary_union

from coastal_terrain_pilot import REGIONS, reference_mask, load_land_reference, classify_validity
from two_cog_seam_pilot import open_sources, warp_sources, source_files
from four_cog_seam_pilot import JUNCTION

ZOOM=11
# Centered geographic tests include full pixels around shores and islands.
SITE_CENTERS={
    "cartagena":(-75.515,10.415),
    "buenaventura":(-77.03,3.88),
    "san_andres":(-81.70,12.57),
    "providencia":(-81.37,13.35),
    "malpelo":(-81.606,4.005),
    "tumaco":(-78.76,1.81),
}
BORDER_TILE=mercantile.tile(*JUNCTION,ZOOM)

def gradients(heights,provenance):
    """Measure both axis directions, splitting cross-source / same-source."""
    h=np.asarray(heights,dtype=np.float32)
    p=np.asarray(provenance,dtype=np.uint8)
    if h.shape!=p.shape:
        raise ValueError("Shape mismatch")
    measured={}
    for key,dh,pa,pb in [
        ("horizontal",np.abs(h[:,1:]-h[:,:-1]),p[:,1:],p[:,:-1]),
        ("vertical",np.abs(h[1:,:]-h[:-1,:]),p[1:,:],p[:-1,:]),
    ]:
        valid=(pa>0)&(pb>0)&np.isfinite(dh)
        cross=valid&(pa!=pb)
        interior=valid&(pa==pb)
        cross_values=dh[cross]
        within_values=dh[interior]
        measured[key]={
            "cross_source_pairs":int(cross.sum()),
            "same_source_pairs":int(interior.sum()),
            "cross_source_max_m":float(cross_values.max()) if cross_values.size else None,
            "cross_source_p95_m":float(np.percentile(cross_values,95)) if cross_values.size else None,
            "same_source_p95_m":float(np.percentile(within_values,95)) if within_values.size else None,
            "same_source_p99_m":float(np.percentile(within_values,99)) if within_values.size else None,
            "high_gradient_cross_pairs_over_100m":int(np.count_nonzero(cross_values>100)),
        }
    return measured

def audit_native_junction(output):
    # A z10 tile contains all four COGs; z11 scan each child near 6N/-74W.
    z=10
    base=mercantile.tile(*JUNCTION,z)
    tiles=[(z+1,x,y) for y in (base.y*2,base.y*2+1)
                        for x in (base.x*2,base.x*2+1)]
    b=mercantile.bounds(base)
    names,paths=source_files((b.west,b.south,b.east,b.north),output/"sources")
    if len(names)!=4:
        raise AssertionError(f"Expected four source COGs near junction, got {len(names)}")
    records=[]
    with ExitStack() as stack:
        src=open_sources(paths,stack)
        for tile in tiles:
            h,p,overlap,delta=warp_sources(src,tile)
            records.append({"tile":list(tile),"sources_present":int(np.unique(p[p>0]).size),
                            "uncovered_pixels":int(np.count_nonzero(p==0)),
                            "overlap_pixels":overlap,
                            "gradients":gradients(h,p)})
    # Also inspect z10 original tile: lower resolution may mask small source transitions.
    with ExitStack() as stack:
        src=open_sources(paths,stack)
        heights,prov,overlap,delta=warp_sources(src,(z,base.x,base.y))
        combined=gradients(heights,prov)
    mx=max(g["cross_source_max_m"] or 0 for g in combined.values())
    return {
        "source_cogs":names,"base_tile":[z,base.x,base.y],
        "observed_max_cross_source_gradient_m":round(mx,3),
        "native_elevation_gradient_diagnostics":combined,
        "detailed_child_tiles":records,
        "interpretation":"Pixel-center height changes can reflect natural topography and/or source discontinuities; 100m flag is investigative only.",
        "seam_origin_unresolved":True,
    }

def audit_coasts(output,land):
    cases=[]
    for name,(lon,lat) in SITE_CENTERS.items():
        center=mercantile.tile(lon,lat,ZOOM)
        tiles=[(ZOOM,center.x+dx,center.y+dy)
               for dy in (-1,0,1) for dx in (-1,0,1)]
        west=min(mercantile.bounds(x,y,ZOOM).west for _,x,y in tiles)
        south=min(mercantile.bounds(x,y,ZOOM).south for _,x,y in tiles)
        east=max(mercantile.bounds(x,y,ZOOM).east for _,x,y in tiles)
        north=max(mercantile.bounds(x,y,ZOOM).north for _,x,y in tiles)
        names,paths=source_files((west,south,east,north),output/"sources")
        geometry=unary_union([geom for geom in land if geom.intersects(box(west,south,east,north))])
        counts={"total_pixels":0,"valid_reference_land":0,
                "missing_reference_land":0,"valid_outside_reference_land":0,
                "missing_outside_reference_land":0}
        actual_heights=[]
        tiles_complete=0
        tiles_with_missing=0
        with ExitStack() as stack:
            src=open_sources(paths,stack)
            for tile in tiles:
                h,p,overlap,delta=warp_sources(src,tile)
                bounds=mercantile.xy_bounds(tile[1],tile[2],tile[0])
                reference_land=reference_mask(bounds,geometry)
                valid=(p>0)&np.isfinite(h)&(h!=-9999)
                for key,v in classify_validity(valid,reference_land).items():
                    counts[key]+=v
                if valid.all():
                    tiles_complete+=1
                else:
                    tiles_with_missing+=1
                if valid.any():
                    actual_heights.append((float(h[valid].min()),float(h[valid].max())))
        cases.append({
            "site":name,"center_lon_lat":[lon,lat],"zoom":ZOOM,
            "sample_tiles":len(tiles),"complete_tiles":tiles_complete,
            "tiles_with_missing_pixels":tiles_with_missing,
            "source_cogs":names,
            "counts":counts,
            "dem_valid_height_min_m":min(v[0] for v in actual_heights) if actual_heights else None,
            "dem_valid_height_max_m":max(v[1] for v in actual_heights) if actual_heights else None,
            "outside_reference_land_is_not_equivalent_to_ocean":True,
        })
    return cases

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,default=Path("output/quality-gates"))
    args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    junction=audit_native_junction(args.output)
    land=load_land_reference()
    coast=audit_coasts(args.output,land)
    report={
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "status":"diagnostics_only_not_national_publication",
        "junction":junction,"coastal_island_sites":coast,
        "national_publication_allowed":False,
        "publication_blockers":[
            "Source seam outliers require comparison to native same-source baseline, slope and original DEM margins",
            "Missing coast/island DEM pixels cannot be replaced with fabricated elevations",
            "Reference-land polygons are not official island or territory boundaries",
            "Nationwide completeness and tile-partition coverage not validated",
        ],
    }
    (args.output/"dem-quality-gates-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"junction_max_cross_gradient_m":junction["observed_max_cross_source_gradient_m"],
        "junction_diagnostics":junction["native_elevation_gradient_diagnostics"],
        "coastal_island_sites":[{k:v for k,v in row.items() if k in ("site","complete_tiles","tiles_with_missing_pixels","counts")} for row in coast],
        "national_publication_allowed":False},indent=2),flush=True)

if __name__=="__main__":
    main()
