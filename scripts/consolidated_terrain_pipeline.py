#!/usr/bin/env python3
"""Consolidated OSM-land-only Terrain-RGB pipeline (non-publication).

Thin orchestration ONLY. Reuses:
  national_tile_plan: 140-source candidate XYZ enumeration and unique ownership
  generate_osm_land_only_terrain: OSM geometry, mask, native COG warp and RGB
  merge_regions: fail-closed SQLite MBTiles merger

No fresh national DEM research, no invented heights, no ocean output. Any
mixed coast tile blocks that *chunk* before native COG downloads. The final
merge refuses incomplete/blocked chunks, missing reports or duplicate tiles.
Low zoom (0-8) and renderer-safe mixed coasts remain outside this stage.
"""
import argparse
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from generate_osm_land_only_terrain import (
    load_osm_coastline_land, load_osm_country, prepare_plan,
    require_verified_staging, write_inland_mbtiles,
)
from merge_regions import merge_mbtiles
from national_tile_plan import candidate_tiles, owner, parse_manifest
from render_only_coast_rgb import COAST_MODE, decode_mask_png

MIN_SAFE_ZOOM = 9
MAX_SAFE_ZOOM = 13
MAX_CHUNK_TILES = 1000
MAX_PLAN_TILES = 150000
DEFAULT_SHARDS = 32
DEFAULT_CHUNK_TILES = 250
SOURCE_COUNT = 140


def atomic_json(path, data):
    """Never leave a partially written plan or gate report."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".incomplete")
    tmp.unlink(missing_ok=True)
    try:
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def load_plan(path):
    root = Path(path)
    result = json.loads(root.read_text())
    if (result.get("schema") != "colombia-land-only-terrain-shards-v1"
            or result.get("source_COGs") != SOURCE_COUNT
            or not result.get("national_release_authorized") is False):
        raise ValueError("Not a valid, non-release 140-source Colombia shard plan")
    chunks = result.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("Empty 140-source shard plan")
    if len(set(c["id"] for c in chunks)) != len(chunks):
        raise ValueError("Duplicate plan chunk IDs")
    if sum(c["tiles"] for c in chunks) != result.get("candidate_tiles"):
        raise ValueError("Plan candidate count differs from chunk totals")
    return result


def create_plan(manifest, output_dir, minzoom=MIN_SAFE_ZOOM,
                maxzoom=MAX_SAFE_ZOOM, shards=DEFAULT_SHARDS,
                chunk_tiles=DEFAULT_CHUNK_TILES):
    """Reuse original candidate and shard-owner algorithms; no raster read."""
    if not MIN_SAFE_ZOOM <= minzoom <= maxzoom <= MAX_SAFE_ZOOM:
        raise ValueError("Only z9-z13 is eligible for this inland consolidation")
    if not 1 <= shards <= 128 or not 1 <= chunk_tiles <= MAX_CHUNK_TILES:
        raise ValueError("Unsafe shard count or chunk size")
    sources = parse_manifest(manifest)
    require_verified_staging(sources)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "plan.json").exists() or list(root.glob("chunk-*.ndjson")):
        raise FileExistsError("Plan output already exists; never silently replace tile roster")
    by_shard = defaultdict(list)
    count_by_zoom = Counter()
    for z in range(minzoom, maxzoom + 1):
        coords = candidate_tiles(sources, z)
        count_by_zoom[str(z)] = len(coords)
        for x, y in sorted(coords):
            by_shard[owner(z, x, y, shards)].append((z, x, y))
    total = sum(count_by_zoom.values())
    if not 0 < total <= MAX_PLAN_TILES:
        raise RuntimeError("Source-cell candidate plan exceeds safe 150,000-tile bound")
    chunks = []
    for shard, tiles in sorted(by_shard.items()):
        for offset in range(0, len(tiles), chunk_tiles):
            group = tiles[offset:offset + chunk_tiles]
            chunk_id = f"{shard:03d}-{offset // chunk_tiles:04d}"
            filename = f"chunk-{chunk_id}.ndjson"
            path = root / filename
            with path.open("x", encoding="utf-8") as file:
                for z, x, y in group:
                    file.write(json.dumps({
                        "z": z, "x": x, "y": y,
                        "tms_y": (1 << z) - y - 1,
                    }, separators=(",", ":")) + "\n")
            chunks.append({
                "id": chunk_id,
                "filename": filename,
                "sha256": sha256_file(path),
                "shard": shard,
                "tiles": len(group),
            })
    summary = {
        "schema": "colombia-land-only-terrain-shards-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_COGs": SOURCE_COUNT,
        "source_manifest_sha256": sha256_file(manifest),
        "zoom_range": [minzoom, maxzoom],
        "shards": shards,
        "max_chunk_tiles": chunk_tiles,
        "candidate_tiles": total,
        "candidate_tiles_by_zoom": dict(count_by_zoom),
        "chunks": chunks,
        "reuse": [
            "national_tile_plan.candidate_tiles",
            "national_tile_plan.owner",
            "generate_osm_land_only_terrain",
            "merge_regions.merge_mbtiles",
        ],
        "national_release_authorized": False,
        "unresolved": [
            "opt-in surface-zero coastal rendering requires a real MapLibre/TileServer screenshot acceptance test",
            "z0-z8 native terrain and full-country renderer validation",
        ],
    }
    atomic_json(root / "plan.json", summary)
    print(json.dumps({"status": "plan_only", "tiles": total,
                      "chunks": len(chunks), "zooms": [minzoom, maxzoom]}, indent=2))
    return summary


def load_chunk(plan_dir, chunk_id):
    root = Path(plan_dir)
    plan = load_plan(root / "plan.json")
    chunks = [c for c in plan["chunks"] if c["id"] == chunk_id]
    if len(chunks) != 1:
        raise ValueError("Chunk not found in verified plan")
    info = chunks[0]
    path = root / info["filename"]
    if path.name != info["filename"] or sha256_file(path) != info["sha256"]:
        raise ValueError("Chunk file missing, tampered or out of plan directory")
    if not 0 < info["tiles"] <= MAX_CHUNK_TILES:
        raise ValueError("Unsafe chunk count")
    tiles = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        z, x, y = (row[k] for k in ("z", "x", "y"))
        if not all(isinstance(v, int) and not isinstance(v, bool) for v in (z, x, y)):
            raise ValueError("Invalid tile coordinates")
        if (not MIN_SAFE_ZOOM <= z <= MAX_SAFE_ZOOM
                or not (0 <= x < (1 << z) and 0 <= y < (1 << z))
                or row.get("tms_y") != (1 << z) - y - 1
                or owner(z, x, y, plan["shards"]) != info["shard"]):
            raise ValueError("Chunk has wrong XYZ/TMS or owner")
        tiles.append((z, x, y))
    if len(tiles) != info["tiles"] or len(set(tiles)) != len(tiles):
        raise ValueError("Chunk count or unique tile ownership mismatch")
    return plan, info, tiles


def render_chunk(plan_dir, chunk_id, manifest, land_clip, land_meta,
                 country_json, output_dir, cache, coast_render_surface=False):
    """Produce native OSM chunk; mixed coast needs explicit render-only opt-in."""
    plan, info, tiles = load_chunk(plan_dir, chunk_id)
    if sha256_file(manifest) != plan["source_manifest_sha256"]:
        raise ValueError("Source manifest changed after immutable plan creation")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    mbtiles = output_dir / f"chunk-{chunk_id}.mbtiles"
    report_path = output_dir / f"chunk-{chunk_id}.report.json"
    if report_path.exists() or mbtiles.exists():
        raise FileExistsError("Chunk already processed: do not overwrite successful/blocked evidence")
    sources = parse_manifest(manifest)
    require_verified_staging(sources)
    physical, meta = load_osm_coastline_land(land_clip, land_meta)
    country = load_osm_country(country_json)
    if coast_render_surface:
        statuses, rows = prepare_plan(tiles, physical, country, include_physical=True)
    else:
        statuses, rows = prepare_plan(tiles, physical, country)
    blocked = [{"zxy": list(row["tile"]), "land_pixels": row["land_pixels"]}
               for row in rows
               if row["status"] == "mixed_coastal_OSM_Colombia_land_and_offland"]
    base = {
        "schema": "colombia-osm-land-only-chunk-v1",
        "chunk_id": chunk_id,
        "chunk_sha256": info["sha256"],
        "source_manifest_sha256": plan["source_manifest_sha256"],
        "source_COGs": SOURCE_COUNT,
        "physical_OSM_sha256": meta["reference_wkb_sha256"],
        "OSM_country_relation": 120027,
        "planned_tiles": len(tiles),
        "mask_summary": dict(statuses),
        "blocked_coastal_tiles": blocked if not coast_render_surface else [],
        "coast_render_mode": COAST_MODE if coast_render_surface else "strict_inland",
        "national_release_authorized": False,
    }
    if blocked and not coast_render_surface:
        report = {**base, "status": "BLOCKED_mixed_coast",
                  "full_land_tiles_written": 0,
                  "skipped_all_offland": statuses.get("skip_no_physical_OSM_Colombia_land", 0)}
        atomic_json(report_path, report)
        raise RuntimeError(
            f"Chunk {chunk_id}: {len(blocked)} mixed coast/island tiles. "
            "No native sources fetched and no MBTiles emitted; see blocker report.")
    if statuses.get("mixed_foreign_physical_OSM_land_blocked", 0):
        report = {**base, "status": "BLOCKED_foreign_land_cannot_be_sea",
                  "blocked_coastal_tiles": blocked,
                  "full_land_tiles_written": 0,
                  "skipped_all_offland": statuses.get("skip_no_physical_OSM_Colombia_land", 0)}
        atomic_json(report_path, report)
        raise RuntimeError("Foreign/out-of-country OSM land must not be rendered as zero sea surface")
    required_tile_count = (
        statuses.get("fully_OSM_Colombia_land", 0) +
        (statuses.get("mixed_coastal_OSM_Colombia_land_and_offland", 0)
         if coast_render_surface else 0))
    if required_tile_count == 0:
        report = {**base, "status": "SKIPPED_no_Colombian_OSM_land",
                  "full_land_tiles_written": 0,
                  "skipped_all_offland": len(tiles)}
        atomic_json(report_path, report)
        return report
    # Native Copernicus download and warp is already implemented and tested
    # in the original generator. No replacement code here.
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    if coast_render_surface:
        result = write_inland_mbtiles(
            mbtiles, rows, sources, cache,
            (-84.0, -5.0, -66.0, 17.0),
            (min(t[0] for t in tiles), max(t[0] for t in tiles)),
            coast_render_surface=True)
    else:
        result = write_inland_mbtiles(
            mbtiles, rows, sources, cache,
            (-84.0, -5.0, -66.0, 17.0),
            (min(t[0] for t in tiles), max(t[0] for t in tiles)))
    if (result["full_land_tiles_written"] != statuses.get("fully_OSM_Colombia_land", 0)
            or result.get("mixed_coast_tiles_written", 0) != (
                statuses.get("mixed_coastal_OSM_Colombia_land_and_offland", 0)
                if coast_render_surface else 0)
            or result.get("skipped_all_offland", 0)
            != statuses.get("skip_no_physical_OSM_Colombia_land", 0)):
        mbtiles.unlink(missing_ok=True)
        raise AssertionError("Native writer count differs from OSM chunk mask")
    report = {**base, **result,
              "status": "SUCCESS_render_only_coast" if coast_render_surface else "SUCCESS_inland_only",
              "mbtiles_file": mbtiles.name, "mbtiles_sha256": sha256_file(mbtiles)}
    atomic_json(report_path, report)
    return report


def merge_verified_chunks(plan_dir, result_dir, target):
    """Reuse existing SQLite merger only after *every* OSM shard passes."""
    plan = load_plan(Path(plan_dir) / "plan.json")
    result_dir = Path(result_dir)
    sources = []
    actual = 0
    for chunk in plan["chunks"]:
        report_path = result_dir / f"chunk-{chunk['id']}.report.json"
        if not report_path.exists():
            raise RuntimeError(f"No report for {chunk['id']}: refusing partial-country merge")
        report = json.loads(report_path.read_text())
        if (report.get("schema") != "colombia-osm-land-only-chunk-v1"
                or report.get("chunk_id") != chunk["id"]
                or report.get("chunk_sha256") != chunk["sha256"]
                or report.get("source_manifest_sha256") != plan["source_manifest_sha256"]
                or report.get("national_release_authorized") is not False
                or report.get("blocked_coastal_tiles")):
            raise ValueError(f"Invalid or blocked chunk report: {chunk['id']}")
        written = report.get("full_land_tiles_written", -1)
        mixed = report.get("mixed_coast_tiles_written", 0)
        skipped = report.get("skipped_all_offland", -1)
        if (not isinstance(mixed,int) or mixed<0 or written<0 or skipped<0
                or written+mixed+skipped != chunk["tiles"]):
            raise ValueError(f"Missing/silent skipped tile in {chunk['id']}")
        render_mode=report.get("coast_render_mode","strict_inland")
        if render_mode not in ("strict_inland",COAST_MODE):
            raise ValueError("Unexpected or unsupported render mode")
        if report["status"] == "SKIPPED_no_Colombian_OSM_land":
            if written:
                raise ValueError("Offland-only chunk reported written tiles")
            continue
        if ((report["status"] not in ("SUCCESS_inland_only","SUCCESS_render_only_coast"))
                or (report["status"]=="SUCCESS_inland_only" and render_mode!="strict_inland")
                or (report["status"]=="SUCCESS_render_only_coast" and render_mode!=COAST_MODE)
                or written+report.get("mixed_coast_tiles_written",0)==0):
            raise RuntimeError(f"Chunk {chunk['id']} not successfully rendered")
        name = f"chunk-{chunk['id']}.mbtiles"
        if report.get("mbtiles_file") != name:
            raise ValueError("Unexpected generated file name")
        path = result_dir / name
        if sha256_file(path) != report.get("mbtiles_sha256"):
            raise ValueError("MBTiles file hash differs from native chunk report")
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("Chunk MBTiles failed SQLite validation")
            if db.execute("SELECT count(*) FROM tiles").fetchone()[0] != written+mixed:
                raise ValueError("Chunk reported incorrect native XYZ count")
            if render_mode==COAST_MODE:
                mask_count=db.execute("SELECT COUNT(*) FROM osm_land_mask").fetchone()[0]
                if mask_count!=written+mixed:
                    raise ValueError("Coast-render MBTiles has missing exact OSM land masks")
                mask_without_tile=db.execute("""SELECT COUNT(*) FROM osm_land_mask m
                    LEFT JOIN tiles t USING(zoom_level,tile_column,tile_row)
                    WHERE t.zoom_level IS NULL""").fetchone()[0]
                if mask_without_tile:
                    raise ValueError("Extra OSM land mask with no Terrain-RGB tile")
        sources.append(path)
        actual += written+mixed
    if len(sources) < 2:
        raise RuntimeError("Existing fail-closed merger requires at least two nonempty input shards")
    output = Path(target)
    # A mixed input set with and without masks cannot be safely merged:
    # analytical provenance would be silently lost in the old merger.
    input_modes=set()
    for path in sources:
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro",uri=True) as db:
            mode=db.execute("SELECT value FROM metadata WHERE name='coast_render_mode'").fetchone()
            input_modes.add(mode[0] if mode else "strict_inland")
    if len(input_modes)!=1:
        raise ValueError("Mixed inland/coastal chunk modes: regenerate consistent shards")
    if output.exists():
        raise FileExistsError("Refuse to replace an already published/merged product")
    tmp=output.with_name(output.name+".incomplete")
    tmp.unlink(missing_ok=True)
    report_path=output.with_suffix(".report.json")
    if report_path.exists():
        raise FileExistsError("Refuse to overwrite existing merge report")
    try:
        merged=merge_mbtiles(sources,tmp)
        if merged["tiles"]!=actual:
            raise AssertionError("Merged native tile counts differ from verified reports")
        with sqlite3.connect(tmp) as db:
            if input_modes=={COAST_MODE}:
                db.execute("""CREATE TABLE osm_land_mask(
                    zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER,
                    mask_png BLOB, PRIMARY KEY(zoom_level,tile_column,tile_row))""")
                for path in sources:
                    with sqlite3.connect(f"file:{path.resolve()}?mode=ro",uri=True) as src:
                        for z,x,y,blob in src.execute(
                                "SELECT zoom_level,tile_column,tile_row,mask_png FROM osm_land_mask"):
                            decode_mask_png(blob) # ensure exact 0/255 factual land mask
                            db.execute("INSERT INTO osm_land_mask VALUES (?,?,?,?)",(z,x,y,blob))
                if db.execute("SELECT COUNT(*) FROM osm_land_mask").fetchone()[0]!=actual:
                    raise AssertionError("Merge discarded factual OSM land masks")
                db.execute("INSERT INTO metadata VALUES(?,?)",("coast_render_mode",COAST_MODE))
                db.execute("INSERT INTO metadata VALUES(?,?)",("visualization_sea_surface_m","0"))
                db.execute("INSERT INTO metadata VALUES(?,?)",("sea_surface_is_bathymetry","false"))
                db.execute("INSERT INTO metadata VALUES(?,?)",("osm_land_mask","osm_land_mask table"))
            db.execute("INSERT OR REPLACE INTO metadata(name,value) VALUES(?,?)",
                       ("attribution", "Contains modified Copernicus DEM data; © OpenStreetMap contributors (ODbL 1.0)"))
            desc=("Colombia OSM-land Copernicus Terrain-RGB; ZERO-METRE SEA is VISUAL-ONLY, not bathymetry; use factual osm_land_mask. Not a national release."
                  if input_modes=={COAST_MODE} else
                  "Colombia inland OSM physical-land-only Terrain-RGB; mixed coast excluded, low zoom pending, NOT a complete national release")
            db.execute("INSERT OR REPLACE INTO metadata(name,value) VALUES(?,?)",
                       ("description",desc))
            db.commit()
            if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise AssertionError("Final combined OSM masks failed SQLite integrity")
        report={"status":"MERGED_RENDER_ONLY_NOT_NATIONAL_RELEASE" if input_modes=={COAST_MODE} else "MERGED_INLAND_ONLY_NOT_NATIONAL_RELEASE",
                "coast_render_mode":next(iter(input_modes)),
                "source_manifest_sha256":plan["source_manifest_sha256"],
                "tiles":actual,"chunks_checked":len(plan["chunks"]),
                "merged_mbtiles":str(output),"merged_sha256":sha256_file(tmp),
                "national_release_authorized":False,
                "unresolved":plan["unresolved"]}
        # The unpublishable .incomplete filename stays until all mask and
        # metadata checks pass. A failed merge cannot leave a real MBTiles.
        atomic_json(report_path,report)
        tmp.replace(output)
        return report
    except BaseException:
        tmp.unlink(missing_ok=True)
        report_path.unlink(missing_ok=True)
        raise

def main():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    pp = commands.add_parser("plan", help="Use established national planner, no native raster")
    pp.add_argument("--manifest", type=Path, required=True)
    pp.add_argument("--output-dir", type=Path, required=True)
    pp.add_argument("--minzoom", type=int, default=9)
    pp.add_argument("--maxzoom", type=int, default=13)
    pp.add_argument("--shards", type=int, default=32)
    pp.add_argument("--chunk-tiles", type=int, default=250)
    render = commands.add_parser("render", help="Real native full-land chunk; block mixed coasts")
    render.add_argument("--plan-dir", type=Path, required=True)
    render.add_argument("--chunk-id", required=True)
    render.add_argument("--manifest", type=Path, required=True)
    render.add_argument("--osm-land-clip", type=Path, required=True)
    render.add_argument("--osm-land-meta", type=Path, required=True)
    render.add_argument("--osm-country-geojson", type=Path, required=True)
    render.add_argument("--output-dir", type=Path, required=True)
    render.add_argument("--cache", type=Path, default=Path("output/native-cog-cache"))
    render.add_argument("--coast-render-only-sea-surface",action="store_true",
                        help="Experimental opt-in 0m sea visualization with factual OSM mask; not bathymetry")
    merge = commands.add_parser("merge", help="Reuse original duplicate-safe MBTiles merger")
    merge.add_argument("--plan-dir", type=Path, required=True)
    merge.add_argument("--result-dir", type=Path, required=True)
    merge.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.command == "plan":
        create_plan(args.manifest, args.output_dir, args.minzoom,
                    args.maxzoom, args.shards, args.chunk_tiles)
    elif args.command == "render":
        render_chunk(args.plan_dir, args.chunk_id, args.manifest,
                     args.osm_land_clip, args.osm_land_meta,
                     args.osm_country_geojson, args.output_dir, args.cache,
                     coast_render_surface=args.coast_render_only_sea_surface)
    else:
        merge_verified_chunks(args.plan_dir, args.result_dir, args.output)


if __name__ == "__main__":
    main()
