# Native two-COG Terrain-RGB source/batch seam pilot

This targeted experimental workflow extends the successful
[single-COG inland batch seam pilot](regional-seam-validation.md).
It deliberately renders **two adjacent Copernicus GLO-30 original
GeoTIFFs** around the **-75° longitude** source boundary in Antioquia,
using Web Mercator z11 parent x-columns 596–599 and rows 987–988.

The west batch owns x=596–597 and the east batch x=598–599 at z11.
Children inherit those owners at z12 and z13. There are 168 potential
unique output tiles and 14 cross-batch seam pairs at default z11–13.

## Method and acceptance

- Fetch only the needed Copernicus native COGs (downloads on the temporary
  GitHub Actions runner, never committed or uploaded as artifacts).
- For **each individual 256×256 Web Mercator output tile**, independently
  warp each intersecting original source directly onto the exact destination
  pixel grid with Rasterio/GDAL bilinear resampling. No cropped geographic
  intermediate DEM mosaic is created.
- Treat the source's actual nodata metadata as missing; never convert it
  to -10000m or fill in invented sea-level values. Reject any resulting
  tile with uncovered pixels.
- Keep a provenance index for each output pixel, identifying the COG that
  supplied the elevation. Source ordering is consistent.
- Verify the source transition across -75° occurs inside actual tiles.
  Count adjacent pixels whose source COG changes and report their actual
  elevation gradient **without requiring two distinct points to have equal
  heights**.
- On a re-opened union-area source set, regenerate each pair of tiles
  straddling the **batch boundary** and compare Terrain-RGB decoded heights
  against the source-sampled reference, with **0.16m** acceptance tolerance
  for 0.1m RGB quantization.
- Validate unique MBTiles z/x/TMS-y keys and SQLite integrity after merge.

## Limitations

This exercises a COG boundary *within the west batch* and a nearby
batch boundary. A 1° Copernicus source boundary does not generally coincide
with a Web Mercator slippy tile boundary.

Source border gradients are descriptive quality metrics; a genuine
natural slope or source-data disagreement can exceed 0.16m between
adjacent source pixels, without indicating a raster-pipeline error.
Source overlap is counted separately for later manual review.

The reference is opened independently but uses the same projection
algorithm. This validation does **not** prove the absolute elevation
accuracy of Copernicus data, other 1° source boundaries, national
land/water masks, or shorelines.

The workflow uploads only a short report with one-day retention;
neither the original COGs nor the trial MBTiles are published.
