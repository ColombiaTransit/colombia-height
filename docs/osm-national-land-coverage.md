# Detailed OSM land polygons versus Colombia native DEM NoData

## Dataset and status

This is a **non-publication** quality-assurance comparison using
[OSMCoastline land polygons](https://osmdata.openstreetmap.de/data/land-polygons.html).
Source archive:
[land-polygons-split-4326.zip](https://osmdata.openstreetmap.de/download/land-polygons-split-4326.zip).
**© OpenStreetMap contributors, ODbL 1.0**:
https://www.openstreetmap.org/copyright.
OpenStreetMap is not an official Colombian border, cadastral coastline
or maritime jurisdiction reference. OSMCoastline also repairs some broken
coastlines and may miss small islands or represent incomplete coastlines.

The detailed global split shapefile is large (about 930 MB compressed).
The GitHub workflow downloads it **once**, streams and bounds the size,
retains only polygonal pieces clipped to study longitude -84…-66 and
latitude -5…17, and SHA256-records both the archive and derived clip.
Overlapping split polygon fragments are unioned **locally** per XYZ tile.
The worldwide raw download and temporary clipped geometry are **never
committed to git, uploaded as test artifact or released**.
Any subsequent public reuse of a derived OSM land database must account
for ODbL attribution and applicable share-alike obligations.

## Scope

The [OSM National Land Coverage Validation workflow](../.github/workflows/osm-national-land-coverage.yml)
performs:

1. Full offline unit-test suite and regeneration of the verified
   original **137** selected Copernicus GLO-30 COG inventory.
2. Retrieve exactly the previous **32** provisional land register shard
   artifacts from [national run 43490555676](https://github.com/ColombiaTransit/colombia-height/actions/runs/43490555676).
3. Pilot the 36 zoom-11 tiles around Tumaco, San Andrés, Providencia
   and Malpelo, comparing exact 256×256 original Copernicus native
   missing-height pixels to OSM land, Natural Earth, geoBoundaries,
   and *optional* direct IGAC departmental polygon geometry. If the official IGAC server fails, the OSM analysis continues, **IGAC-dependent counts are recorded as null (unavailable), never zero**, and no resulting source can be classified as proven IGAC land.
4. Re-evaluate **all 1,917** incomplete original zoom-13 tiles and
   independently count the original **1,004** Natural Earth land-gap
   subset; fail if original missing-height counts drift.
5. Cross-index missing pixel centers against all **52** originally
   unselected public Copernicus 1-degree COG squares. Rank each only
   as a **potential source** by exact missing pixels on OSM land and
   independently IGAC administrative land. A COG ID appearing in a
   square does **not** prove that the COG supplies any valid heights.
6. Reconcile all counts and record the results in one-day evidence
   artifacts only, not MBTiles or permanent Releases.

## Strict interpretation

- OSM land geometry may represent other countries and cannot assign
  Colombian sovereignty or automatically approve new COG selection.
- A missing DEM pixel **outside OSM land is unknown**, not proven water.
  It must not be converted to a synthetic zero-elevation ocean.
- A missing DEM pixel inside OSM land is a review candidate, **not
  automatically an accepted Colombian territorial land gap**.
- Official IGAC department polygons are useful but not authoritative
  pixel-precise shorelines. Small islands omitted there, particularly
  Malpelo, are not discarded automatically. DIMAR official marine
  information is a further independent source, not automatically dry land.
- Quitasueño stays excluded from the project; OSM alone cannot override
  this deliberate scope decision.
- The 137 selected source COGs remain unchanged, missing DEM values
  stay missing, source-edge QA remains required after manually approved
  source expansions, and national publication is always forbidden by
  this workflow: `national_publication_allowed=false`.
- Output must include **© OpenStreetMap contributors** and ODbL
  attribution before public distribution.

Final terrain generation must still separately address coastline policy,
real native height recovery, tile completeness, geographic source scope
and seam validation. This study does not produce Terrain-RGB or MBTiles.

## Initial CI finding and service outage

The first successful global OSM download and Colombia bbox clip produced
**4,184 polygon fragments**. Pilot-centre OSM probe points included
Bogotá, San Andrés, Providencia and Malpelo; the approximate Tumaco sample
point was outside OSM mapped land, which is not itself a claim about
Tumaco's built-up area or coast. The pilot then encountered a transient
**HTTP 503** from the official IGAC REST service. The audit now treats
that external reference as optional and preserves unknown IGAC measurements
as **null**, without inferring no land or stopping OSM-only results.
