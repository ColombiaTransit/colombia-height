# Colombia coastline and islands — DEM coverage audit

## Purpose

A successful inland Terrain-RGB test does **not** establish that the Copernicus
GLO-30 data cover the sea, offshore islands or coastal lowlands. This is a
source-data audit: **do not publish any new Terrain-RGB tiles yet**.

The manual [Audit Colombia Coast and Islands](../.github/workflows/coast-islands-audit.yml)
workflow samples seven representative windows:

| Region | Kind | Location |
| --- | --- | --- |
| Cartagena | Caribbean coast | Bolívar |
| Barranquilla | Caribbean coast | Atlántico |
| Buenaventura | Pacific coast | Valle del Cauca |
| Tumaco | Pacific coast | Nariño |
| San Andrés | Island | Archipelago |
| Providencia | Island | Archipelago |
| Malpelo | Small remote island | Pacific Ocean |

It fetches the public Copernicus source index and any intersecting GeoTIFFs,
then compares a **coarse ~185 m grid of valid/invalid DEM pixels** against
geoBoundaries Colombia ADM0. Individual independent points are sampled at
native resolution to check island landmarks.

The artifact `coastal-island-audit.json` reports:

- Source availability and missing geographic 1-degree cells by region
- Valid and missing DEM grid samples within and outside the Colombia polygon
- Sampled heights for identified test points, or explicit source/nodata statuses
- Data provenance and limitations

**Limitations:**

- A point outside the Colombia boundary may be another country, sea, or an
  excluded/missing island. It must not be assumed to be ocean.
- Zero metres in a DEM is a plausible valid height, **not proof of sea water**.
- A valid point on an island does not prove complete island coverage.
- The ~185 m audit grid can miss very small islands such as Malpelo. The native
  point probes help detect these but do not supersede a polygon audit.
- The windows are samples, not the full national coastline.
- Missing DEM pixels must **never** be replaced with -10,000m (Terrain-RGB
  RGB 0,0,0) or indiscriminately filled with 0m.

## Proposed treatment of ocean and data voids

1. Keep native DEM validity separate from a vetted land/water polygon mask.
2. Report missing DEM over land as **data gaps**, requiring explicit decisions
   or alternative source data, rather than fabricating terrain.
3. For confirmed ocean, choose either **no terrain tile** for a fully ocean
   map tile, or a documented sea-level policy with independent water geometry.
4. At coastline tiles, use a consistent independently validated land/sea mask
   with careful boundary sampling, then test elevation continuity and artifacts
   in MapLibre 3D.
5. Validate mainland and island coverage, especially San Andrés, Providencia
   and Malpelo, before production release.
6. Build globally unique z/x/y ownership across batches for zoom 0–13.

**Current status:** coastal/island policy remains unimplemented. The audit
produces evidence; it does not declare the source data complete or modify
existing experimental MBTiles.

## Run

Actions → Audit Colombia Coast and Islands → Run workflow → `region=all`.

Single-region execution is also supported to debug or rerun one problematic
location without re-downloading the other six. Attach or review the emitted
`coastal-island-audit.json` for the next design decision.
