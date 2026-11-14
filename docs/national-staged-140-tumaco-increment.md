# Tumaco: incremental native GLO-30 staging source 139 → 140

**Date:** 14 November 2026  
**Status:** complete staging-only QA, **no national Terrain-RGB release**.

## Verified runs

- [Successful separate 140-source staging #43609451961](https://github.com/ColombiaTransit/colombia-height/actions/runs/43609451961)
- [Successful **incremental only** 139 → 140 native DEM and frozen OSM comparison #43609826904](https://github.com/ColombiaTransit/colombia-height/actions/runs/43609826904)
- [Earlier successful exact Tumaco native GLO-30 source recovery #43497684367](https://github.com/ColombiaTransit/colombia-height/actions/runs/43497684367)
- [Earlier successful original 30 m native 79° W source edge #43608660364](https://github.com/ColombiaTransit/colombia-height/actions/runs/43608660364)
- [Permanent machine-readable 140-source incremental result](../data/national-staged-140-tumaco-increment-2026-11-14.json)
- [Updated 27 ambiguous geographic source tiles](../data/staged140-residual-geography-2026-11-14.json)

## Source and reproducibility

The 137 verified original selected Copernicus source COGs are untouched. The two already staged Malpelo and Gorgona COGs retain their source priority. Only the source `Copernicus_DSM_COG_10_N01_00_W080_00_DEM` at Tumaco is appended as the 140th source in a **separate staging CSV**.

The 140-stage workflow **reused** the successful 139-source staging artifact rather than rebuilding national source inventory or changing production settings. The 139 → 140 audit reused the successful 139-source countrywide all-zoom aggregate and frozen z13 OSM pixel counts. Only **811** native XYZ tiles overlapping the additional Tumaco source's footprint were evaluated, from zoom 0 through 13. At low zoom, physically local original COGs suffice to measure the pixel recovery; at high zoom, all original sources intersecting each changed tile are used to validate exact full/partial coverage. Previous heights are preserved to within 0.001 m, with no artificial ocean fill.

**Zero repeated national source-shard runs, zero new OSMCoastline global downloads, zero repeated original Tumaco 24-tile audit.**

## National source-based XYZ candidate coverage, zoom 0–13

| Metric | 139-source island staging | 140-source staging including Tumaco |
| --- | ---: | ---: |
| Candidate XYZ tiles z0–z13 | 98,152 | **98,904** |
| Full native DEM coverage | 94,288 | **94,950** |
| Partial native DEM coverage | 3,864 | **3,954** |
| Added source-footprint tile candidates | — | **752** |
| Actual overlapping tiles re-warped with source pixels | — | **811** |

The larger partial count is caused by expanded source-cell geographic scope. **No previously valid original DEM heights were lost.**

## Native zoom-13 source recovery and land-reference effect

| Metric | Before (139 sources) | After (140 sources) |
| --- | ---: | ---: |
| z13 candidate tiles | 73,166 | **73,718** |
| Fully covered z13 tiles | 71,203 | **71,709** |
| Partially covered z13 tiles | 1,963 | **2,009** |
| Original 139-scope z13 partial tiles made full by Tumaco | — | **22** |
| Original 139-scope z13 NoData samples filled with genuine GLO-30 elevations | — | **460,333** |

The already validated original 24-tile Tumaco native-restoration count matches the newly audited 139 → 140 recovery exactly at z13: **460,333** real original Copernicus elevations. In **two** known positive IGAC departmental z13 tiles, the original **5,865** missing OSM+IGAC pixels are now fully recovered; these are within administrative polygons, not official pixel-accurate coastlines.

Using the previously frozen **actual z13 OSM-land pixel counts**, the 140-source addition fixes **130,257** missing OSM-land sample centers in the **existing 139-source candidate area**. This is exact: lower and upper mathematically possible recovered OSM land pixels both equal 130,257.

- 139 reference-scope OSM land missing: **23,878,663**.
- 140 result *on that same fixed reference scope*: **23,748,406** missing OSM-land pixels.
- Original 139-scope tiles with missing OSM land: **1,005 → 997**.
- The 140-only study includes **552 new z13 tile candidates**, of which **68** are incomplete. Their missing native DEM samples total **2,688,103**. The OSM-land/water status of those samples is still **UNKNOWN** because they were not in the frozen 137/139 land-reference audit. Do not claim this number is missing Colombian terrain or ocean.
- Thus the 140 source scope *as a whole* has a **rigorous range** of **23,748,406 to 26,436,509** missing OSM-land pixels, until a local reference of the newly added region is checked. The lower bound is **not** a newly observed complete-national-land count.

The 32 preexisting *border/offshore* land-reference case tiles from the earlier 139 screening reduce to **27**; the 140 source has repaired 64,766 OSM-land missing pixels within five of those tiles. The 27 retained ambiguous tiles contain **394,622** missing OSM land sample centers (historical **IGAC-positive missing = 0**). They are not assigned to Colombia automatically. Foreign whole-tile reference areas are not per-pixel sovereign borders.

## Do NOT duplicate work

The earlier 137-source national 32-shard DEM source scan, 137-source OSM/IGAC mask, 139-source countrywide update, eight-island source review, Malpelo/Gorgona native source joins, and Tumaco's 24 original z13 tiles and native 79° W seam were all completed. **None must be rerun merely to add Tumaco to staging.**

Next release blockers:

1. Narrow geographical audit only for actual missing pixels in **new 140-only Tumaco candidate tiles** and the **27 unresolved previously known border/offshore reference tiles**. It must not mistake sea, Colombian territorial water, a COG 1° bounding cell, or foreign administrative overlap for proven Colombian *land*.
2. Confirm the required treatment of genuine missing land and water pixels for the intended national Terrain-RGB encoding, retaining original Copernicus source values and explicit NoData rather than fabricating zero ocean heights.
3. Do not automatically select the remaining **49** omitted public COG candidates. No national MBTiles or Terrain-RGB release until all independent scope and output-quality gates are resolved.

© OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright. geoBoundaries gbOpen country outlines are *non-authoritative reference* layers; IGAC department polygons are official administrative boundaries but not certified high-resolution shorelines.
