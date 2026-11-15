# Colombia Height — ColombiaTerrain Terrain-RGB

**Stable countrywide release: `v1.0.0` (15 November 2026).**

Validated national **Copernicus DEM GLO-30 + OSM Colombian land**
in **Mapbox Terrain-RGB 256 px PNG / SQLite MBTiles**, zoom **0–13**.
Built for **TileServer GL** and **MapLibre GL JS**.

### Permanent links for other projects

- **Exact pinned version:** [v1.0.0 release](https://github.com/ColombiaTransit/colombia-height/releases/tag/v1.0.0)
- **Machine-readable exact version:** [v1.0.0 Terrain-RGB manifest](https://github.com/ColombiaTransit/colombia-height/releases/download/v1.0.0/colombia-terrain.manifest.json)
- **Stable moving pointer:** [latest Terrain-RGB manifest](https://github.com/ColombiaTransit/colombia-height/releases/latest/download/colombia-terrain.manifest.json)
- **Latest stable release:** [GitHub Releases/latest](https://github.com/ColombiaTransit/colombia-height/releases/latest)
- [Versioned release notes and install commands](release/RELEASE_NOTES.md) · [Data attribution and license](release/DATA_LICENSE.md)

```bash
# Fetch the exact version or use --tag latest to follow newer approved releases.
python3 scripts/install_terrain_release.py --tag v1.0.0 \
  --output /srv/colombia-terrain/colombia-terrain.mbtiles
```

The installer only needs Python 3. It downloads and verifies **three GitHub
Release assets** (the 4.16 GiB MBTiles exceeds the GitHub 2 GiB single-asset
limit), checks each part and the final complete SHA-256, and installs
atomically without a second full-size download directory.

**Genuine national quality approval:** 66,607 Terrain-RGB tiles and matching
factual OSM masks; all 14 zoom levels; 71 native PNG grids served pixel-exact
by real TileServer GL; 7/7 nationwide MapLibre 3D browser scenes passed.
The lowest -239.1 m land pixel was independently traced to the original
Copernicus GLO-30 source at a deep mine, not a generator defect.
The intentionally flat background outside Colombian OSM land is approved
for 3D visualization only, **not bathymetry nor a factual foreign DEM**.
See [national QA evidence](docs/national-terrain-QA-2026-11-15.md).

Once self-hosted, TileServer GL serves
`/data/colombia-terrain/{z}/{x}/{y}.png` and
`/data/colombia-terrain.json`; GitHub itself offers DOWNLOAD URLs rather
than an on-demand raster tile service.
See [TileServer GL integration](docs/tileserver-gl-terrain-integration.md).

### Generator provenance

The [countrywide OSM 140-source generator](docs/consolidated-terrain-pipeline.md)
was run once across 32 candidate shards (26 nonempty), with 409 immutable
chunks, all native OSM/mask and checksum gates. Its successful existing
output was promoted to the public version without re-running Copernicus
downloads or region generation.

---

## Historical baseline status (13 November 2026)

**Historical research state before the 15 November 2026 public v1.0.0 release.** The selected source inventory is
137 Copernicus GLO-30 COGs (~5.184 GiB). A completed national native-pixel
coverage scan of 96,751 z0–13 candidate tiles found **92,973 fully covered**
and **3,778 partially covered**. All 32 geographic shards reconciled with
unique XYZ IDs: [successful run #43435820259](https://github.com/ColombiaTransit/colombia-height/actions/runs/43435820259).

Regional, two-COG and four-COG pilot seam validation succeeded, but
**countrywide publication had not yet been authorized at that historical checkpoint**.
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
- Released country footprint: OpenStreetMap Colombia relation R120027, intersected with OSMCoastline physical land polygons; © OpenStreetMap contributors, ODbL 1.0.
- geoBoundaries/Natural Earth/IGAC were **historical comparative references only**, not the published final land clip.
- The final license obligations for modified Copernicus GLO-30 and OSM-derived masks are documented at [release/DATA_LICENSE.md](release/DATA_LICENSE.md).

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

## Historical validation stages (since completed)

1. Source COG inventory and island probes — completed for the selected 137 COGs.
2. Small/medium region Terrain-RGB and seam pilots — passed for tested areas.
3. National native-DEM pixel coverage registry — completed, 96,751 candidates.
4. Reference land/shoreline and island-gap classification — completed for national v1.0.0.
5. Confirm country-only OSM land/island scope, missing-land policy and systematic edge QA — completed.
6. National z0–13 Terrain-RGB MBTiles generated, validated and released as v1.0.0.

Keep generated GeoTIFF, MBTiles, and release assets outside git.
