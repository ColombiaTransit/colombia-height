# National Terrain-RGB draft: automated QA results (15 November 2026)

This is a **quality report for the existing UNPUBLISHED draft**, not permission
to publish or a substitute for provenance-aware interpretation.

## Original product, no rebuilding

- Original release: `colombia-terrain-draft-2026-11-14` (**draft-only**).
- Source: the already reviewed 140 Copernicus GLO-30 source-cell inventory,
  genuine OSMCoastline physical land, and Colombia OSM relation R120027.
- Original MBTiles (SHA-256):
  `daa49c62e2c08b8922ca7f2c9f7575346b37cdcd4b1a84659f03d3d818377bdb`.
- Size: **4,466,196,480 bytes (~4.16 GiB)**; native Mapbox Terrain-RGB 256 px
  PNGs in MBTiles, zoom **0–13**.
- **98,904** source-cell candidate tiles in **409** immutable chunks.
  Exactly **26** shards contain candidate tiles; six intentionally contain
  none (IDs 3, 8, 9, 10, 25, 27).

## Automated national OSM/native-pixel integrity — PASS

Evidence: [real national pixel and OSM QA run
#43688658311](https://github.com/ColombiaTransit/colombia-height/actions/runs/43688658311),
and its preserved JSON report in the draft release. That workflow's overall
result was **failure solely because the separate, subsequent MapLibre browser
smoke reported a premature style-loaded state**. The independent pixel QA
step itself passed and its result was carried forward unchanged.

- **66,607** actual Terrain-RGB PNG tiles and **66,607** factual 256x256
  grayscale OSM land-mask PNGs verified one-to-one.
- **62,312** full Colombian land tiles and **4,295** land/offland tiles.
- **4,217,511,110** genuine Colombian land height pixels; **147,645,242**
  explicitly flat, **visual-only** out-of-scope/background pixels.
- All 14 zoom levels contain generated native terrain.
- **303** stored masks were independently regenerated from the original
  audited OSMCoastline and R120027 geometry: **zero discrepancies**.
- **32,297** source-cell candidates are intentionally not emitted;
  **151** of these were additionally sampled against original OSM:
  **none contained Colombian land**. The original chunk generator and merger
  had already independently enforced skip/written accounting for all
  candidate tiles. Do not describe the 151-sample audit as exhaustive.
- Rasterized original-land elevation range: **-239.1 to 5,691.6 metres**.
  This is an observed encoded minimum/maximum, not an independently
  surveyed national altitude claim. In particular, the most negative land
  pixel should be separately geo-located and explained before treating
  the feed as an analytical elevation reference.
- 510 sampled adjacent land-only tile boundaries: absolute cross-edge
  pixel gradients p50 **1.0 m**, p95 **11.7 m**, p99 **24.1 m**,
  max **123.9 m**. These are observed gradients; peaks may be natural relief
  and are not, alone, evidence of a COG seam.

## Real TileServer GL — PASS

Actual `maptiler/tileserver-gl` Docker serving the original MBTiles:

- Real national TileJSON advertises PNG format, zoom **0–13**.
- **71** geographically sampled Terrain-RGB PNGs, covering every zoom, gave
  pixel-identical decoded heights through TileServer GL.
- A genuinely absent ocean/offland tile returned HTTP **204**, not an
  artificial zero-ocean tile.
- Original nationwide MBTiles SHA-256 was unchanged after serving.

The exact test JSON is saved as
`national-real-tileserver-gl-qa.json` in the original draft release.

## Real MapLibre GL JS 6.8 Chromium browser — PASS 7/7

The first two browser workflows had **test-harness timing/version mistakes**
(undefined ESM `version`, then prematurely treating an in-flight
`isStyleLoaded()` as a durable failure); original DEM data was not modified.
Final successful browser-only recovery run:
[#43689989955](https://github.com/ColombiaTransit/colombia-height/actions/runs/43689989955).

The independent original full-pixel and HTTP JSON reports were **reused**, not
recalculated. Chromium waited for real completed 3D terrain and a settled
MapLibre style. **All seven real regional scenes passed** using the genuine
TileServer GL Docker instance, with real Terrain-RGB PNGs, and **zero reported
DEM/JavaScript/HTTP errors**:

| Scene | MapLibre terrain elevation at test point |
| --- | ---: |
| Bogotá — Andes | 2,556.2 m |
| Medellín — Andes | 1,476.7 m |
| Cartagena — Caribbean coast | 0.0 m (visual-only coast sampling) |
| Tumaco — Pacific coast | 6.8 m |
| San Andrés — island | 3.7 m |
| Leticia — Amazon border | 80.1 m |
| Colombia — national overview | 2,271.3 m |

The exact final browser report `national-maplibre-browser-qa.json`
and original full-pixel/TileServer GL reports have been saved in the **same
UNPUBLISHED** draft release, together with the three immutable MBTiles
parts. Seven real browser screenshots are available as [successful job
artifact #14151544544](https://github.com/ColombiaTransit/colombia-height/actions/runs/43689989955/artifacts/14151544544)
(retention is temporary).

## Final quality closure decision (15 November 2026)

Both previously open items are now **closed**:

1. Colombia-only OSM / Geofabrik footprint and flat, *non-bathymetric* 0m
   out-of-country background: **accepted by project owner, no blocker**.
2. Negative -239.1m source value: **reproduced from original native Copernicus
   file, independently verified OSM land, and geospatially explained by
   Pribbenow deep open-pit coal mining**. No data mutation, no generator fix
   and no country-wide reprocessing needed.

**Final QA disposition: TECHNICALLY APPROVED FOR NATIONAL MAPLIBRE / TILESERVER
GL TERRAIN USE.** The existing draft is internally validated across all
66,607 factual land tiles, mask provenance, 0–13 TileServer GL HTTP outputs,
and seven national MapLibre 3D scenes.

**Publication control** is distinct from technical quality: the current
GitHub draft remains unpublished and `national_release_authorized=false`
until explicit release publishing is performed. Do not mistake the fact
that mining operations can descend below sea level for bogus sea/bathymetry.

## Important release semantics and visual reservations

1. This is a **Colombia-only 3D visual product**. Inside the audited physical
   OSM Colombian land mask, decoded heights are from original Copernicus
   samples. Sea and foreign/outside-Colombia land use **0 m as rendering-only
   background**, not bathymetry, foreign measured terrain, or analytic data.
   The factual per-pixel Colombian land mask is available in the extra
   `osm_land_mask` SQLite table, not automatically exposed by TileServer GL.
2. **ACCEPTED / CLOSED — country-border background policy.** Visible
   artificial national-border elevation steps can occur, notably near Leticia.
   These follow the deliberately Colombia-only OSM/Geofabrik export footprint
   and the intentionally flat 0m background outside scope. On 15 November
   2026 the project owner explicitly accepted this display limitation as
   **not a blocker**. Do not re-open the border-shape/source-selection research
   and do not silently classify out-of-scope physical land as bathymetry.
3. **ACCEPTED / CLOSED — -239.1 m minimum physically explained.**
   The exact original land-mask pixel is at **9.56427307378, -73.50892066956**,
   tile **z13/x2423/y3877**, row 87, col 67 (MBTiles internal TMS y is
   4314). The original Copernicus DEM cell
   `Copernicus_DSM_COG_10_N09_00_W074_00_DEM` has a native sample of
   **-240.72646 m**. The original rasterio bilinear warp gives
   **-239.11595 m**, and the immutable Terrain-RGB decodes **-239.1 m**;
   all original-land pixels on that tile match source rewarping to **<=0.05 m**.
   The existing original OSMCoastline+Colombia R120027 mask independently
   confirms all 65,536 pixels of that tile are valid country land.
   In the 11x11 *source* pixel window the native Copernicus elevations are
   continuously negative (**-240.7 to -132.4 m**; 121/121 source pixels
   below sea level): a coherent excavated depression, not a PNG encoding glitch.

   The exact low point is **~565 m from the OSM feature centroid** of
   [Mina de carbón Pribbenow](https://mapcarta.com/W98642735), OSM way
   **98642735**, `landuse=quarry`, operated by Drummond Ltd. The
   [operator documents its open-pit Pribbenow/La Loma mine in Cesar](https://drummondltd.com/inventario-de-emisiones-de-gei-2025/).
   A [2015 first-hand mine visit/interview](https://paisminero.com/index.php?Itemid=1203&catid=167&id=15179:pribbenow-la-mina&limitstart=1&option=com_content&view=article)
   explicitly describes a production pit with levels **below sea level**
   and references a working mine level around **-280 m**. The precise
   individual pixel depth is NOT independently surveyed by these sources;
   nevertheless the coherent original Copernicus source data, native
   rewarp, OSM land mask, and known nearby deep open-pit excavation
   explain the negative elevation. This is **not a generator bug** and
   there is **no justification to force it to 0m or rerun the 26 shards**.

   Evidence: [source-localizing GitHub Action #43691933777](https://github.com/ColombiaTransit/colombia-height/actions/runs/43691933777).
   The immutable original draft Release additionally retains
   `original-minimum-height-investigation.json` (exact coordinates,
   nearest COG, source 11x11 patch stats, min 9x9 Terrain-RGB
   neighbourhood, per-zoom negative statistics). The 4.16 GiB original
   MBTiles SHA256 remained unchanged.
4. This document records passing **automated** national checks, not human
   approval to publish. The draft and its three QA JSON reports remain
   unreleased pending human acceptance.

**No Copernicus source archive, native rendering, original OSM inventory, or
successful shard was rebuilt during this QA.**
