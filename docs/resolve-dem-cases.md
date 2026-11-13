# Two targeted DEM quality investigations

This workflow has **two independent jobs** so that a failure or a blocker in
one case does not prevent the other from producing an evidence report.

## Case 1: Native-height transition at 6° N

Use the original source COGs for the N05/N06 latitude boundary in two
neighboring 1° longitude cells (W075 and W074). Sample 350 longitude
positions per cell and six native pixel rows on each side of the 6°
parallel. Compare the north/south source border pixel-center height
differences to each source's immediate 1–5-pixel interior steps.
Distances are native DEM resolution (~30m), **not z10 tile spacing**.
A border height difference over 40m and over 3× both immediate local
gradients is flagged for investigation, not automatically removed.
No smoothing is performed. Evidence report: `native-seam-report.json`.

## Case 2: Tumaco z11 missing pixels

Repeat the same 3×3 tile audit that previously found **23,384** missing
output pixels. Locate each incomplete tile by XYZ and TMS y, and the
actual bounding box of missing-pixel centers in WGS84. Compare each
pixel to independent Natural Earth land reference. Inspect up to 64
sample points against the native source GeoTIFFs to distinguish absent
source coverage, source NoData, and reprojection gaps. Evidence report:
`tumaco-native-gap-report.json`.

Any output tile with missing data remains excluded: no invented zero
height or -10000m placeholders. Natural Earth is a comparison, not
a sovereignty or water classification.

The workflow only uploads small 1-day JSON artifacts; source COGs
are downloaded to temporary GitHub runners and no MBTiles are released.
