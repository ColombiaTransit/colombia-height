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

## Important release semantics and visual reservations

1. This is a **Colombia-only 3D visual product**. Inside the audited physical
   OSM Colombian land mask, decoded heights are from original Copernicus
   samples. Sea and foreign/outside-Colombia land use **0 m as rendering-only
   background**, not bathymetry, foreign measured terrain, or analytic data.
   The factual per-pixel Colombian land mask is available in the extra
   `osm_land_mask` SQLite table, not automatically exposed by TileServer GL.
2. **Visible artificial national-border elevation steps** can occur, notably
   near Leticia. These are inherent to the explicitly chosen country-clipped
   flat-background policy, not a demonstrated native DEM seam. A map designer
   should consider the visual appearance before a public release.
3. The **-239.1 m** observed minimum genuine-land pixel warrants a targeted
   independent geolocation/source sanity check if the dataset will be used
   for altitude analytics. Automated QA cannot identify its cause by minimum
   alone. No new COG download is authorized or needed to inspect its XYZ
   tile coordinate in the already-built MBTiles.
4. This document records passing **automated** national checks, not human
   approval to publish. The draft and its three QA JSON reports remain
   unreleased pending human acceptance.

**No Copernicus source archive, native rendering, original OSM inventory, or
successful shard was rebuilt during this QA.**
