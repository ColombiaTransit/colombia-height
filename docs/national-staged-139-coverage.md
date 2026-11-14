# National 139-source staging coverage: exact DEM and OSM-land comparison

Date: 14 November 2026. **Status: evidence completed; national publication prohibited.**

- [Successful countrywide 139-source incremental GLO-30 audit, run #43605294875](https://github.com/ColombiaTransit/colombia-height/actions/runs/43605294875)
- [Permanent machine-readable result register](../data/national-staged-139-coverage-2026-11-14.json)
- [Original 137-source native DEM and land QA, run #43490555676](https://github.com/ColombiaTransit/colombia-height/actions/runs/43490555676)
- [Original 137-source precise OSM-land audit, run #43573144549](https://github.com/ColombiaTransit/colombia-height/actions/runs/43573144549)

## Method and scope

Original baseline: 137 publicly available, verified Copernicus GLO-30 COGs. The 32 complete nationwide original source registers verified **96,751 candidate XYZ tiles at zoom 0–13**. Their compact shard data store only **3,778 incomplete tiles**; the other **92,973 fully covered tiles** are certified in the original summary counts. The current script reconstructs those implicit fully covered tiles from the exact original 137-source degree-cell plan, checks every shard's totals and geographical ownership, and fails closed on source or source-precedence changes.

The staged 139-source manifest appends exactly two reviewed COGs **after all original sources**, preserving original native heights at overlaps:

- `Copernicus_DSM_COG_10_N03_00_W082_00_DEM`: Malpelo
- `Copernicus_DSM_COG_10_N03_00_W079_00_DEM`: Gorgona

All *1,558* original/new candidate tiles intersecting the two additional source footprints are evaluated against genuine native Copernicus COG pixels. Every unaffected tile reuses the reconciled original 137-source observation. The augmented 139-source candidate tile set is independently regenerated at each zoom. The exact original 1,917 incomplete z13 OSM-land records are updated for affected source locations; missing DEM on newly included z13 candidate tiles is evaluated separately.

The source cells extend over sea and, in other parts of the original countrywide inventory, across neighboring countries. This is **not a Colombia-only legal land mask**. No NoData is assumed to be 0m water.

## All-zoom result

| Metric | Original 137 COGs | Staged 139 COGs |
|---|---:|---:|
| Candidate XYZ tiles across zoom 0–13 | 96,751 | **98,152** |
| Fully covered native DEM tiles | 92,973 | **94,288** |
| Partially covered native DEM tiles | 3,778 | **3,864** |
| New candidate tiles compared to original inventory | — | 1,401 |

The staged inventory adds a *larger geographic candidate area*; therefore the count of partially covered tiles is not a direct measure of regressions.

## Exact zoom-13 reference-pixel result

| Metric | 137 COG baseline | 139 COG stage |
|---|---:|---:|
| Candidate z13 tiles | 72,108 | 73,166 |
| Incomplete z13 tiles in full **respective** candidate areas | 1,917 | 1,963 |
| Tiles with missing native DEM pixels on OSM land | 1,008 | **1,005** |
| Missing z13 samples **inside OSM land polygons** | 23,879,764 | **23,878,663** |
| Missing z13 samples **outside OSM land (UNKNOWN, NOT confirmed ocean)** | 25,216,184 | 26,564,973 |
| Missing z13 native DEM samples (both categories) | 49,095,948 | 50,443,636 |

**Comparable footprint reconciliation (the original 137-source candidate tiles):**

- Original 1,917 incomplete z13 tiles reduced to **1,851** after adding the two COGs, so **66 originally incomplete tiles are now fully covered**.
- **1,278,812** original missing native z13 pixels recovered: **1,101** inside OSM polygons and **1,277,711** outside OSM polygons (their land/water classification is unknown).
- Missing z13 DEM samples in the original footprint fall from 49,095,948 to **47,817,136**.
- The expanded staged footprint introduces **1,058 new z13 candidate tiles**, of which **112 are partially covered**. They contribute **2,626,500** new missing DEM samples, all *outside* the OSM-land reference. None of those newly introduced unknown pixels may be called ocean or a Colombian land defect without further evidence.
- Arithmetic check: **47,817,136 + 2,626,500 = 50,443,636** missing samples in the expanded staged scope.
- Arithmetic check for OSM land: **23,879,764 − 1,101 = 23,878,663**. The expanded scope has no additional missing OSM-land pixels.

This comparison explicitly separates source *recovery* from the *expanded denominator*. The staged 139-source inventory improves the original study area but is not yet complete countrywide on a geographically authoritative Colombia terrestrial footprint.

## Remaining blockers and next scope decisions

1. **Colombia territorial masking**: the 23,878,663 OSM-land missing pixels include neighboring-country land. OSM coastline is an observation, not Colombian legal jurisdiction. Segregate remaining gaps against independently reviewed Colombian polygons including named offshore islands; do not classify unidentified ocean as land or water.
2. **Tumaco**: the additional original Copernicus source `N01_W080` remains outside the 139-source staging. A previous exact native z13 test recovered valid DEM heights there; Colombian coastal land status requires separate evidence and review before a further source-stage decision.
3. **Other omitted public COGs**: 50 of the original 52 candidate sources remain outside staging; geographic source-cell overlap alone does not demonstrate true Colombian missing elevation, or source validity.
4. **IGAC administrative reference**: unavailable during the staged audit; the IGAC column is intentionally `null`, not an invented zero. Earlier IGAC results are frozen historical context only.
5. **Strict Terrain-RGB**: no ocean depth/zero synthetic fill; no Mapbox Terrain-RGB tiles were created or released; all national production release gates remain closed.

This dataset is from Copernicus DEM GLO-30 Public COGs, which represent a **digital surface model** rather than pure bare-earth terrain. For its general GLO-30 source and release limitations see [AWS Open Data](https://registry.opendata.aws/copernicus-dem/). OSM attribution, when reusing its polygons: © OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright.

## Operational integration

The [national staged QA workflow](../.github/workflows/national-staged-139-osm-qa.yml) runs after the same original/staging inventory generation and downloads the frozen previous 32-shard and exact OSM evidence artifacts. It recomputes only source-affected pixel masks and verifies they preserve original heights. **Results artifacts are retained for one day**; the key measured outcome is retained permanently in the JSON register linked above. If baseline artifacts expire, the frozen national baseline must be regenerated or a new approved preservation mechanism established; the QA must not silently guess original counts.
