# ColombiaTerrain v1.0.0 — data attribution and scope

This dataset is a **modified, combined product**, not a claim of ownership
over original Copernicus or OpenStreetMap data.

## Copernicus GLO-30 DEM

The ColombiaTerrain Raster DEM was produced using Copernicus WorldDEM-30.
When redistributing this dataset or displaying derived results, retain
the official attribution for an **adapted product**:

> produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus
> Defence and Space GmbH 2014-2018 provided under COPERNICUS by the
> European Union and ESA; all rights reserved.

Source and data licensing: https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM

Copernicus DEM GLO-30 is a digital surface/elevation model; users must not
assume it represents a professionally surveyed bare-earth DTM. Reprojection,
bilinear sampling and Mapbox Terrain-RGB encoding are modifications.

## OpenStreetMap / OSMCoastline

The Colombia-only physical land mask is derived from OSMCoastline land
polygons and the Colombia administrative OSM relation **R120027**.

> © OpenStreetMap contributors, Open Database License (ODbL) 1.0.

https://www.openstreetmap.org/copyright

https://opendatacommons.org/licenses/odbl/1-0/

The accompanying per-pixel `osm_land_mask` table preserves the factual
land-vs-background distinction and attribution. Downstream users remain
responsible for the ODbL requirements applicable to the OSM-derived data.
The project does not replace or waive either original licence.

## Coverage, provenance and caveats

- Geography: Colombia-only OSM land, including supported islands.
- Altitude values on factual Colombian land: original Copernicus GLO-30
  reprojected and encoded as Mapbox Terrain-RGB 256px PNG.
- Ocean and **outside-Colombia physical land**: *zero-meter visualization
  background only*. This is NOT ocean depth, actual foreign land elevation,
  analytic elevation, or bathymetry.
- The per-pixel OSM land provenance is available in the MBTiles
  `osm_land_mask` SQLite table (grayscale PNG, 255=Colombian land,
  0=outside country scope).
- Elevation queries used for analytical purposes MUST test this land mask
  before returning height values to users.
- Dataset native GLO-30 DEM ~30-meter source resolution; the delivery
  format is an XYZ/MBTiles pyramid from zoom 0 through zoom 13.
  It does not imply 30-meter pixels at every zoom.
- Negative elevations in mining excavations are real original source
  values, including the verified −239.1 m Pribbenow case.
- The full original MBTiles and all native tile rows are backed by SHA-256
  and national QA: https://github.com/ColombiaTransit/colombia-height/blob/main/docs/national-terrain-QA-2026-11-15.md

Neither the European Union, ESA, Airbus, DLR, OpenStreetMap Foundation nor
any contributor endorses this derived product or its particular land
clipping decisions.
