# One canonical Colombia terrain pipeline (14 November 2026)

**Status: full z0–13 country-clipped implementation and regression tests passed; final nationwide MBTiles are NOT built or published.** The active entry point is [consolidated_terrain_pipeline.py](../scripts/consolidated_terrain_pipeline.py). It imports existing, tested components rather than rewriting native DEM warping, PNG encoders, OSM polygon handling, or MBTiles merging.

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

- **plan** reuses the 140-source manifest, the established national tile enumeration and unique shard-owner algorithm. It generates immutable, SHA256-checked, bounded chunk rosters. It has no DEM, OSM or remote source request. The current country-plan supports the complete z0–z13 range, up to 150,000 candidates with 250 tiles per chunk by default (hard maximum 1,000).
- **render** reuses the true OSMCoastline land WKB reference, OSM Colombia relation R120027 and the existing native GLO-30 source downloader/warp/PNG SQLite writer. Original 137 COG priority is retained. It downloads only previously verified sources intersecting required Colombian OSM land tiles, including mixed coastal tiles when explicit render-only mode is selected.
- **Strict by default:** a mixed OSM land/offland chunk generates a blocker report before native COG download. **Explicit option 1:** `--coast-render-only-sea-surface` encodes a 0m *visual sea surface* on confirmed physical OSM sea, **not** bathymetry, and preserves every true original native Colombian land elevation. The exact factual boolean mask is stored per terrain tile in the additional `osm_land_mask` SQLite table. A mixed tile with foreign/out-of-Colombia physical land still blocks in the strict sea-only option. The national display mode requires another explicit --render-flat-outside-colombia flag; this records neighboring foreign land as FLAT OUT-OF-SCOPE background, not OSM sea or genuine foreign heights. An all-offland chunk produces no terrain tile or COG download. RGB(0,0,0) / -10,000m fake trenches remain forbidden.
- **merge** checks every planned chunk, counts, SHA256 and SQLite, invokes the existing duplicate-safe merger, then also copies and verifies `osm_land_mask` from every coastal shard into the final database **atomically**. Missing/blocked chunks, inconsistent render modes or invalid mask PNGs prevent any final MBTiles file. The result remains explicitly **non-release**.

The existing 140-source CSV and OSM geometry were preserved in [pilot run #43624636935](https://github.com/ColombiaTransit/colombia-height/actions/runs/43624636935), but its artifacts are retained only **7 days** under the current repository settings. Reuse them instead of redownloading worldwide OSM polygons while available.

### Commands (only with prepared existing inputs)

Plan, no raster reads:

~~~bash
python scripts/consolidated_terrain_pipeline.py plan \
  --manifest output/stage140/colombia_dem_manifest_tumaco_staging_140.csv \
  --output-dir output/terrain-plan-140 \
  --minzoom 0 --maxzoom 13 --shards 32 --chunk-tiles 250
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

By default this command still stops on mixed coastal chunks. For the now-tested complete national display policy, add both **--coast-render-only-sea-surface** and **--render-flat-outside-colombia** to the render or shard command. The first renders only confirmed sea at 0m; the second records physical neighboring countries as a separate 0m out-of-scope display background, never mislabelled sea. All shards must use the same mode. The factual OSM mask is retained in the output and the verified merged database; MapLibre itself ignores that extra table. **Never call the 0m display surface bathymetry, sampled elevation, or a complete Colombia DEM.** Do not launch all national chunks yet.

Merge only when *all* original-source verified national shard reports succeed (not yet run nationwide):

~~~bash
python scripts/consolidated_terrain_pipeline.py merge \
  --plan-dir output/terrain-plan-140 \
  --result-dir output/terrain-chunks \
  --output output/colombia-inland-unreleased.mbtiles
~~~

## Validation and the genuinely unresolved items

[Offline regression workflow](../.github/workflows/validate-consolidated-terrain-pipeline.yml) covers the existing native PNG, original sharding/merge contracts and new chunk orchestration using fixtures only. No national source scans, native COG or global OSM redownloads are triggered by CI.

1. **Option 1 implemented and TileServer GL + MapLibre 6.8 browser passed:** [real Cartagena #43628318643](https://github.com/ColombiaTransit/colombia-height/actions/runs/43628318643) rendered 28 OSM-mask candidates at z11–13: 17 mixed coastal, 9 full land, 2 offland skipped; emitted **26 actual Terrain-RGB+land-mask tiles** from the existing 140-source roster. All 1,142,998 original land pixels were preserved within **0.05m**, and **560,938 confirmed sea pixels** became an explicit render-only 0m surface (not bathymetry). Test output [artifact #14126918472](https://github.com/ColombiaTransit/colombia-height/actions/runs/43628318643/artifacts/14126918472), seven-day retention. The actual end-to-end TileServer GL Docker and MapLibre Chromium test [#43630855308](https://github.com/ColombiaTransit/colombia-height/actions/runs/43630855308) passed for 26 real Cartagena tiles with exact delivered RGB heights and no DEM/JS errors. Nationwide cross-zoom and border rendering still requires final QA.
2. **Full z0–13 engine implemented:** the real lowzoom z0–3 [#43635436079](https://github.com/ColombiaTransit/colombia-height/actions/runs/43635436079) succeeded with seven original Copernicus native tiles; z4–8 source cells have an OSM mask audit [#43634723596](https://github.com/ColombiaTransit/colombia-height/actions/runs/43634723596). Native production and cross-zoom QA over the whole country are not yet performed.
3. **National output and draft storage:** [manual immutable 32-shard draft build](../.github/workflows/national-terrain-draft-build.yml) and [actual 85GB disk / size estimate](national-generator-z0-z13-storage-and-build.md) are now implemented but not yet executed for the entire country. Final export/attribution/size: once the two gates above are solved, use the old 140 COG sources and validated merging/edge checks, and select storage for national output without exceeding free-runner artifact quotas.

**Do not repeat:** inventory of 137/139/140 COGs, all 32 original national DEM shards, old 997 potential foreign land deficits, 68 Tumaco candidates, 2026-11-14 island/source reconciliation, or the previous Medellín/coastal/COG-junction pilots. Source attribution: Contains modified Copernicus DEM data; © OpenStreetMap contributors (ODbL 1.0).
