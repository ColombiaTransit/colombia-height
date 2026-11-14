# OSM / IGAC / neighboring-country source triage — 14 November 2026

## Source evidence

[Successful triage #43588621857](https://github.com/ColombiaTransit/colombia-height/actions/runs/43588621857)
reused the fully audited [OSM national zoom-13 report #43573144549](https://github.com/ColombiaTransit/colombia-height/actions/runs/43573144549)
and [actual native GLO-30 recovery #43497684367](https://github.com/ColombiaTransit/colombia-height/actions/runs/43497684367).

The check evaluated all **52** unselected public Copernicus COG cells and all
**1,917** incompletely covered baseline zoom-13 XYZ tiles, including **1,008**
with missing native DEM samples inside OSMCoastline land reference polygons.

It also downloaded geoBoundaries **gbOpen ADM0** context polygons for the
neighboring land and sea region: VEN, BRA, PER, ECU, PAN, NIC, CRI and HND.
All eight were available in this run. These are independent **non-authoritative
national boundary references**; overlap percentages refer to a 1-degree
COG cell or XYZ tile **area**, NOT verified missing DEM pixel membership
or a Colombian sovereignty decision.

The exact per-source evidence is retained permanently in
[the 52-source review register](../data/osm-territorial-source-review-2026-11-14.json).

## Outcome

| Evidence class | COG candidates | Meaning |
| --- | ---: | --- |
| OSM land + direct official IGAC department + already tested real native recovery | **1** | Tumaco (N01 W080) |
| Existing native DEM recovery for the named Malpelo island vicinity | **1** | Malpelo (N03 W082); the IGAC departmental mask does not contain its island land in this study |
| Near a named island study probe, without native recovery test at this stage | **1** | N03 W079 near Gorgona, candidate source investigation only |
| 1-degree source cell predominantly overlaps a foreign administrative polygon | **30** | Likely foreign-land OSM observations; **not automatically rejected** |
| Source cell has partial foreign ADM0 contact | **9** | Border/mixed-country investigation still needed |
| No missing OSM land pixels among the examined z13 candidate tiles | **10** | No demonstrated OSM land coverage benefit in this **bounded z13 baseline**; no general ocean or source exclusion |

The **1,917** tiles break down into **981** foreign-polygon-dominant
context tiles, **20** with some foreign boundary contact, **909** without
missing OSM land pixels, **3** with nearby island probes and missing OSM
land reference, **2** with jointly OSM/IGAC missing pixels, and **2**
remaining without a settled geographic reference. These categories are
advisory, based on tile geographic contact and conservative priority, not
a definitive national land-mask classification.

## Concrete source candidates

- `Copernicus_DSM_COG_10_N01_00_W080_00_DEM` (Tumaco). The original z13 OSM
  audit attributes **130,336** missing DEM pixel centers to OSM land inside
  this COG cell, of which **5,865** also intersect the direct official IGAC
  administrative polygon. A separate earlier native recovery test **proved
  460,333 real restored original DEM pixels** in its 24 test tiles, preserving
  all existing valid heights. That larger number is **not** a declaration
  that all pixels are Colombian land.
- `Copernicus_DSM_COG_10_N03_00_W082_00_DEM` (Malpelo vicinity). The OSM z13
  audit found **354** missing OSM-reference land samples in its candidate
  source cell. Earlier actual original native DEM tests restored **145,625**
  pixels in 23 z13 tiles, but the IGAC administrative land reference omits
  this island here. The island's geography must be confirmed separately.
- `Copernicus_DSM_COG_10_N03_00_W079_00_DEM` (near Gorgona). **747** missing
  native DEM pixels on OSM land in the relevant degree cell. The named island
  probe is near the cell boundary, not an exact territorial polygon. Run the
  [targeted native source test](../.github/workflows/gorgona-edge-native-qa.yml)
  before any source decision.

## Required safeguards and next work

1. **Do not add or exclude a COG automatically from the 1-degree or tile
   border overlap classification.** Countries, coastlines, and island
   polygons are different types of geography.
2. Keep a separate **named-island review** (Gorgona, Malpelo, San Andrés,
   Providencia and smaller cays). Island point proximity can select a
   *research target*, never a certified land pixel.
3. Use native height recovery tests on the few plausible Colombian
   sources. A COG's presence in a public catalog and the matching
   reference-land NoData count are insufficient for source approval.
4. After manual scope review, validate the whole newly selected source
   set against coastline and seam quality gates; only then consider
   national Terrain-RGB MBTiles production.
5. Preserve OSM ODbL attribution: © OpenStreetMap contributors —
   https://www.openstreetmap.org/copyright. Additional geoBoundaries
   attribution/license data are retained in each ephemeral triage report.

**The selected baseline still contains exactly 137 COGs.** No missing DEM
height has been replaced with artificial 0m or bathymetry. Quitasueño
remains explicitly excluded. `national_publication_allowed=false`.
