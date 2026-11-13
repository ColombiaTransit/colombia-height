# National land-reference validation (non-publication)

This follows the successful 32-shard native DEM scan,
[run 43435820259](https://github.com/ColombiaTransit/colombia-height/actions/runs/43435820259).
The 137-source scan classified **96,751** z0–13 candidates as **92,973
complete** and **3,778 partial**. A complete DEM tile is *not*
equivalent to Colombian territory, and an incomplete pixel is *not* ocean.

## Reference geometry and limitations

Compare two independent but **non-authoritative** layers:

- [geoBoundaries Colombia ADM0](https://www.geoboundaries.org/api/current/gbOpen/COL/ADM0/)
  (versioned GeoJSON URL and licence recorded in the report).
- [Natural Earth 1:10m land and minor islands](https://www.naturalearthdata.com/downloads/10m-physical-vectors/)
  (both layers; minor islands can be missing from a simplified country polygon).

Authoritative IGAC mapping is a *future territorial review*.
[IGAC publishes administrative and border geometry](https://mapas2.igac.gov.co/server/rest/services/limites/limites/MapServer),
but administrative boundaries are not automatically an exact
pixel-level coastline. Never infer sovereignty or water from the
provisional comparison. Quitasueño remains excluded by project decision.

Classify each missing native DEM pixel into **one** of four buckets:
(1) both references say land, (2) geoBoundaries only,
(3) Natural Earth only, or (4) outside both references — **unknown,
NOT "sea"**. Missing DEM pixels are never replaced by 0 m or -10000 m.

## Execution

The [National Land Coverage Validation workflow](../.github/workflows/national-land-coverage.yml)
supports manually selected **pilot** and **full** modes. Changes to
the implementation automatically start the pilot only.

**Pilot**: 3×3 zoom-11 neighborhoods at Tumaco, San Andrés, Providencia
and Malpelo — 36 tiles, nine per site. All are compared with both
reference masks, including full-DEM tiles. Tumaco includes known XYZ
**11/574/1012**. Reports list disjoint missing-pixel counts and candidate
public Copernicus cells outside the 137-source manifest.

**Full**: *manual only*, 32 geographic shards and the existing
candidate/ownership model. The selected source DEM masks are recomputed;
only incomplete tiles are output to compressed per-shard records.
The reconciler checks 32 shards, unique XYZ ownership, all missing
pixel partitions, and the current 96,751/92,973/3,778 baseline.
If the input manifest changes, halt for review. Reprocessing is
independent of the earlier 1-day national DEM artifacts.

All new artifacts expire after **one day**. No national MBTiles or
permanent Releases are created.

## Unselected source COGs

The global Copernicus catalog is compared to missing DEM pixels to
suggest *possibly omitted* 1-degree COG cells, but no COG is added to
the approved input manifest automatically. Near Tumaco, public cell
`Copernicus_DSM_COG_10_N01_00_W080_00_DEM` is a known inventory
scope difference. Source masks, coastline and island jurisdiction
must be reviewed before changing the inventory. Extra source hints
are only produced at zooms 9–13 (lower zoom tiles are too broad).

## Acceptance

- Pilot reports 36 tiles, 9 per site, including Tumaco's known gap.
- Four mutually exclusive categories sum to exact missing DEM pixels.
- Disagreeing or absent reference land is **not** silently called sea.
- Nationwide mode, if run, reconciles all 3,778 incomplete candidates.
- Every report explicitly retains `national_publication_allowed: false`.

Before production: verify official IGAC land/island geometry and
reference disagreements; resolve missing land DEM; decide the strict
partial-tile encoding/omission policy; continue systematic source-edge
QA. Existing valid heights must never be overwritten.
