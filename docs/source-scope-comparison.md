# Targeted omitted-source COG comparison — Tumaco and Malpelo

The successful [four-site land pilot](national-land-coverage.md) detected
missing DEM pixels inside a Natural Earth reference-land polygon at
Tumaco (1,691) and Malpelo (1,329). These are **provisional** land
reference intersections, not a verified territorial finding. It also
identified two public Copernicus source cells missing from the selected
137-source manifest:

- Tumaco: `Copernicus_DSM_COG_10_N01_00_W080_00_DEM`.
- Malpelo: `Copernicus_DSM_COG_10_N03_00_W082_00_DEM`.

This analysis tests whether the *actual original source COG pixels*,
sampled in the same Web Mercator XYZ 256×256 target grid, recover the
missing heights without corrupting or replacing the existing 137-source
elevations. It is not a proposal to fill unknown heights with sea level.

## How to reproduce

[Compare Unselected Copernicus Coastal COGs](../.github/workflows/compare-unselected-coastal-cogs.yml)
is a separate diagnostic workflow. It:

1. Reconstructs the existing 137-source selected manifest and fails
   if its size or source HEAD verification differs.
2. Confirms the two candidate source files are present in the public
   Copernicus catalog and absent from the selected manifest.
3. Opens the original 137 sources plus the two candidates in a temporary
   in-memory selection; it does **not** modify the source CSV.
4. Recomputes the 3×3 zoom-11 neighborhoods at **Tumaco and Malpelo**
   (18 distinct XYZ tiles) twice, first using only selected sources,
   then using selected sources followed by the two extra source COGs.
5. Compares all 65,536 target pixels per tile: recovered valid DEM
   heights, unchanged prior valid heights, residual missing height
   pixels, and recovered pixels intersecting each land-reference
   category. All pixels outside both polygon references remain
   **unknown** rather than automatically "sea".
6. Writes a JSON report with exact per-tile and per-site counts.
   Retention is **one day**. All source DEM downloads remain in the
   ephemeral job filesystem; no source is checked into git.

## Acceptance and limits

- No previously valid height may disappear, and the absolute difference
  for retained valid heights must be no more than **0.001 m**. This is
  a deterministic pixel-reference check, *not* an assertion that
  adjacent natural terrain elevations must agree.
- Recovered pixels must be originally valid native Copernicus height
  values. Classification must reconcile separately for the two
  reference land geometries.
- No tile is published, no missing value is fabricated, no selected
  source inventory is edited, and `national_publication_allowed=false`.
- A source candidate may recover unknown offshore pixels without
  proving missing land coverage; jurisdiction must be reviewed
  separately using official IGAC coastline/island data.
- Only 18 zoom-11 tiles are tested. The full 32-shard land audit
  remains a separate prerequisite for national publication.

The national source selection remains **137 Copernicus COGs**. Any
source expansion requires a separate documented decision backed by
territorial and DEM pixel-coverage evidence.
