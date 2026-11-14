# No-repeat DEM coverage and geographic QA worklist

Updated 14 November 2026. This is the active gate register for the public ColombiaTransit/colombia-height project. It prevents further duplicative national DEM processing.

## Completed: do not repeat without changed native inputs or a demonstrated defect

| Research item | Verified evidence | State |
| --- | --- | --- |
| Original national 137-COG z0–13 coverage | [#43490555676](https://github.com/ColombiaTransit/colombia-height/actions/runs/43490555676) | Completed: 96,751 XYZ tiles, 3,778 incomplete |
| Original native-DEM vs OSM z13 NoData pixel mask | [#43573144549](https://github.com/ColombiaTransit/colombia-height/actions/runs/43573144549) | Completed: 1,917 incomplete z13 tiles, 1,008 with OSM-land missing |
| 52 omitted public COG sources, country/IGAC triage | [#43588621857](https://github.com/ColombiaTransit/colombia-height/actions/runs/43588621857), [#43497166858](https://github.com/ColombiaTransit/colombia-height/actions/runs/43497166858) | Completed advisory register, source-cell contact is not pixel country |
| Tumaco N01 W080 exact native candidate benefit | [#43497684367](https://github.com/ColombiaTransit/colombia-height/actions/runs/43497684367) | Completed: in 24 z13 tiles, 460,333 new genuine DEM samples, including 6,602 in IGAC departmental polygons, all original values unchanged |
| Malpelo/Gorgona exact native island DEM gap recovery | [#43594868906](https://github.com/ColombiaTransit/colombia-height/actions/runs/43594868906) | Completed: 97/97 and 86/86 original OSM island missing samples filled |
| Santa Catalina/Gorgonilla corrected land probes | [#43595662069](https://github.com/ColombiaTransit/colombia-height/actions/runs/43595662069) | Completed: 0 missing z13 island OSM land pixels in 137 COGs |
| Malpelo/Gorgona native source joins | [#43596436204](https://github.com/ColombiaTransit/colombia-height/actions/runs/43596436204), [#43596823989](https://github.com/ColombiaTransit/colombia-height/actions/runs/43596823989) | Completed bounded seam QA; 0 disproportionate 30m border flags in inspected lines |
| Eight minor island Natural Earth candidates | [#43596436204](https://github.com/ColombiaTransit/colombia-height/actions/runs/43596436204) | Completed original DEM mask checks, 11,629 original valid z13 island-polygon pixels; territory reference unverified |
| Exactly 139 staged source inventory, with original precedence | [#43604399337](https://github.com/ColombiaTransit/colombia-height/actions/runs/43604399337) | Completed; original 137 untouched and two supplementary COGs appended after them |
| All-zoom 139-source candidate coverage and z13 OSM land reconciliation | [#43605294875](https://github.com/ColombiaTransit/colombia-height/actions/runs/43605294875) | Completed; 98,152 tiles, 23,878,663 remaining z13 OSM-land NoData samples |
| Missing z13 OSM-land geographical tile-level triage | [#43607959646](https://github.com/ColombiaTransit/colombia-height/actions/runs/43607959646) | Completed. **No DEM or full OSM re-download.** 973 whole tiles inside foreign geoBoundaries reference, 30 partial/mixed-country, 2 no ADM0 land contact |

## Current residual territory status (staged 139)

**23,878,663** z13 samples are inside OSM land and missing the selected DEM. This is a *multi-country* reference region, not confirmed Colombian missing DEM. By **whole tile** ADM0 geometry, **23,419,275** samples in **973 tiles** are within foreign country polygons (geoBoundaries reference only). The remaining **32 tiles** account for **459,388** missing OSM-land samples: 30 mixed-country / coast-border geometry tiles (436,102) and two without country-reference contact (23,286).

Within those 32, **two tiles near Tumaco** contain **7,031** remaining OSM-land NoData pixels, of which **5,865** are *independently known* to lie within official IGAC administrative departmental polygons. The IGAC mask is not a fine-resolution coastline, so the remaining 1,166 OSM-only samples in those two tiles are not legally attributed to Colombia.

For the other **30** ambiguous tiles (452,357 missing OSM-land samples), **no pixels have been positively classified by the historical IGAC mask**. Most are along foreign borders; do not call them Colombian land, landless water, or conclusively foreign at per-pixel resolution. A geoBoundaries whole-tile classification is safe as a reference **screen** but remains non-authoritative.

The exact limited worklist, including all 32 XYZ keys, appears in [the permanent residual-gap priority register](../data/staged139-residual-colombia-qa-priorities-2026-11-14.json).

## Next genuinely new work — in order

1. **Tumaco N01 W080 — DONE for staging:** Native 30m seam was verified in [#43608660364](https://github.com/ColombiaTransit/colombia-height/actions/runs/43608660364) with 350 samples, a 0m edge gap and 0 exceptional flags. A separately gated 140-source CSV passed [#43609451961](https://github.com/ColombiaTransit/colombia-height/actions/runs/43609451961). Its source-local 139→140 all-zoom native DEM and frozen OSM test passed [#43609826904](https://github.com/ColombiaTransit/colombia-height/actions/runs/43609826904) **without national or global OSM reruns**, recovering 460,333 genuine z13 native heights, 130,257 exact OSM-land NoData sample centers on the old scope, and all 5,865 missing IGAC-positive samples. [Permanent results](../data/national-staged-140-tumaco-increment-2026-11-14.json). Do NOT repeat stage/increment or the earlier 24-tile native DEM test.
2. **Next: only unresolved geography.** The original 32 139-stage partial-border/offshore cases are **27 tiles (394,622 OSM-land missing samples)** after targeted Tumaco restoration; all historical known IGAC-positive land gaps in those cases are repaired. [Updated exact residual tile list](../data/staged140-residual-geography-2026-11-14.json). Independently resolve the land classification of **2,688,103 NoData samples on newly added 140-only z13 candidates** with a *small local* reference rather than rerunning nearly 1GB global OSM; sea/country must remain unknown until verified. Do not confuse 27 residual old-scope cases with new 140-only uncertainty.
3. **No more source-list rescan:** Source inventory is **137 original production / 140 separate staging** (Malpelo, Gorgona, Tumaco). Recalculate only genuinely changed source-local grids after an independently approved new COG, never the national 32-shard old baseline, without a material new input or detected defect. The other 49 omitted COGs remain advisory.
4. **Publication policy:** decide how true ocean/NoData pixels are represented *without inventing 0m elevations*, validate the source and Terrain-RGB encoding semantics, coast/islands and all zoom-level national output before generating any national MBTiles release.

## Source ownership and safeguards

- The approved production inventory remains **137 original native Copernicus COGs**; the separately reviewed **139** and latest **140** staging inventories are studies only.
- Never edit an existing valid original source height or infer a land/country from a COG bounding box.
- Quitasueño is explicitly excluded by maintainer decision.
- An unavailable IGAC reference is **null**, not an assumed no-overlap.
- A native original Copernicus height of exactly 0 m is not the same as a synthesized ocean elevation.
- No national release, synthetic ocean, or fabricated bathymetry.
- GIS references used: © OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright; geoBoundaries gbOpen ADM0 (approximate independent boundaries); IGAC administrative polygons, not official shoreline.
