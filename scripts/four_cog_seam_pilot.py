#!/usr/bin/env python3
"""Four-batch native-COG Terrain-RGB test across 2x2 degree source junctions.

An inland ~1.75 x 1.75 degree region straddles lon -74 and lat 6,
covering the four adjacent Copernicus GLO-30 1-degree cells. Four
independently rendered z10 parent-tile quadrants are merged, and both
horizontal and vertical batch seams are checked against native COGs.

No clipped intermediate DEM, no inferred water heights, no publication.
"""
import argparse
import json
import sqlite3
from contextlib import ExitStack
from pathlib import Path

import mercantile
import numpy as np

from strict_terrain import encode_tile
from merge_regions import merge_mbtiles
from two_cog_seam_pilot import (
    open_sources, warp_sources, decode_png, source_boundary_stats, source_files,
)

BASE_Z=10
X_RANGE=range(299,304)
Y_RANGE=range(492,497)
BATCHES={
    "northwest":(range(299,302),range(492,495)),
    "northeast":(range(302,304),range(492,495)),
    "southwest":(range(299,302),range(495,497)),
    "southeast":(range(302,304),range(495,497)),
}
ACCEPTANCE_M=0.16
JUNCTION=(-74.0,6.0)

def base_bbox(xs,ys):
    w=mercantile.bounds(min(xs),max(ys),BASE_Z)
    e=mercantile.bounds(max(xs),min(ys),BASE_Z)
    return (w.west,w.south,e.east,e.north)

def tiles_for(xs,ys,z):
    factor=1<<(z-BASE_Z)
    return [(z,x,y) for row in ys for y in range(row*factor,(row+1)*factor)
            for col in xs for x in range(col*factor,(col+1)*factor)]

def owner(z,x,y):
    if z<BASE_Z:
        raise ValueError("Not a child of the z10 pilot grid")
    x0=x>>(z-BASE_Z)
    y0=y>>(z-BASE_Z)
    for name,(xs,ys) in BATCHES.items():
        if x0 in xs and y0 in ys:
            return name
    raise ValueError(f"Outside regional grid: {z}/{x}/{y}")

def adjacent_pairs(z):
    """Every internal edge exactly once, including cross-batch edges."""
    factor=1<<(z-BASE_Z)
    xs=range(min(X_RANGE)*factor,(max(X_RANGE)+1)*factor)
    ys=range(min(Y_RANGE)*factor,(max(Y_RANGE)+1)*factor)
    for y in ys:
        for x in xs:
            if x+1 in xs:
                if owner(z,x,y)!=owner(z,x+1,y):
                    yield ("west_east",(z,x,y),(z,x+1,y))
            if y+1 in ys:
                if owner(z,x,y)!=owner(z,x,y+1):
                    yield ("north_south",(z,x,y),(z,x,y+1))

def source_stats(dem,provenance):
    """Two kinds of source-border pixels, with physical gradients separately."""
    horiz=source_boundary_stats(dem,provenance)
    cross=(provenance[1:,:]!=provenance[:-1,:]) & (provenance[1:,:]!=0) & (provenance[:-1,:]!=0)
    gradients=np.abs(dem[1:,:]-dem[:-1,:])[cross]
    return {
        "east_west_source_pixel_pairs":horiz["cross_source_adjacent_pixel_pairs"],
        "north_south_source_pixel_pairs":int(cross.sum()),
        "max_north_south_source_gradient_m":round(float(gradients.max()),3) if gradients.size else None,
    }

def render_batch(root,name,maxzoom):
    xs,ys=BATCHES[name]
    bounds=base_bbox(xs,ys)
    filenames,paths=source_files(bounds,root/"source-cache")
    folder=root/name
    folder.mkdir(parents=True,exist_ok=True)
    output=folder/(name+".mbtiles")
    output.unlink(missing_ok=True)
    counts={}
    stats={"east_west_source_pixel_pairs":0,"north_south_source_pixel_pairs":0,
           "overlap_pixels":0}
    with ExitStack() as stack:
        sources=open_sources(paths,stack)
        db=sqlite3.connect(output)
        try:
            db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT)")
            db.execute("CREATE TABLE tiles(zoom_level INTEGER,tile_column INTEGER,tile_row INTEGER,tile_data BLOB,PRIMARY KEY(zoom_level,tile_column,tile_row))")
            db.executemany("INSERT INTO metadata VALUES (?,?)",[
                ("name","Colombia four-source crossing "+name),
                ("format","png"),("type","baselayer"),("version","1.0"),
                ("minzoom",str(BASE_Z)),("maxzoom",str(maxzoom)),
                ("attribution","Contains modified Copernicus DEM data"),
                ("bounds",",".join(map(str,bounds))),
            ])
            for z in range(BASE_Z,maxzoom+1):
                count=0
                for tile in tiles_for(xs,ys,z):
                    dem,provenance,overlaps,_=warp_sources(sources,tile)
                    if not np.all(provenance):
                        raise RuntimeError(f"Missing DEM coverage in {name} {tile}: {int((provenance==0).sum())} pixels")
                    png,_=encode_tile(dem,strict=True)
                    z0,x,y=tile
                    db.execute("INSERT INTO tiles VALUES (?,?,?,?)",
                               (z0,x,(1<<z0)-1-y,png))
                    samples=source_stats(dem,provenance)
                    for key in ("east_west_source_pixel_pairs","north_south_source_pixel_pairs"):
                        stats[key]+=samples[key]
                    stats["overlap_pixels"]+=overlaps
                    count+=1
                counts[str(z)]=count
                db.commit()
            if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise AssertionError("Invalid region MBTiles")
        except BaseException:
            db.close()
            output.unlink(missing_ok=True)
            raise
        db.close()
    return {"name":name,"bounds":bounds,"mbtiles":str(output),
            "source_cogs":filenames,"download_bytes":sum(p.stat().st_size for p in paths),
            "tiles_by_zoom":counts,"raster_source_stats":stats,
            "mbtiles_bytes":output.stat().st_size}

def get_tile(db,tile):
    z,x,y=tile
    r=db.execute("SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                 (z,x,(1<<z)-1-y)).fetchone()
    if r is None:
        raise AssertionError(f"Missing {tile}")
    return decode_png(r[0])

def verify(root,batches,maxzoom):
    union=base_bbox(X_RANGE,Y_RANGE)
    names,paths=source_files(union,root/"source-cache")
    # Exactly four source degree cells in an inland test region. A different
    # source count means the actual test footprint unexpectedly changed.
    if len(names)!=4:
        raise AssertionError(f"Expected four native source COGs, found {len(names)}: {names}")
    data={b["name"]:b for b in batches}
    metrics={}
    max_reference_error=0
    totals={"west_east":0,"north_south":0}
    with ExitStack() as stack:
        sources=open_sources(paths,stack)
        conns={name:stack.enter_context(sqlite3.connect(
            f"file:{Path(batch['mbtiles']).resolve()}?mode=ro",uri=True))
            for name,batch in data.items()}
        for z in range(BASE_Z,maxzoom+1):
            items=[]
            for orientation,a,b in adjacent_pairs(z):
                lhs=get_tile(conns[owner(*a)],a)
                rhs=get_tile(conns[owner(*b)],b)
                ldem,lprov,_,_=warp_sources(sources,a)
                rdem,rprov,_,_=warp_sources(sources,b)
                if not np.all(lprov) or not np.all(rprov):
                    raise AssertionError("Reference source has uncovered pixels")
                err=max(float(np.max(np.abs(lhs-ldem))),float(np.max(np.abs(rhs-rdem))))
                if err>ACCEPTANCE_M:
                    raise AssertionError(f"Reference mismatch {orientation} {a}->{b}: {err:.3f} metres")
                max_reference_error=max(max_reference_error,err)
                if orientation=="west_east":
                    gradient=np.abs(lhs[:,-1]-rhs[:,0])
                else:
                    gradient=np.abs(lhs[-1,:]-rhs[0,:])
                items.append({"orientation":orientation,
                              "first_tile":list(a),"second_tile":list(b),
                              "reference_error_m":round(err,4),
                              "max_adjacent_pixel_gradient_m":round(float(gradient.max()),3)})
                totals[orientation]+=1
            metrics[str(z)]=items
        # Junction coordinate must fall inside region, and have nearby DEM
        # provenance from all four native COGs in its parent z10 tile.
        junction_tile=mercantile.tile(*JUNCTION,BASE_Z)
        if owner(junction_tile.z,junction_tile.x,junction_tile.y) not in data:
            raise AssertionError("Four-source junction outside test region")
        test_dem,provenance,_,_=warp_sources(sources,(
            junction_tile.z,junction_tile.x,junction_tile.y
        ))
        n_sources=len(set(int(x) for x in np.unique(provenance) if x))
        if n_sources!=4:
            raise AssertionError(f"Expected all four sources in junction tile, found {n_sources}")
        junction_stats=source_stats(test_dem,provenance)
        if not junction_stats["east_west_source_pixel_pairs"] or not junction_stats["north_south_source_pixel_pairs"]:
            raise AssertionError("Junction did not exercise both north-south and east-west source transitions")
    return {"all_four_source_cogs":names,"reference_error_limit_m":ACCEPTANCE_M,
            "maximum_reference_error_m":round(max_reference_error,4),
            "verified_cross_batch_pairs":totals,
            "junction_lon_lat":list(JUNCTION),
            "junction_map_tile":[junction_tile.z,junction_tile.x,junction_tile.y],
            "junction_native_cog_count":n_sources,
            "junction_native_source_transitions":junction_stats,
            "seams_per_zoom":metrics,
            "validated":True}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path,default=Path("output/four-cog"))
    p.add_argument("--maxzoom",type=int,choices=(11,12),default=11)
    a=p.parse_args()
    root=a.output
    root.mkdir(parents=True,exist_ok=True)
    batches=[render_batch(root,name,a.maxzoom) for name in BATCHES]
    joined=root/"four-cog-merged.mbtiles"
    joined.unlink(missing_ok=True)
    merged=merge_mbtiles([b["mbtiles"] for b in batches],joined)
    expected=sum(sum(b["tiles_by_zoom"].values()) for b in batches)
    if merged["tiles"]!=expected:
        raise AssertionError(f"Merged tile count {merged['tiles']} != {expected}")
    qa=verify(root,batches,a.maxzoom)
    with sqlite3.connect(joined) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise AssertionError("Merged SQLite corrupt")
    report={
        "status":"four_source_multi_batch_validated",
        "created_but_not_published":True,
        "bbox":base_bbox(X_RANGE,Y_RANGE),
        "zoom_min":BASE_Z,"zoom_max":a.maxzoom,
        "batches":batches,"merged":merged,"quality_assurance":qa,
        "limitations":[
            "One selected 2x2 degree Copernicus junction, not all Colombia source borders",
            "Native source gaps fail closed rather than creating synthetic ocean elevation",
            "The independent re-opened reference uses the same warping implementation",
            "Production nationwide coastline and island policies remain separate tasks",
        ]}
    (root/"four-cog-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("quality_assurance","batches")},indent=2),flush=True)
    print(json.dumps({k:v for k,v in qa.items() if k!="seams_per_zoom"},indent=2),flush=True)

if __name__=="__main__":
    main()
