# Colombia Height

Reproducible inventory and preparation of **Copernicus DEM GLO-30** elevation data for Colombia, intended for self-hosted terrain maps (e.g. TileServer GL / MapLibre).

## Active development path (14 November 2026)

The current supported development entry point is the [consolidated OSM-land-only Terrain-RGB pipeline](docs/consolidated-terrain-pipeline.md), built from **existing** original source/OSM land validators, the original shard ownership and the validated MBTiles merger. The latest [offline consolidation regression #43626725409](https://github.com/ColombiaTransit/colombia-height/actions/runs/43626725409) succeeded (20 tests). The first [real 140-source/OSM inland pilot #43624636935](https://github.com/ColombiaTransit/colombia-height/actions/runs/43624636935) succeeded with 10 true native tiles.

The new entry point uses z9–13 immutable chunk rosters and **fails closed** for mixed physical land/offland tiles; nationwide Terrain-RGB generation/publication remains blocked by renderer-safe mixed-coast handling and lower zooms z0–8. Prior successful Medellín, coast, island, source-seam and land-gap research is historical verified evidence: **do not repeat those scans/pilots**. The underlying 137 original production COGs remain unchanged; 140 is still a separately verified staging source list.

## Historical baseline status (13 November 2026)

**Research and validation — not published**. The selected source inventory is
137 Copernicus GLO-30 COGs (~5.184 GiB). A completed national native-pixel
coverage scan of 96,751 z0–13 candidate tiles found **92,973 fully covered**
and **3,778 partially covered**. All 32 geographic shards reconciled with
unique XYZ IDs: [successful run #43435820259](https://github.com/ColombiaTransit/colombia-height/actions/runs/43435820259).

Regional, two-COG and four-COG pilot seam validation succeeded, but
**countrywide terrain generation and publication are not authorized**.
DEM coverage does not imply Colombian land jurisdiction; missing DEM values
must not be replaced with 0 m or artificial -10000 m bathymetry.

The [national land-reference audit](docs/national-land-results-2026-11-13.md)
completed successfully across all 32 shards. A subsequent
[official IGAC department-polygon source screen](docs/official-igac-source-screen.md)
examined 52 omitted candidate COGs and found one direct administrative-land
candidate at Tumaco. A follow-up direct native-pixel z13 comparison verified
real DEM-height recovery at Tumaco and Malpelo. The 52-source screen and
two-source experiment are recorded in the
[durable source review register](data/official-igac-source-review-2026-11-13.json).
Neither administrative polygons nor Natural Earth establish a certified
coastline or the status of every remote island. No additional COG has yet
been approved for inclusion; all 137 selected COGs remain unchanged.

## OSM land-reference audit (non-publication)

The [OSM native DEM land-coverage study](docs/osm-national-land-coverage.md)
compares original Copernicus NoData pixels with detailed OSMCoastline
land polygons, including a four-site island/coast pilot and all 1,917
original incomplete z13 tiles (the initial 1,004 Natural Earth land-gap
tiles are tracked separately). The global OSM dataset is downloaded
only once per workflow run and is not committed or released.
OSM land is **not** a legal Colombian territory mask, and absence of an
OSM land polygon does **not** prove ocean; no synthetic elevations or
automatic source expansions are permitted. Data source attribution:
**© OpenStreetMap contributors, ODbL 1.0**.

## Source and attribution

- Elevation: [Copernicus DEM GLO-30 Public](https://registry.opendata.aws/copernicus-dem/), AWS bucket `copernicus-dem-30m`. See the source licence and attribution conditions before redistributing derivatives.
- Country boundaries: [geoBoundaries gbOpen COL ADM0](https://www.geoboundaries.org/), subject to the licence and attribution specified in the API metadata.
- Geographic coverage is based on the selected ADM0 geometry, including islands only if present in that boundary dataset. Country polygon coverage and DEM coverage must be checked separately.

## Run the inventory

In GitHub, go to **Actions → Inventory Colombia DEM → Run workflow**.

It produces an artifact named `colombia-dem-inventory` containing:

- `colombia_dem_manifest.csv` — intersecting available source tiles, URLs, sizes and HEAD status
- `colombia_dem_summary.json` — source, counts, known total size and any failed size checks

Locally:

```bash
python -m pip install -r requirements.txt
python scripts/inventory.py --output output/
```

The script does **not** download GeoTIFF content. The full dataset download and terrain RGB conversion will be designed after examining the inventory and available runner disk space.

## Validation stages

1. Source COG inventory and island probes — completed for the selected 137 COGs.
2. Small/medium region Terrain-RGB and seam pilots — passed for tested areas.
3. National native-DEM pixel coverage registry — completed, 96,751 candidates.
4. Reference land/shoreline and island-gap classification — in progress.
5. Confirm official land/island scope, missing-land policy, systematic edge QA.
6. Only after quality gates: generate, validate and consider publishing national Terrain-RGB MBTiles.

Keep generated GeoTIFF, MBTiles, and release assets outside git.
