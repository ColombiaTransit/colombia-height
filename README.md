# Colombia Height

Reproducible inventory and preparation of **Copernicus DEM GLO-30** elevation data for Colombia, intended for self-hosted terrain maps (e.g. TileServer GL / MapLibre).

## Status

Phase 1: **inventory only**. No DEM source files or large MBTiles are committed to git. The inventory workflow can be started manually from GitHub Actions, and produces a CSV manifest and JSON summary.

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

## Planned stages

1. Inventory and verify coverage, counts, file sizes
2. Download and process selected regional batches (without exhausting GitHub-hosted runner storage)
3. Generate and validate Mapbox Terrain-RGB tiles
4. Generate optional contours, benchmark MBTiles sizes and publication strategy

Keep generated GeoTIFF, MBTiles, and release assets outside git.
