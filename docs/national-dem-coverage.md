# National native DEM coverage registry

This is Step 1 of the Colombia Terrain-RGB national build: classify the
already-planned 137 Copernicus GLO-30 source cells and up to 96,751
candidate XYZ tiles, not generate Terrain-RGB MBTiles.

The [National DEM Pixel Coverage Register](../.github/workflows/national-dem-coverage.yml)
workflow offers **pilot** and **full** modes. Pushes to the workflow
run a small pilot only; the expensive 32-shard scan must be chosen
explicitly using workflow_dispatch mode=full.

## Method

Reproduce the current 137-source extended inventory and fail closed if
its count or HEAD status changes. Candidates reuse the existing
`national_tile_plan.candidate_tiles` method (degree-cell intersection,
no assumed land cover). Every candidate XYZ has one regional geographic
owner. Zooms 0–8 go to shard 0, and zooms 9–13 are spatially grouped
into an 8-column × 4-row regional grid. An output tile is assigned to
exactly one shard.

For each candidate tile, the classifier:
1. identifies nearby 1-degree Copernicus COGs with a two-native-pixel
   bilinear margin;
2. downloads only needed source GeoTIFFs into its transient runner
   cache, independently from other shards;
3. uses the **native source grid**, original source NoData and the
   validated per-tile 256 × 256 Web Mercator warp;
4. classifies the full 65,536 output pixel mask as
   `full_dem_coverage`, `partial_dem_coverage`, or
   `no_dem_coverage`, and records valid/missing counts; and
5. writes compressed row-level XYZ/TMS records plus a JSON shard
   summary. No RGB PNG or MBTiles is created.

The 32-shard reconciler fails if a shard is absent, if XYZ IDs
are duplicated, if geographic ownership differs, or if the total
does not match the independently recomputed national candidate count.

## Critical interpretation

A **full DEM tile is NOT automatically publishable**. Copernicus
can contain valid heights over offshore cells, and native source
availability does not determine official Colombian territory.
Missing pixels must not be encoded as arbitrary -10,000m or 0m.
Partial and absent tiles remain gated until a separate land/ocean
policy and official coastline/island inclusion review.

The workflow reports `national_publication_allowed=false` even
when all source coverage counts reconcile.

The first bounded pilot samples 24 candidates from geographic shard 12
at zooms 10–11. It deliberately labels this output `complete=false`
and cannot be confused with national coverage. National full scanning
is deliberately not automatic, to protect free GitHub Actions budget.

All artifacts have one-day retention and are removed by the
existing temporary test-artifact cleanup allowlist.

## Initial pilot results — 13 November 2026

The first 32-shard architecture smoke test
[run 43422120885](https://github.com/ColombiaTransit/colombia-height/actions/runs/43422120885)
passed. The source manifest reverified **137 COGs**, and 24 bounded
sample output tiles in geographic shard 12 at zoom 10 all had full
native DEM pixel coverage. This is a *sample*, not national coverage.

The subsequent targeted Tumaco check found an important
**source-selection difference**, first exposed by
[run 43422421562](https://github.com/ColombiaTransit/colombia-height/actions/runs/43422421562)
and diagnosed by the passing
[run 43422773930](https://github.com/ColombiaTransit/colombia-height/actions/runs/43422773930):

| XYZ tile | Native sources used | Valid / 65,536 | Missing |
| --- | ---: | ---: | ---: |
| 11/574/1012 in 137-source selected inventory | 2 | 27,648 | **37,888** |
| Earlier local all-available-source audit | 3 | 42,152 | **23,384** |

The missing **14,504** additional pixels come from a COG present in
the public Copernicus global catalog but **omitted from the currently
selected Colombia inventory**:
`Copernicus_DSM_COG_10_N01_00_W080_00_DEM`.

This source is offshore in the test area; do **not** automatically
assign it to Colombian territory or add it to the national input
manifest without an official-scoped coverage decision.

**Classification convention:** full/partial/no coverage means
coverage from the **137 selected source COGs**, not all Copernicus
sources worldwide and not a country jurisdiction classification.
A future inventory-scope check must distinguish absent data within
a selected source from adjacent *unselected* source COGs, especially
along the coast.

The full 32-shard workflow is available separately as manual
`workflow_dispatch` mode `full`. It has not been run by these pilots.
Its result must reconcile all candidates before national coverage
counts may be stated.
