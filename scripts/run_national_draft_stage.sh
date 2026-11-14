#!/usr/bin/env bash
# Durable but NEVER automatically published national Terrain-RGB staging.
# Called by workflow_dispatch only. Requires GITHUB_TOKEN contents:write.
set -euo pipefail
STAGE="$1"
DRAFT_TAG="$2"
SHARD_ID="$3"

[[ "$DRAFT_TAG" =~ ^colombia-terrain-draft-[A-Za-z0-9-]+$ ]] || {
  echo "Draft release tag must start with colombia-terrain-draft-"
  exit 1
}

require_draft() {
  test "$(gh release view "$DRAFT_TAG" --json isDraft --jq .isDraft)" = true || {
    echo "Refuse non-draft release: $DRAFT_TAG"
    exit 1
  }
}

disk_gate() {
  local required="$1"
  df -h .
  python -c 'import shutil,sys; n=shutil.disk_usage(".").free/1024**3; lo=float(sys.argv[1]); print(f"Actual runner free disk: {n:.2f}GiB, requires {lo:g}GiB"); sys.exit(0 if n>=lo else 1)' "$required"
}

if [[ "$STAGE" == prepare ]]; then
  # Source artifact is already downloaded by the workflow before this point.
  test -f output/stage140/colombia_dem_manifest_tumaco_staging_140.csv
  test -f output/osm-reference/osm-land-study.wkb.gz
  test -f output/osm-country/colombia-relation-120027.json
  python scripts/consolidated_terrain_pipeline.py plan \
    --manifest output/stage140/colombia_dem_manifest_tumaco_staging_140.csv \
    --output-dir output/plan --minzoom 0 --maxzoom 13 \
    --shards 32 --chunk-tiles 250
  mkdir -p output/draft-assets
  tar -czf output/draft-assets/colombia-terrain-inputs.tar.gz \
    -C output stage140 osm-reference osm-country
  tar -czf output/draft-assets/colombia-terrain-plan.tar.gz \
    -C output plan
  if gh release view "$DRAFT_TAG" >/dev/null 2>&1; then
    echo "Existing release tag: refuse overwriting immutable source and plan"
    exit 1
  fi
  gh release create "$DRAFT_TAG" --draft \
    --title "UNPUBLISHED Colombia OSM Terrain-RGB, z0-13" \
    --notes "DRAFT ONLY. Original DEM on positive Colombian OSM physical land; flat out-of-country background and sea are VISUAL ONLY and not measured elevation or bathymetry. Do NOT publish until final national QA."
  gh release upload "$DRAFT_TAG" \
    output/draft-assets/colombia-terrain-inputs.tar.gz \
    output/draft-assets/colombia-terrain-plan.tar.gz
  echo "PLAN COMPLETE; prepared original OSM data and 140-source manifest stored in unpublished draft release"
  exit 0
fi

if [[ "$STAGE" == build-shard ]]; then
  [[ "$SHARD_ID" =~ ^([0-9]|[12][0-9]|3[01])$ ]] || {
    echo "Shard must be between 0 and 31"
    exit 1
  }
  disk_gate 25
  require_draft
  mkdir -p output/download
  gh release download "$DRAFT_TAG" --dir output/download \
    --pattern 'colombia-terrain-plan.tar.gz'
  gh release download "$DRAFT_TAG" --dir output/download \
    --pattern 'colombia-terrain-inputs.tar.gz'
  tar -xzf output/download/colombia-terrain-plan.tar.gz -C output
  tar -xzf output/download/colombia-terrain-inputs.tar.gz -C output
  python scripts/consolidated_terrain_pipeline.py shard \
    --plan-dir output/plan --shard-id "$SHARD_ID" \
    --manifest output/stage140/colombia_dem_manifest_tumaco_staging_140.csv \
    --osm-land-clip output/osm-reference/osm-land-study.wkb.gz \
    --osm-land-meta output/osm-reference/osm-land-study-metadata.json \
    --osm-country-geojson output/osm-country/colombia-relation-120027.json \
    --output-dir output/shard-chunks --cache output/native-source-cache \
    --coast-render-only-sea-surface --render-flat-outside-colombia \
    --start-free-gib 25 --reserve-free-gib 10
  mkdir -p output/draft-assets
  archive="$(printf 'colombia-shard-%03d.tar' "$SHARD_ID")"
  tar -cf "output/draft-assets/$archive" -C output/shard-chunks .
  size=$(stat -c%s "output/draft-assets/$archive")
  echo "Shard archive size: $size bytes"
  test "$size" -lt 1800000000 || {
    echo "Shard archive >1.8 GB, GitHub Release asset must remain under 2 GiB"
    exit 1
  }
  require_draft
  # No --clobber: previous finished output is immutable. GitHub can rerun only failed jobs.
  gh release upload "$DRAFT_TAG" "output/draft-assets/$archive"
  echo "SHARD COMPLETE: $SHARD_ID in UNPUBLISHED draft release"
  exit 0
fi

if [[ "$STAGE" == merge ]]; then
  disk_gate 35
  require_draft
  mkdir -p output/download output/shard-chunks
  gh release download "$DRAFT_TAG" --dir output/download \
    --pattern 'colombia-terrain-plan.tar.gz'
  tar -xzf output/download/colombia-terrain-plan.tar.gz -C output
  gh release download "$DRAFT_TAG" --dir output/download \
    --pattern 'colombia-shard-*.tar'
  python - <<'PY'
import json
from pathlib import Path
plan=json.loads(Path("output/plan/plan.json").read_text())
expected={int(c["shard"]) for c in plan["chunks"]}
actual={int(p.stem.split("-")[-1]) for p in Path("output/download").glob("colombia-shard-*.tar")}
if expected!=actual:
    raise ValueError(f"Missing/extra shard assets: expected {sorted(expected)} / actual {sorted(actual)}")
print(f"All {len(actual)} national shards available, now checking each chunk ledger and bytes")
PY
  for archive in output/download/colombia-shard-*.tar; do
    tar --keep-old-files -xf "$archive" -C output/shard-chunks
  done
  python scripts/consolidated_terrain_pipeline.py merge \
    --plan-dir output/plan --result-dir output/shard-chunks \
    --output output/colombia-terrain.mbtiles
  PYTHONPATH=scripts python - <<'PY'
import json, sqlite3
from pathlib import Path
from render_only_coast_rgb import COUNTRY_CLIP_MODE
p=Path("output/colombia-terrain.mbtiles")
summary=json.loads(p.with_suffix(".report.json").read_text())
assert summary["coast_render_mode"]==COUNTRY_CLIP_MODE
assert summary["national_release_authorized"] is False
with sqlite3.connect(p) as db:
    assert db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    assert db.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]==summary["tiles"]
    assert db.execute("SELECT COUNT(*) FROM osm_land_mask").fetchone()[0]==summary["tiles"]
    meta=dict(db.execute("SELECT name,value FROM metadata"))
    assert (int(meta["minzoom"]),int(meta["maxzoom"]))==(0,13)
print(f"MERGED ({p.stat().st_size/1024**3:.2f}GiB), strict country-only data + mask, NOT PUBLISHED")
PY
  mkdir -p output/draft-assets
  split --bytes=1536M --numeric-suffixes=0 --suffix-length=3 \
    output/colombia-terrain.mbtiles output/draft-assets/colombia-terrain.mbtiles.part-
  (
    cd output
    sha256sum colombia-terrain.mbtiles >draft-assets/colombia-terrain.mbtiles.sha256
  )
  require_draft
  gh release upload "$DRAFT_TAG" \
    output/draft-assets/colombia-terrain.mbtiles.part-* \
    output/draft-assets/colombia-terrain.mbtiles.sha256 \
    output/colombia-terrain.report.json
  echo "FINAL DRAFT PARTS READY. Reassemble locally with cat and verify .sha256. No public release."
  exit 0
fi

echo "Unknown stage: $STAGE"
exit 2
