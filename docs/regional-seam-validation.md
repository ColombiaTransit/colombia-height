# Regional batch and seam validation — Antioquia

The [Regional Terrain-RGB Seam and Batch Validation](../.github/workflows/regional-seam-validation.yml)
workflow creates **two independently mosaicked, adjacent** experimental
Antioquia MBTiles batches in one ephemeral GitHub Actions runner.

Each batch owns 2 × 2 full Web Mercator z11 parent tiles; their z12/z13
descendants remain exclusively owned by that batch. The combined sample
covers 4 × 2 z11 tiles near Medellín (z11 x=593..596, y=987..988).

At the default zoom range 11–13 this exercises **168** tiles across the
two batches (8 z11, 32 z12, 128 z13), including a 2-tile, 4-tile and
8-tile shared vertical seam at each zoom.

## Controls

- Independent source mosaics: each region has its own tile-aligned DEM
  processing extent; source downloads are cached only on the local runner.
- Both mosaics are snapped to a global 1-arcsecond geographic sample grid.
  Different grid origins can create artificial cross-batch resampling seams.
- Any incomplete Copernicus source pixel fails immediately; no fabricated
  sea level or -10,000m values can be encoded.
- Merge uses SQLite z/x/TMS-y primary keys; duplicate ownership is an error.
- A *third, independent union-area reference mosaic* renders each shared
  tile pair as one 512 × 256 output. The generated batch tiles are decoded
  from Terrain-RGB and compared pixel-for-pixel to the reference, with a
  0.16m limit allowing 0.1m encoding quantization and floating-point jitter.
- Natural terrain gradients across the two adjacent pixel centers are
  reported separately; they are **not** required to equal zero.
- The resulting MBTiles must pass SQLite integrity and exact tile counts.

Only the compact JSON report is uploaded as a temporary one-day artifact.
The experimental MBTiles and source GeoTIFFs are deleted with the runner
after completion; permanent releases are not created.

## Current limits

This is an *inland* seam/ownership test, not a countrywide test. It does not
prove native coastal DEM coverage, sea treatment or official island geometry.
The same global grid and independent-reference validation must eventually
be applied to coastal/island batches before national publication.
