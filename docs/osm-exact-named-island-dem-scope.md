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
