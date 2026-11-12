# Terrain-RGB coastal/island pilot (Cartagena, Buenaventura, San Andrés)

## Experimental workflow

[Coastal and Island Terrain-RGB Pilot](../.github/workflows/coastal-terrain-pilot.yml)
builds three compact, tile-aligned Mapbox Terrain-RGB MBTiles datasets at
zoom levels 11–12. They are **temporary test artifacts**, retained for one
day and not published as releases.

The pipeline:
1. Downloads Copernicus GLO-30 source GeoTIFFs intersecting the *aligned*
   Web Mercator sample region, with a two-native-pixel edge margin.
2. Builds a DEM mosaic and reprojects each map tile individually.
3. Compares every destination pixel against the actual finite/nodata DEM mask.
   The Natural Earth 1:10m Land + Minor Islands mask is computed separately.
4. Records four mutually exclusive classes: valid/missing pixels within the
   reference land polygons, and valid/missing outside those polygons.
5. **Emits PNG Terrain-RGB only if all 65,536 pixels are backed by valid
   Copernicus DEM samples.** Any incomplete map tile is excluded and counted.
6. Keeps real DEM values including real zero heights untouched; no synthetic
   sea-level filling, no RGB 0,0,0 for missing pixels, no interpolation over
   source gaps. Full coverage is required *after* bilinear reprojection.
7. Verifies every emitted PNG, MBTiles SQLite storage and pixel-count totals.

### Important non-goals

- Natural Earth reference-land polygons are not official Colombian boundaries.
  'Outside reference land' is **not** asserted to be ocean.
- A source height of 0 metres is **not** asserted to be water.
- Excluded partial tiles leave missing map coverage and are not ready for
  national publication. The report quantifies how many.
- This pilot does not solve tile seams, water masking or the authoritative
  island coverage validation gate.
- Rasterio bilinear reprojection is not a substitute for source DEM coverage
  or elevation accuracy validation.

If a region has zero complete tiles, the workflow **fails closed** rather
than publishing an empty MBTiles. Reports and MBTiles are temporary artifacts;
the cleanup allowlist includes their name. No source DEMs are uploaded.

Next decision is data-driven: for each coast/island pilot compare emitted
coverage, omitted tile count and locations of missing land and non-land
pixels. Then choose a vetted coastal handling policy and seam tests before
running full country shards.
