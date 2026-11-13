# Regional Terrain-RGB seam and batch validation — Antioquia

The [Regional Terrain-RGB Seam and Batch Validation](../.github/workflows/regional-seam-validation.yml)
workflow creates **two independently rendered, adjacent** Antioquia MBTiles
batches. Each batch owns 2 × 2 Web Mercator z11 parent tiles; their
z12/z13 descendants remain exclusively owned by that batch. The area
covers 4 × 2 z11 tiles near Medellín (z11 x=593..596, y=987..988).

At zoom 11–13 the validation expects **168** distinct tiles: 8 z11,
32 z12 and 128 z13; there are 2, 4 and 8 cross-batch vertical seam
pairs respectively (14 in total).

## Previous failure and fix

Two runs failed the first seam: [43232358338](https://github.com/ColombiaTransit/colombia-height/actions/runs/43232358338)
and [43376364793](https://github.com/ColombiaTransit/colombia-height/actions/runs/43376364793).
Both reported a maximum error of **0.906 metres** at z11/594/987 ->
z11/595/987 (strict acceptance <= 0.16 metres).
The second run used identical output dimensions for its reference
but still failed, so resizing the comparison window was not a fix.

The previous method used `rasterio.merge` to crop and resample the
same source COG into **different intermediate geographic DEM rasters**
for west, east and reference extents. Differences can arise in the
intermediate merge/resampling phase, making this insufficiently
reproducible for shard-edge validation.

The current single-COG pilot therefore opens the original Copernicus
COG *unchanged*, reads its original native raster samples and affine
transform, and warps each slippy tile directly from that native grid.
Each batch is still rendered independently. The seam reference re-reads
the original source independently and renders on the exact same
256 x 256 Web Mercator pixel grids as each batch.

## Acceptance checks

- Exactly one original Copernicus DEM source COG must cover this pilot
  area; the test intentionally **fails closed** when multiple COGs are
  involved. Native-grid multi-COG stitching is a separate follow-up.
- Every generated tile must have full DEM coverage. Missing DEM pixels
  are never turned into fake -10,000m heights or filled with sea level.
- Two independent MBTiles batches merge without duplicate z/x/TMS-y
  coordinates; the SQLite database passes its integrity check.
- Each Terrain-RGB tile adjacent to the batch boundary decodes to
  heights within **0.16m** of the separately rendered native COG
  reference, accounting for RGB 0.1m quantization and float precision.
- Pixel-to-pixel terrain gradient *across* adjacent slippy tiles is
  separately reported. Real slopes are not required to have zero
  height difference between neighboring pixels.
- Full regression tests include a synthetic one-COG native-grid
  reproducibility check and a guard against unsupported multi-COG input.

Only the compact JSON summary is uploaded as a **temporary one-day
artifact**. Experiment MBTiles and COGs are deleted with the runner.
No permanent terrain release is created.

## Remaining release gates

1. Confirm this revised single-COG pilot passes a new Action run. The
   earlier 0.906m issue is not considered resolved without that run.
2. Independently test adjoining batches whose source COGs differ, with
   an explicitly common native sampling grid at source boundaries.
3. Repeat across actual coastlines and islands, verifying the water
   policy and full native DEM data masks, not just available filenames.
4. Estimate national build size/time, guard shard ownership and avoid
   artificial height trenches before any public release.
