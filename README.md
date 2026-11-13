# Colombia Height

Reproducible inventory and preparation of **Copernicus DEM GLO-30** elevation data for Colombia, intended for self-hosted terrain maps (e.g. TileServer GL / MapLibre).

## Current status (13 November 2026)

**Research and validation — not published**. The selected source inventory is
137 Copernicus GLO-30 COGs (~5.184 GiB). A completed national native-pixel
coverage scan of 96,751 z0–13 candidate tiles found **92,973 fully covered**
and **3,778 partially covered**. All 32 geographic shards reconciled with
unique XYZ IDs: [successful run #43435820259](https://github.com/ColombiaTransit/colombia-height/actions/runs/43435820259).

Regional, two-COG and four-COG pilot seam validation succeeded, but
**countrywide terrain generation and publication are not authorized**.
DEM coverage does not imply Colombian land jurisdiction; missing DEM values
must not be replaced with 0 m or artificial -10000 m bathymetry.

The next step is the [land-reference validation](docs/national-land-coverage.md):
first a **36-tile pilot** across Tumaco, San Andrés, Providencia, Malpelo;
then optionally a separately dispatched full 32-shard land-reference audit.
Its polygon sources are provisional and are **not** an official ocean mask.
Every intermediate artifact has short retention; no permanent Releases exist.

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
