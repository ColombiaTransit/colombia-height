# Nationwide provisional land-reference results — 13 November 2026

The 32-shard [National Land Coverage Validation run #43490555676](https://github.com/ColombiaTransit/colombia-height/actions/runs/43490555676) **succeeded** (all shard jobs and final reconciliation). The detailed shard records were read from the 32 one-day GitHub Actions ZIP artifacts; this retained summary preserves the findings after artifact expiry.

## Verified overall totals

| Metric | Value |
| --- | ---: |
| Selected original Copernicus GLO-30 COGs | 137 |
| Candidate tiles z0–13, each counted exactly once | 96,751 |
| Tiles with full native DEM pixel coverage | 92,973 |
| Tiles with partial native DEM pixel coverage | 3,778 |
| Partially covered tiles with missing pixels inside Natural Earth land but outside geoBoundaries COL ADM0 | 1,946 |
| Partially covered tiles with missing pixels outside both land references | 2,084 |
| Tiles in both preceding groups | **252** |
| Native DEM pixel samples missing inside **both** land references | **0** |
| Native DEM pixel samples missing inside geoBoundaries only | **0** |
| Native DEM pixel samples missing inside Natural Earth only | **45,024,354** |
| Native DEM pixel samples missing outside both reference polygons | **60,194,108** |
| Missing pixel samples across all zooms | **105,218,462** |
| COGs in public catalog not selected but near missing pixels | 52 |
| Tiles with at least one potential unselected catalog cell | 2,245 |
| Shards reconciled | 32/32 |
| Duplicate/incorrect XYZ ownership | 0 |
| National publication authorized | **No** |

**CRITICAL: Pixel counts sum over z0–13 and therefore repeatedly sample the same physical areas at different resolutions. They are NOT an area measurement, independent ground pixels, or an assertion that 45 million Colombian land pixels lack height.** The worldwide Natural Earth land reference was clipped to a rectangular Colombia study envelope (lon -84 to -66, lat -5 to 17), but **this rectangle includes neighboring countries**. That explains why Natural Earth-only gaps cannot be interpreted as national territorial gaps without official coastline/island geometry.

## Missing DEM reference pixels by zoom

| Zoom | Partial tiles | Missing inside Natural Earth only | Missing outside both references |
| --- | ---: | ---: | ---: |
| 0 | 1 | 56 | 65,414 |
| 1 | 2 | 174 | 130,616 |
| 2 | 2 | 716 | 129,240 |
| 3 | 2 | 2,985 | 123,669 |
| 4 | 3 | 10,846 | 167,919 |
| 5 | 6 | 38,381 | 283,394 |
| 6 | 12 | 140,581 | 360,406 |
| 7 | 27 | 416,970 | 734,922 |
| 8 | 61 | 791,959 | 1,523,116 |
| 9 | 119 | 1,294,864 | 2,521,201 |
| 10 | 235 | 2,751,225 | 4,980,819 |
| 11 | 466 | 6,069,541 | 9,143,155 |
| 12 | 925 | 9,556,370 | 14,883,975 |
| 13 | 1,917 | 23,949,686 | 25,146,262 |
| **Total** | **3,778** | **45,024,354** | **60,194,108** |

At z13, 1,004 partial tiles have missing pixels inside Natural Earth-only land; 1,011 have missing pixels outside both references. These groups overlap. **Do not call either group confirmed missing Colombian land or confirmed ocean**.

## Native COG source expansion: targeted evidence

A separate read-only [18-tile source comparison run #43491477657](https://github.com/ColombiaTransit/colombia-height/actions/runs/43491477657) tested:

- Tumaco: `Copernicus_DSM_COG_10_N01_00_W080_00_DEM` recovered 90,280 genuine native DEM pixels, including **all 1,691** provisional missing reference-land pixels. **23,384** pixels remain missing outside both references.
- Malpelo: `Copernicus_DSM_COG_10_N03_00_W082_00_DEM` recovered 348,672 native DEM pixels, including **all 1,329** provisional missing reference-land pixels. No missing pixels remain in the nine z11 pilot tiles.

Original valid height samples remain unchanged; no synthetic zero sea-level or bathymetry was generated. Both COGs remain **outside** the selected 137-source production manifest pending formal scope approval. See [source expansion review](../data/provisional-source-expansion-review.json).

## Interpretation, unresolved gates, and next recommended action

1. **Territorial scope:** compare the 52 candidate source cells and the 1,946 incomplete Natural Earth-only reference tiles with suitable official IGAC land/island geometry. Use DIMAR coastal data where appropriate. A rectangular bounding box and unfiltered Natural Earth polygons cannot assign Colombian jurisdiction.
2. **Independent coastal diagnostics:** prioritize high-zoom tiles with reference-land discrepancies. Nearby public COG existence only signals a *candidate* source: it does **not** guarantee recovery or that the source belongs to Colombia.
3. **Final source selection:** approve additional COGs only when they recover necessary real land heights inside a reviewed Colombian scope; preserve the baseline 137-source reproducibility and logged provenance. The Tumaco and Malpelo test confirms two strong candidates but not a blanket 52-source expansion.
4. **Strict tile policy:** retain original valid heights. Unknown missing pixels stay unencoded and unfilled. No ocean zero, -10000m trench, or unapproved partial-tile Terrain-RGB release.
5. **National build gating:** only after official territory/shoreline verification, successful source-edge QA and a publication-safe missing-pixel policy, build/merge MBTiles and consider release.

Result: **national source-DEM and provisional reference-mask discovery are complete**; national land/ocean resolution and production are not.
