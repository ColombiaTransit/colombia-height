# OSM-only Colombian LAND DEM source QA — 14 November 2026

**Decision: geography and source-gap triage completed at z13; Terrain-RGB publication still blocked by coast-tile output encoding and all-zoom QA.**

## Scope: OpenStreetMap physical land only

The project must use **OSM natural=coastline derived land polygons**, intersected with the Colombia **OSM administrative relation 120027**, to decide which terrain pixel centers require elevation. An administrative boundary may include sea, and therefore does not by itself prove physical land. Island labels, COG bounding squares, and 0 m DEM values also do not prove land.

**Sea depth, bathymetry, ocean floor, and missing DEM pixels outside Colombian OSM physical land are explicitly out of scope.** No sea floor elevations may be fabricated or inserted. NoData must never be encoded as an arbitrary 0 m surface or a -10,000 m RGB trench.

## Completed OSM-only evidence, without national native DEM reruns

- [Source-local native 140 Copernicus DEM evidence, run #43609826904](https://github.com/ColombiaTransit/colombia-height/actions/runs/43609826904)
- [Bounded OSM coastline and Colombia boundary study for the 27 + 68 cases, run #43611992754](https://github.com/ColombiaTransit/colombia-height/actions/runs/43611992754)
- [All **997** original-scope OSM-land NoData tiles reconciled against OSM country relation, run #43612505074](https://github.com/ColombiaTransit/colombia-height/actions/runs/43612505074)

| Study | OSM land / Colombia result |
| --- | --- |
| All 997 original-source-area z13 tiles with 23,748,406 verified missing native DEM pixels *on OSM physical land* | All 997 full tile footprints are disjoint from Colombia's OSM relation 120027. Therefore these missing land pixels are outside the Colombia project scope. |
| 67 out of 68 additional Tumaco z13 incomplete tiles | Whole tile disjoint from OSM Colombia. Together 2,656,871 missing native DEM pixels, also outside project scope. |
| One new Tumaco tile at z13/x2297/y4050 | The tile partially contacts OSM Colombia's **administrative** relation. It contains 31,232 missing native samples. The **bounded OSM coastline query detected no coastline, closed CCW land/islet polygon, or OSM island-area hint in this tile.** Missing pixels on physical Colombian OSM land are *not demonstrated*; do not claim these 31,232 are sea depths or definitely ocean. |

**Finding:** Zero **confirmed missing physical Colombian OSM land height pixels** remain in the audited z13 source-gap inventory. The single offshore tile can be kept as a narrow OSM-geography monitoring/geometry limitation, not a new COG search or a blocker due to sea depths.

Country context came from the OSM Colombia admin_level=2 [relation 120027](https://www.openstreetmap.org/relation/120027), fetched via the OSM Nominatim polygon lookup. Offshore coast/island geography came from one restricted OSM Overpass query near Tumaco (not the global OSM coastline archive). The local query returned 31 coastlines and 28 named-island polygon hints in its broader bounding box, but none intersected the one partially administrative-boundary-contacted tile.

## Runtime contract for a future land-only MBTiles generator

1. Build a pixel-accurate boolean *physical land* mask from OSM coastline polygons. Intersect with the OSM Colombia administrative relation. Neither mask alone is sufficient to establish required height.
2. **If a tile has no Colombian OSM land pixel, do not export that tile**. No ocean/bathymetry tile is needed.
3. **If any required land pixel lacks a genuine native Copernicus elevation, fail closed**. Do not fill with zero, bathymetry or neighboring values.
4. For **mixed coast + land** tiles, do not invent heights for the outside-land pixels. Explicitly validate transparent/masked PNG raster-dem handling in MapLibre and TileServer GL before publishing. Alpha alone must not be assumed safe.
5. Verify source preservation, all zooms, island continuity, tile borders and the final MBTiles output. Existing strict terrain code handles NoData only by rejecting *any* missing pixel, so a countrywide land-only output encoder still needs an independent implementation/test.

A standalone implementation of the source validity contract is in [scripts/osm_land_only_dem_policy.py](../scripts/osm_land_only_dem_policy.py), with [unit tests](../tests/test_osm_land_only_dem_policy.py).

## No-repeat policy

The source selection remains **137 original immutable public GLO-30 COGs** and **140 total separately staged** (Malpelo, Gorgona, Tumaco). Do **not** rerun the original 32 nationwide shards, the 139/140 full source mask audits, 52 candidate-source triage, island-native source comparisons, 24-tile Tumaco test, or the worldwide OSMCoastline archive unless the underlying data materially changes. The remaining work is **terrain-rgb rendering/validation of only Colombian OSM land**, not more coastline inventory or bathymetric research.

[Permanent machine-readable OSM-only result](../data/osm-only-land-source-qa-conclusion-2026-11-14.json). [Central work plan](dem-qa-no-repeat-workplan.md).

**Release status:** No national MBTiles / Terrain-RGB release approved yet.

OSM attribution: © OpenStreetMap contributors; ODbL 1.0; https://www.openstreetmap.org/copyright. Copernicus DEM DSM attribution also applies.
