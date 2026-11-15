# Colombia Terrain-RGB v1.0.0 — first stable nationwide release

**Status: validated stable dataset — 15 November 2026**

Colombia-only Copernicus GLO-30 (~30m source data) terrain in
**Mapbox Terrain-RGB 256×256 PNG / SQLite MBTiles**, zoom **0–13**,
for TileServer GL and MapLibre GL.

**Release tag:** `v1.0.0`. The tag and version-specific download
URLs are immutable references for integrations. The GitHub
`releases/latest/download/…` URLs remain stable entry points
that follow future designated stable releases.

### Official URLs for other projects

- **Pinned immutable manifest:**
  https://github.com/ColombiaTransit/colombia-height/releases/download/v1.0.0/colombia-terrain.manifest.json
- **Moving latest manifest:**
  https://github.com/ColombiaTransit/colombia-height/releases/latest/download/colombia-terrain.manifest.json
- **Versioned release page:**
  https://github.com/ColombiaTransit/colombia-height/releases/tag/v1.0.0
- **Latest stable release page:**
  https://github.com/ColombiaTransit/colombia-height/releases/latest

The dataset is distributed as **three parts** because the whole national
MBTiles exceeds GitHub's 2 GiB per-asset limit.

- `colombia-terrain.mbtiles.part-000` — 1,610,612,736 bytes
- `colombia-terrain.mbtiles.part-001` — 1,610,612,736 bytes
- `colombia-terrain.mbtiles.part-002` — 1,244,971,008 bytes

The three files concatenate directly, in the above numeric order,
to one **4,466,196,480-byte** `colombia-terrain.mbtiles` file.

**Full SHA-256:**

```text
daa49c62e2c08b8922ca7f2c9f7575346b37cdcd4b1a84659f03d3d818377bdb
```

### Download and verify (no source-code checkout needed)

```bash
BASE=https://github.com/ColombiaTransit/colombia-height/releases/download/v1.0.0
for i in 000 001 002; do
  curl -fL --retry 3 -o "colombia-terrain.mbtiles.part-${i}" \
    "${BASE}/colombia-terrain.mbtiles.part-${i}"
done
curl -fL --retry 3 -O "${BASE}/colombia-terrain.mbtiles.sha256"
cat colombia-terrain.mbtiles.part-{000,001,002} > colombia-terrain.mbtiles
sha256sum -c colombia-terrain.mbtiles.sha256
```

For future automatic upgrades, use the machine-readable latest manifest
and installer:

```bash
python3 scripts/install_terrain_release.py \
  --tag latest --output /srv/colombia-terrain/colombia-terrain.mbtiles
```

The installer works with Python 3 standard libraries only, streams parts
into ONE temporary MBTiles (no double disk usage), independently hashes
each part and the complete output, and atomically installs only if correct.

### TileServer GL and MapLibre

Place the completed `colombia-terrain.mbtiles` in the TileServer GL
data directory with `deploy/tileserver-gl/config.json` (or merge its
`colombia-terrain` data entry into an existing server config).

Server endpoints **once you run your own TileServer GL service**:

- `/data/colombia-terrain.json` — TileJSON
- `/data/colombia-terrain/{z}/{x}/{y}.png` — Mapbox Terrain-RGB PNG (XYZ)

Client source:

```js
map.addSource('colombia-terrain', {
  type: 'raster-dem',
  tiles: ['https://YOUR_TILESERVER/data/colombia-terrain/{z}/{x}/{y}.png'],
  tileSize: 256, minzoom: 0, maxzoom: 13, encoding: 'mapbox'
});
map.setTerrain({ source: 'colombia-terrain', exaggeration: 1 });
```

**GitHub Release asset URLs are downloads, not live on-demand terrain
tile service endpoints.** Individual projects should download/reassemble
the MBTiles once and serve it with their own TileServer GL instance.

### Validation and approved caveats

- **66,607** native Terrain-RGB tiles and **66,607** exact per-pixel
  OSM land masks (SQLite `osm_land_mask`), with original OSM reference
  audits. All zooms 0–13 are present.
- **71** real TileServer GL terrain grids verified pixel-identical.
- **7/7** real MapLibre GL 6.8/Chromium geographic scenes passed.
- The most-negative genuine land height **−239.1 m** is explained
  by the native Copernicus source in the deep Pribbenow open-pit
  mine area; original source and OSM land masks were separately verified.
- Flat **0m outside Colombian OSM land** is accepted as *render-only*
  water/out-of-country backdrop. **Not bathymetry, not foreign DEM and
  never valid factual height outside the land mask.**

Additional release evidence is included as
`national-full-pixel-mask-osm-qa.json`,
`national-real-tileserver-gl-qa.json`,
`national-maplibre-browser-qa.json` and
`original-minimum-height-investigation.json`.
See `release/DATA_LICENSE.md` and
`docs/national-terrain-QA-2026-11-15.md`.

**Required modified Copernicus credit:**

> produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and
> © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS
> by the European Union and ESA; all rights reserved.

**OSM attribution:** © OpenStreetMap contributors, ODbL 1.0.
The factual OSM-derived land-mask table is included with the MBTiles.
