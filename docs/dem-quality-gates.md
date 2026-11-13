# Source-junction gradient and coastal/island DEM quality gates

[DEM Source Seam and Coast Coverage Quality Gates](../.github/workflows/dem-quality-gates.yml)
audits the Copernicus GLO-30 native DEM values without modifying them.
This is a **research-only** workflow, not a release generator.

## Native COG source seam analysis

At the previously validated four-source intersection (74° W, 6° N),
the workflow samples the parent z10 tile and four child z11 tiles.
Every pixel has a source-provenance index. Adjacent pixel differences
are measured separately in the east–west and north–south directions:

- across **different** source files;
- within the **same** source file (local terrain gradient reference).

The report includes maxima and 95th percentiles across COG boundaries,
95th/99th percentiles inside each source, and counts of cross-source
height gradients greater than 100 metres for investigation. That threshold
is an *audit flag*, not evidence by itself of incorrect elevation.
The earlier 225.375m adjacent-sample difference is explicitly under
investigation. Native samples, slope, source masks, and boundary geometry
must be compared before diagnosing an artificial seam.

## Coast and island coverage

At zoom 11, the workflow samples nine adjacent slippy tiles around each of:
Cartagena, Buenaventura, San Andrés, Providencia, Malpelo, and Tumaco.
Each tile is warped directly from the original Copernicus GeoTIFF files.

For each pixel, compare DEM provenance/validity to independent Natural
Earth 1:10m land and minor-island reference polygons. Record valid and
missing heights inside/outside those polygons, and distinguish complete
tiles from those with DEM gaps.

**Outside Natural Earth land is not automatically ocean**. Elevation
zero in Copernicus is not proof of sea. The reference geometries are not
legal Colombian territory borders, particularly for remote islets.

## Release blockers

The report always records `national_publication_allowed: false`.
This audit alone cannot authorize a national dataset: unexplained
source discontinuities, offshore data masks, official country/island
scope, and full national coverage/partition validation still need
resolution. Missing DEM values must never be encoded as -10000m
or silently set to sea level.

Only the compact JSON report is uploaded as a 1-day temporary artifact.
The source COGs remain local to the ephemeral GitHub runner.
