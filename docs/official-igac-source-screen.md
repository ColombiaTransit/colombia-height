# Official IGAC geographic screening of omitted Copernicus GLO-30 sources

The successful [national DEM land-reference scan](national-land-results-2026-11-13.md)
classified **96,751** XYZ candidates, including **1,917** incomplete
zoom-13 tiles. Of those, **1,004** contain missing pixels covered by
Natural Earth land polygons, but no missing pixels intersect the
simplified geoBoundaries Colombia ADM0 land mask. This does **not** prove
that Colombian land is fully covered: Natural Earth includes neighboring
countries and geoBoundaries can omit very small islands.

The national source catalog produced **52** additional 1-degree Copernicus
GLO-30 cells near missing pixels, many along borders or open water. Their
mere presence is not reason to alter the approved set of 137 COGs.

## Source used and limitation

This stage uses IGAC's [official Líneas Limítrofes y Entidades
Territoriales](https://mapas2.igac.gov.co/server/rest/services/limites/limites/MapServer)
ArcGIS REST layer **2**, `departamentos` (polygon features). Fetch the
current features with `outSR=4326` and `f=geojson`; fail closed if the
source is unavailable, incomplete, or has a suspicious coordinate system.

The department polygons describe **administrative territorial areas**,
not a certified high-resolution land/sea shoreline. They can include
imprecise coastlines, omit small insular features, or have coarser
boundaries than a z13 Terrain-RGB pixel. Spatial contact is evidence
for further investigation, *not legal approval or proof of genuine
land DEM gaps*. For marine shorelines and small islands, consult the
[DIMAR IDE maritime, fluvial and coastal data portal](https://www.dimar.mil.co/ide)
as a further independent official reference. Never use a national
maritime jurisdiction polygon as a land polygon.

## Workflow

The [Official IGAC National DEM Source Scope Screen](../.github/workflows/official-territory-screen.yml)
consumes **all 32** ephemeral land-register shard artifacts from
[successful run 43490555676](https://github.com/ColombiaTransit/colombia-height/actions/runs/43490555676).
It checks all 3,778 incomplete XYZ IDs, freezes the expected 1,917
incomplete z13 and 1,004 z13 Natural Earth-gap candidates, and identifies
the exact 52 public COG cell candidates.

A 1-degree COG candidate receives one of three strictly **advisory**
classes:

- **A — IGAC administrative polygon and candidate COG cell overlap** in
  a z13 partial tile. Needs a *native DEM missing-pixel recovery* test and
  verified shoreline/territory review before possible inclusion.
- **B — intersects IGAC administrative polygon somewhere in its cell**,
  without a matching z13 incomplete tile/COG-cell intersection. Needs
  closer examination; no automatic addition.
- **C — no overlap with available IGAC department polygons**, which may
  mean foreign territory, offshore area, or islands omitted from that
  layer. It is *not* proof of water or exclusion from Colombia.

For transparency, the output also records each original 1-degree
source bounding box, administrative departments intersected, number
of z13 land-reference-gap tiles that mention the source, and tiles
with IGAC/COG-area overlap. **These are tile/cell intersection counts,
not exact missing-pixel counts, recovered heights, or source eligibility.**
The original pixel-level Copernicus DEM is not downloaded or modified
in this stage.

## Invariants

- The selected manifest remains **137 native GLO-30 COGs**.
- Quitasueño remains excluded, per the project scope; do not infer it
  belongs in the build from mainland or ocean polygons.
- The two separately tested COGs for Tumaco and Malpelo remain
  provisional; their real 3,020 land-reference pixel recoveries were
  independently demonstrated in
  [run 43491477657](https://github.com/ColombiaTransit/colombia-height/actions/runs/43491477657).
- No COGs are silently added to the national source manifest.
- No DEM NoData becomes sea level 0m or fabricated bathymetry.
- No Terrain-RGB MBTiles or permanent Releases are created.
- Explicit release gate: `national_publication_allowed=false`.

**After screening:** identify high-priority z13 areas inside reviewed
Colombian land, distinguish neighboring countries and remote islets,
then test native DEM recovery only for geographically justified source
candidates. Final coast/island policy and DEM edge validation are still
required before publication.
