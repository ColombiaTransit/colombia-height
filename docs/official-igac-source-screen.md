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


## Verified geometric results — 13 November 2026

[Run #43497166858](https://github.com/ColombiaTransit/colombia-height/actions/runs/43497166858)
**passed** using the *direct official IGAC MapServer*; it returned 33
departmental polygons. The original unpaginated service query failed
HTTP 500 in [run #43496738265](https://github.com/ColombiaTransit/colombia-height/actions/runs/43496738265);
the corrected direct-source request succeeded, **without invoking the
explicitly unverified fallback**.

| Evidence | Verified result |
| --- | ---: |
| Additional source COG candidates | 52 |
| z13 tiles with incomplete native DEM | 1,917 |
| z13 tiles with Natural Earth-only missing land reference pixels | 1,004 |
| Such z13 tiles intersecting an official IGAC department polygon somewhere | **2** |
| Public COGs with an IGAC polygon AND overlapping missing z13 tile/cell area (tier A) | **1** |
| Public COGs without qualifying IGAC department polygon contact (tier C) | **51** |

**The sole tier A source:**
`Copernicus_DSM_COG_10_N01_00_W080_00_DEM`, cell lon -80…-79,
lat 1…2. Its administrative contact is **Nariño**. There are 24
incomplete z13 tile source hints for this COG, eight with
Natural Earth-only missing pixels, and only **two** with both an
IGAC administrative polygon and the COG cell in the tile area.
These are geographic intersections, **not proven missing land DEM pixels**.

The Malpelo source
`Copernicus_DSM_COG_10_N03_00_W082_00_DEM` was classified tier C
because the official departmental polygons do not capture that
island in this screening. However, an independent native-COG
[run #43491477657](https://github.com/ColombiaTransit/colombia-height/actions/runs/43491477657)
**verified real recovery** of its provisional missing island heights.
**Do not discard Malpelo or any tiny island solely because it is not
present in the IGAC administrative department geometry.**

Other tier C candidates should be distinguished as likely outside
Colombia mainland, coastline, or potentially omitted small islands
using independent official DIMAR coastline/island layers before any
final exclusion. No source is approved or added by this screen.

The next experiment is the
[exact z13 original-pixel recovery diagnostic](../.github/workflows/igac-native-z13.yml):
check Tumaco and Malpelo under both official IGAC administrative
polygons and Natural Earth island references, preserving every
existing DEM sample and all remaining NoData masks.


## Exact original z13 DEM pixel recovery — successful run 43497684367

[Native z13 IGAC recovery workflow](https://github.com/ColombiaTransit/colombia-height/actions/runs/43497684367)
**passed**. It reopened selected native Copernicus COGs and recomputed
the same 256×256 Web Mercator tiles with the two extra original COGs
temporarily appended. All previous valid height samples were
preserved within 0.001m; nothing was filled with 0m or a synthetic depth.

| Result | Tumaco / N01_W080 | Malpelo / N03_W082 |
| --- | ---: | ---: |
| Incomplete z13 tiles sampled | 24 | 23 |
| Missing native DEM pixels, before | 485,376 | 161,753 |
| Real original Copernicus heights recovered | **460,333** | **145,625** |
| Recovered pixels inside IGAC administrative polygons | **6,602** | **0** |
| Missing pixels remaining inside IGAC administrative polygons | **0** | **0** |
| Recovered pixels in Natural Earth land but outside IGAC | 99,151 | 0 |
| Remaining missing DEM pixels, total | **25,043** | **16,128** |

**Tumaco:** real native source data repaired all **6,602** missing
height samples intersecting the IGAC department polygon in these 24
z13 tiles. The source therefore has independently verified
administrative-land pixel value, but the remaining nodata must not
be declared sea or replaced with fictitious zero elevations.

**Malpelo:** 145,625 native heights were recovered in the targeted
23 z13 candidate tiles, but none of those recovered pixels were
classified by the official IGAC *administrative* polygons or the
Natural Earth land reference at **this specific zoom/selection**.
This does not contradict the earlier z11 island audit showing
1,329 missing Natural Earth island-reference pixels recovered.
It illustrates why remote islets and high-zoom source masks require
separate geographical and multi-zoom validation.

Both remain **provisional**; unchanged 137-source production manifest,
no MBTiles publication. The durable machine-readable decisions and
the complete 52-COG candidate ID list are retained in
[the official source review register](../data/official-igac-source-review-2026-11-13.json).

**Remaining gate:** obtain a trustworthy *land* polygon and shoreline
reference from the appropriate DIMAR/IGAC open datasets covering
coasts, Malpelo and outlying Colombian islands; then evaluate only
geographically relevant sources. An administrative boundary layer
cannot classify all ocean pixels or automatically eliminate the
51 remaining COG candidates.
