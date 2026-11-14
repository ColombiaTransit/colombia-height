# One canonical Colombia terrain pipeline (14 November 2026)

**Status: consolidated orchestration implemented and offline CI passed; not a nationwide release.** The active entry point is [consolidated_terrain_pipeline.py](../scripts/consolidated_terrain_pipeline.py). It imports existing, tested components rather than rewriting native DEM warping, PNG encoders, OSM polygon handling, or MBTiles merging.

## Verified components to retain, not rerun

| Component | Original implementation | Completed evidence |
| --- | --- | --- |
| Native GLO-30 warp / COG seam QA | [two_cog_seam_pilot.py](../scripts/two_cog_seam_pilot.py) | [two-source #43387160709](https://github.com/ColombiaTransit/colombia-height/actions/runs/43387160709), [four-source #43389958360](https://github.com/ColombiaTransit/colombia-height/actions/runs/43389958360) |
| Terrain-RGB PNG and SQLite | [generate_osm_land_only_terrain.py](../scripts/generate_osm_land_only_terrain.py) | [real native 10-tile pilot #43624636935](https://github.com/ColombiaTransit/colombia-height/actions/runs/43624636935) |
| Original coast-and-islands pilot | [coastal_terrain_pilot.py](../scripts/coastal_terrain_pilot.py) | [#43210445882](https://github.com/ColombiaTransit/colombia-height/actions/runs/43210445882), 20 DEM-complete tiles each in Cartagena, Buenaventura, San Andrés |
| Exact OSM physical land + Colombia mask | [osm_national_land_audit.py](../scripts/osm_national_land_audit.py), [generate_osm_land_only_terrain.py](../scripts/generate_osm_land_only_terrain.py) | [#43612505074](https://github.com/ColombiaTransit/colombia-height/actions/runs/43612505074), [#43624636935](https://github.com/ColombiaTransit/colombia-height/actions/runs/43624636935) |
| Unique tile ownership / 32-shard plan | [national_tile_plan.py](../scripts/national_tile_plan.py) | [#43199806768](https://github.com/ColombiaTransit/colombia-height/actions/runs/43199806768), 96,751 candidates for original 137 |
| Strict duplicate-safe MBTiles merge | [merge_regions.py](../scripts/merge_regions.py) | [#43385550734](https://github.com/ColombiaTransit/colombia-height/actions/runs/43385550734) |
| Reviewed 140 COG staging inventory | [stage_tumaco_140.py](../scripts/stage_tumaco_140.py) | [#43609451961](https://github.com/ColombiaTransit/colombia-height/actions/runs/43609451961) |

Historical pilots remain as tests and evidence. They are not alternative production generators. The coastal experiment used Natural Earth for reference and only accepted complete DEM tiles: it did **not** establish the approved OSM-only handling of partially missing mixed coast tiles.

## Consolidated workflow

- **plan** reuses the 140-source manifest, the established national tile enumeration and unique shard-owner algorithm. It generates immutable, SHA256-checked, bounded chunk rosters. It has no DEM, OSM or remote source request. The current safe stage covers z9–z13, up to 150,000 candidates with 250 tiles per chunk by default (hard maximum 1,000).
- **render** reuses the true OSMCoastline land WKB reference, OSM Colombia relation R120027 and the existing native GLO-30 source downloader/warp/PNG SQLite writer. Original 137 COG priority is retained. It downloads only sources actually intersecting fully inland tiles.
- A chunk with **any mixed OSM land/offland pixels** generates a blocker report and fails **before native download or SQLite writing**. A chunk with no Colombian OSM land generates a skip report and no COG download. It never inserts RGB(0,0,0), fake bathymetry or 0 m for NoData.
- **merge** checks reports for every planned chunk, verifies correct counts, hashes and SQLite integrity, then invokes the existing duplicate-safe MBTiles merger. Missing and blocked chunks prevent a countrywide merge. The result is explicitly marked **non-release**.

The existing 140-source CSV and OSM geometry were preserved in [pilot run #43624636935](https://github.com/ColombiaTransit/colombia-height/actions/runs/43624636935), but its artifacts are retained only **7 days** under the current repository settings. Reuse them instead of redownloading worldwide OSM polygons while available.

### Commands (only with prepared existing inputs)

Plan, no raster reads:

~~~bash
python scripts/consolidated_terrain_pipeline.py plan \
  --manifest output/stage140/colombia_dem_manifest_tumaco_staging_140.csv \
  --output-dir output/terrain-plan-140 \
  --minzoom 9 --maxzoom 13 --shards 32 --chunk-tiles 250
~~~

Render one chunk; substitute an actual chunk ID from plan.json:

~~~bash
python scripts/consolidated_terrain_pipeline.py render \
  --plan-dir output/terrain-plan-140 \
  --chunk-id 000-0000 \
  --manifest output/stage140/colombia_dem_manifest_tumaco_staging_140.csv \
  --osm-land-clip output/osm-reference/osm-land-study.wkb.gz \
  --osm-land-meta output/osm-reference/osm-land-study-metadata.json \
  --osm-country-geojson output/osm-country/colombia-relation-120027.json \
  --output-dir output/terrain-chunks \
  --cache output/native-cog-cache
~~~

This command will deliberately stop on any chunk containing mixed coastal tiles. Do not launch all national chunks or publish inland-only results as complete Colombia.

Merge only when *all* shard reports succeed (not yet possible nationwide):

~~~bash
python scripts/consolidated_terrain_pipeline.py merge \
  --plan-dir output/terrain-plan-140 \
  --result-dir output/terrain-chunks \
  --output output/colombia-inland-unreleased.mbtiles
~~~

## Validation and the genuinely unresolved items

[Offline regression workflow](../.github/workflows/validate-consolidated-terrain-pipeline.yml) covers the existing native PNG, original sharding/merge contracts and new chunk orchestration using fixtures only. No national source scans, native COG or global OSM redownloads are triggered by CI.

1. **Renderer-safe mixed coast/no-data encoding:** MapLibre raster-dem decodes RGB and does not treat transparent alpha as an authoritative missing-height mask. This is a real unresolved consumer compatibility gate; do not fill ocean with fabricated depths.
2. **z0–z8 implementation and all-zoom renderer verification:** the new adapter deliberately limits rendering to z9–13. Prior national planning covered z0–13 but was a dry run, not finished native output.
3. **Final export/attribution/size:** once the two gates above are solved, use the old 140 COG sources and validated merging/edge checks, and select storage for national output without exceeding free-runner artifact quotas.

**Do not repeat:** inventory of 137/139/140 COGs, all 32 original national DEM shards, old 997 potential foreign land deficits, 68 Tumaco candidates, 2026-11-14 island/source reconciliation, or the previous Medellín/coastal/COG-junction pilots. Source attribution: Contains modified Copernicus DEM data; © OpenStreetMap contributors (ODbL 1.0).
