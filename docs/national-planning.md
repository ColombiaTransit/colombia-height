# Eight small-island candidates and national slippy-tile ownership

## Small-island source-cell reconciliation

The extended inventory run (43195302813) listed **8** Natural Earth
`ne_10m_minor_islands` polygon representative points within 0.35° of known
island/cay sampling locations. Their sample points are recorded in
`data/minor-island-review.json`:

- 2 near the San Bernardo archipelago: source COG `N09 W076`.
- 5 near Serranilla Bank: source COG `N15 W080`.
- 1 near Bajo Nuevo Bank: source COG `N15 W079`.

All three source COGs **are already in the extended 137-source manifest**.
No additional Copernicus degree cells are needed *for these eight locations*.
The reconciler in `scripts/reconcile_minor_islands.py` checks this directly
against a freshly rebuilt extended CSV, and fails if that assertion becomes
false.

These records remain **pending official territorial and native DEM-pixel
verification**. Proximity to a named bank or an available 1° DEM COG does not
establish sovereignty, emergence above water, or local DEM data quality.
Quitasueño Bank is excluded from this dataset's maintainer-defined scope.

## National planning — no DEM output yet

The [National DEM Tile Plan (Dry Run)](../.github/workflows/national-tile-plan.yml)
workflow runs the baseline inventory, extends it with the island registry,
reconciles the eight minor-island candidates, and computes candidate
Web Mercator tiles for zoom levels 0–13.

`scripts/national_tile_plan.py` deduplicates slippy tile IDs before
assigning them deterministically to shards:

- Low zoom (z0–6) belongs solely to shard 0 to avoid splitting
  globally spanning coarse zoom tiles.
- For z7–13, a tile's z7 ancestor selects its shard, and all
  descendants stay in the same shard.
- Unique candidate z/x/y identifiers and shard ownership are tested
  and counted. Candidate lists are **not uploaded**; only summary
  reports are attached, with one-day artifact retention.
- Ownership is independent of the order of DEM source rows.

**The planner is NOT a production build.** One-degree source bounding
cells are used conservatively and may cover a great deal of ocean.
The planner does not identify land and water, validate native DEM
masks nationwide, eliminate DEM edge voids, or produce MBTiles.

### Gate before release

1. Confirm official offshore land/cay geometries and native source
   coverage, including the eight nominated Natural Earth shapes.
2. Implement a vetted water/no-data policy and test coastal
   interpolation. Missing source data cannot be silently mapped to
   either -10,000m or sea level.
3. Prove exact tile-edge continuity between shards and run
   a multi-shard experimental build before any nationwide release.
4. Estimate disk/memory/time and release size per shard.
5. Keep only published, validated releases long-term; transient Action
   reports expire after one day.
