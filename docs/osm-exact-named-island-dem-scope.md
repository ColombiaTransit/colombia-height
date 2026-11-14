# Exact OSM island polygon / native DEM gap audit

## Purpose

[GitHub Actions: Exact OSM Named-Island Native DEM Scope QA](https://github.com/ColombiaTransit/colombia-height/actions/workflows/osm-named-island-native-scope.yml) tests whether missing native Copernicus GLO-30 pixel centers fall **inside a real OSMCoastline land polygon containing a named island probe**, rather than merely within a 1-degree source cell or near a point.

The six investigated land-probe names are Malpelo, Gorgona, Gorgonilla, San Andrés, Providencia and Santa Catalina. Quitasueño remains deliberately excluded.

## Evidence and methodology

1. Verify the immutable 137-source baseline and load the complete previously audited 1,917 incomplete z13 XYZ tiles from [national OSM audit 43573144549](https://github.com/ColombiaTransit/colombia-height/actions/runs/43573144549).
2. Temporarily download the upstream OSMCoastline split EPSG:4326 land polygons, retain their SHA256 provenance and ODbL attribution, and clip them to the original study rectangle.
3. For each named island, find the **polygon containing its approximate probe point**. If the probe is not in any polygon or the matched polygon is implausibly large for an island, mark it unresolved. Never convert a proximity buffer into land.
4. For z13 tiles intersecting the polygon, compare exact WGS84 XYZ pixel-center coordinates to that polygon and to the **original 137-source native DEM NoData mask**.
5. Report missing island polygon pixels and their intersections with the 52 previously identified unselected Copernicus 1-degree source cells. These are **candidates**, not proof that the extra COG supplies valid elevations.

## Safeguards

- OSM polygons establish an observed land outline, **not Colombian legal jurisdiction**. Administrative boundaries and sovereignty decisions require separate reviewed sources.
- A missing OSM polygon does not prove ocean. No ocean pixels are assigned zero, no bathymetry is fabricated, and no valid native heights are changed.
- The original 137 COGs remain selected; the 52 extras are not automatically promoted. No national Terrain-RGB MBTiles are generated or released.
- Source attribution: © OpenStreetMap contributors, ODbL 1.0; https://www.openstreetmap.org/copyright
- Full per-island pixel counts are emitted only after the workflow passes its native source and reference integrity checks. The GitHub Actions artifact is retained for one day.

## Prior confirmed candidate recovery

- Tumaco `N01_W080`: 460,333 native DEM pixels recovered in the earlier z13 test (not all Colombian land).
- Malpelo `N03_W082`: 145,625 native DEM pixels recovered in the earlier z13 test (island attribution still requires review).
- Gorgona vicinity `N03_W079`: 1,133,187 native DEM pixels recovered in 47 z13 tiles, including all 747 previously missing OSM land pixels in the matching source degree cell; this is not yet a proof of **Gorgona-island-specific** coverage.

The new exact island-polygon check is designed specifically to close the last distinction.

## Completed exact native island recovery — 14 November 2026

[Successful native recovery workflow #43594868906](https://github.com/ColombiaTransit/colombia-height/actions/runs/43594868906) compared exact zoom-13 OSM-island pixel centers before and after temporarily adding one original GLO-30 COG per island:

| Island | Omitted original GLO-30 source | Native DEM missing on island before | Real native pixels recovered | Missing afterwards | Maximum original valid height change |
| --- | --- | ---: | ---: | ---: | ---: |
| Malpelo | `N03_W082` | 97 | **97** | **0** | 0 m |
| Gorgona | `N03_W079` | 86 | **86** | **0** | 0 m |

The original 137-source manifest remains unchanged. This is an in-memory native COG comparison only; no invented elevations, bathymetry, source promotion or national release.

## Corrected Santa Catalina / Gorgonilla probes — 14 November 2026

Earlier approximate sample points were outside their OSM polygon. A separate [successful small-area OSM API coastline / original DEM workflow #43595662069](https://github.com/ColombiaTransit/colombia-height/actions/runs/43595662069) used **closed coastline way rings**, not a geographic buffer, to validate new points:

| Island | Corrected probe (latitude, longitude) | Original native source inventory | z13 tiles with island polygon centers | Real valid native DEM pixel centers | Native DEM NoData on island |
| --- | --- | --- | ---: | ---: | ---: |
| Santa Catalina | 13.38798, -81.37467 | Original 137 COGs | 1 | **3,457** | **0** |
| Gorgonilla | 2.93935, -78.21193 | Original 137 COGs | 2 | **1,657** | **0** |

A CORALINA locality reference also fell inside the same Santa Catalina OSM polygon; a Gorgonilla lighthouse coordinate from DIMAR also fell inside the same Gorgonilla polygon. The confirmed corrected sample points are now included in [the island probe registry](../data/colombia-island-probes.json); the older points and their research provenance are retained in [the correction source file](../data/island-probe-candidate-corrections-2026-11-14.json).

The exact pixel results are permanently recorded in [the island native recovery register](../data/exact-osm-island-native-recovery-2026-11-14.json).

**Interpretation:** The identified four island polygons have no remaining native z13 NoData on their OSM land pixel centers *if* the two tested additional GLO-30 sources are temporarily present. The original 137 manifest, by design, still omits Malpelo and Gorgona's two extra COGs, so their production gaps are not yet fixed. The result does **not** certify Colombian legal jurisdiction, neighboring smaller cays, all zoom levels, DEM source seams or a national Mapbox Terrain-RGB release.

OSM reference attribution: © OpenStreetMap contributors; ODbL 1.0; https://www.openstreetmap.org/copyright.
