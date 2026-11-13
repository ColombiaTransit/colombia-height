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


## Measured results — successful run 43491477657 (13 November 2026)

[Actions report](https://github.com/ColombiaTransit/colombia-height/actions/runs/43491477657)
confirmed the 18-tile native source comparison. Recovered reference-land
pixels are counted using the provisional combined reference, not a
certified Colombian territory mask.

| Native-source metric | Tumaco (9 z11 tiles) | Malpelo (9 z11 tiles) |
| --- | ---: | ---: |
| Baseline missing DEM pixels | 113,664 | 348,672 |
| Actual source pixels recovered with the single local extra COG | 90,280 | 348,672 |
| Recovered provisional reference-land pixels | 1,691 | 1,329 |
| Remaining missing provisional land pixels | **0** | **0** |
| Remaining missing pixels outside both reference land polygons | **23,384** | **0** |
| Tiles with recovered DEM pixels | 3 | 6 |

**Result:** Both source candidates eliminate *all 3,020* missing pixels
inside the provisional land references at the two test sites, while
preserving every previously valid DEM height within 0.001m.
The 23,384 Tumaco residual pixels are outside *both* reference polygons,
but **cannot be declared open sea without a separate official coastline
review**. This is not a reason to fill them with a synthetic 0m.

**Recommendation:** Promote the two source candidates to *reviewed
provisional land-coverage fixes*, but **do not modify** the 137-source
manifest or change the national build/release gate until the official
IGAC/DIMAR island-and-coast geometry and nationwide 32-shard land report
have been reviewed. Preserve the selected-vs-augmented native-pixel
comparison as reproducible evidence.


## Official cartographic gate: IGAC versus DIMAR

Before accepting the two new COGs into national input, compare the
recovered land-reference footprint with:

- [IGAC: Líneas Limítrofes y Entidades Territoriales](https://mapas2.igac.gov.co/server/rest/services/limites/limites/MapServer)
  (official administrative/territorial lines and departments, **not**
  automatically an exact pixel-scale shoreline or bathymetry mask).
- [Colombia en Mapas: instructions to download official boundary datasets](https://www.colombiaenmapas.gov.co/colombia-mapas/preguntas-frecuentes-faq/index.html)
  (lists GeoJSON, GeoPackage, shapefile and geodatabase).
- [DIMAR geospatial data infrastructure](https://www.dimar.mil.co/node/5834)
  (marine/coastal datasets; inspect provenance, coverage and licensing).
- [DIMAR / CECOLDO data access](https://cecoldo.dimar.mil.co/web/solicitudes)
  (open/downloadable datasets first; request access if necessary).

Do not rasterize *administrative boundary lines* as though they were a
validated coastline. A verified coastline requires shoreline polygons,
island coverage, datum/scale, and information on any maritime boundary.
At zoom 11 especially, a missing height outside the reference polygon
must remain unresolved until coastal evidence justifies treating the
pixel differently. Even after the scope decision, a missing source value
must not be replaced by an invented bathymetric depth.
