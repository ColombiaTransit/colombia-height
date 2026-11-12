# Antioquia multi-source Terrain-RGB pilot

This manually triggered workflow processes a test region around central Antioquia:
`-76.15, 5.85, -75.00, 7.10` (W,S,E,N). It deliberately crosses
Copernicus 1-degree tile boundaries and generates Mapbox Terrain-RGB
at zoom 11–13. The Medellín point remains a source-vs-RGB control.

Run [Antioquia Terrain RGB Multi-source Pilot](../.github/workflows/antioquia-terrain.yml)
from the Actions tab. This job downloads only intersecting source COGs;
GeoTIFFs remain temporary and are **not** uploaded.

Artifact: `medellin-terrain-rgb.mbtiles` (legacy file name, covering the test
region), and `antioquia-validation.json`. Look at `source_tiles`, `mbtiles_bytes`,
`edge_diagnostics`, and `validation`.

## Limitations and next engineering steps

- This is a *test rectangle*, **not** the administrative department of Antioquia.
- Adjacent tile edge differences are diagnostic, not a definitive seam test:
  real terrain can have sharp gradients.
- Pixels outside the input DEM mosaic are currently encoded as -10000 metres.
  This is not acceptable for a production nationwide DEM: use full Web
  Mercator tile coverage with buffered source reads, masking or other valid
  no-data handling to avoid false trenches at batch boundaries.
- Source coverage of Colombia's islands has not been verified.
- MBTiles regional mosaics must have a unique tile owner at each zoom level.
  A nationwide pipeline needs tile-aligned partitions, stitching safeguards,
  and seam regression tests before publish.
- Copernicus GLO-30 is a DSM. It is not a 30m street-level elevation survey.

This phase establishes CPU, disk, output size and cross-source behavior on
GitHub-hosted runners before building the national dataset.
