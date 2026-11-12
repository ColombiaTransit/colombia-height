# Strict terrain workflow and regional merging

The first Antioquia experiment built Terrain-RGB successfully, but found **26.88%, 10.86%, 4.36%** encoded no-data pixels at zooms 11–13, respectively. These represented missing pixels from the arbitrarily clipped DEM as RGB 0/0/0, which decodes to -10,000 metres and must never be released.

## Tile-aligned test

The [Validate Strict Tile-Aligned Terrain](../.github/workflows/validate-strict-terrain.yml) workflow is manual. It:

1. Runs synthetic unit tests for DEM no-data rejection and tile-grid alignment.
2. Expands the requested Antioquia rectangle to **whole slippy map tile boundaries** at the lowest output zoom level (11).
3. Downloads GLO-30 data covering the extended area (plus two source-pixel widths).
4. Reprojects directly into exact 256×256 Web Mercator tiles (zoom 11–13).
5. **Fails closed** if even one generated tile has missing elevation pixels. It does not publish a partial result.
6. Uploads MBTiles and a JSON report only if all tests pass.

This is intentionally a *strict land-only pilot*. It does not yet solve the coast/ocean problem. A nationwide design requires an explicit ocean/void strategy and coverage checks, rather than misrepresenting missing data as deep trenches.

## Deterministic regional merging

`scripts/merge_regions.py` merges two or more MBTiles with a unique primary key `(zoom_level,tile_column,tile_row)`. It **aborts and removes output** upon discovering a duplicate; it does not silently overwrite one region's elevation with another's.

At national scale, each map tile must have exactly one region owner, at **every zoom**. The initial test jobs overlap geographically by design and **must not be merged** as-is. Region ownership and ocean/void masks still need explicit design and verification.

## Coverage / acceptance gates still pending

- Validate Colombia's mainland **and islands** against a reliable territorial boundary dataset.
- Check source DEM extent and ocean/void conventions against coverage polygons and sample areas.
- Verify adjacent map tile borders using quantitatively comparable heights and visual samples, not only a generous 500 m threshold.
- Plan zoom 0–13 ownership where low zoom tiles span multiple regions (e.g. one global low-zoom job).
- Confirm licences/attribution and test TileServer GL serving raster-dem and its elevation API.
- Decide whether interpolation over small genuine no-data holes is acceptable; never silently fill large missing areas with fabricated heights.
