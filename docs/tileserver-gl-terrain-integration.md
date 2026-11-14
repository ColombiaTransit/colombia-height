# Deploy Colombia Terrain-RGB MBTiles with TileServer GL

**Current target server: [maptiler/tileserver-gl](https://github.com/maptiler/tileserver-gl).**
This project produces **Mapbox Terrain-RGB PNG in SQLite MBTiles**, NOT vector
PBF/PMTiles, GeoTIFF, or Terrarium. TileServer GL serves the *data*; the
browser's MapLibre GL JS loads the tiles as type \`raster-dem\`. There is no
conversion, COG processing, or TileServer-specific re-encoding step.

## Approved server-side configuration

The checked-in [config.json](../deploy/tileserver-gl/config.json) mounts a
single file named \`/data/colombia-terrain.mbtiles\`:

~~~json
{
  "options": {"paths": {"root": "/data", "mbtiles": "."}},
  "styles": {},
  "data": {
    "colombia-terrain": {
      "mbtiles": "colombia-terrain.mbtiles",
      "tileSize": 256,
      "sparse": false
    }
  }
}
~~~

Use this as a **fragment** if you already run TileServer GL with other
MBTiles, styles and maps: add the \`colombia-terrain\` entry to your existing
\`data\` object rather than replacing your entire configuration.

For an isolated Docker container, place \`config.json\` and the MBTiles in the
same host folder, e.g. \`/srv/colombia-terrain\`, then run:

~~~bash
docker run -d --name colombia-tileserver --restart unless-stopped \
  -p 8080:8080 \
  -v /srv/colombia-terrain:/data:ro \
  maptiler/tileserver-gl:latest --config /data/config.json
~~~

For reproducible production, replace the floating \`latest\` tag with the
tested image tag or digest. The path in the volume contains the completed
generator's MBTiles (not the temporary pilot; the country dataset is not yet
published).

### Endpoints

- TileJSON: \`http://your-server:8080/data/colombia-terrain.json\`
- Terrain-RGB PNG tile: \`http://your-server:8080/data/colombia-terrain/{z}/{x}/{y}.png\` (XYZ URLs; TileServer GL translates internal MBTiles TMS y)
- With \`sparse: false\`, tiles outside OSM Colombian physical land have **HTTP 204 No Content**, not a fabricated all-sea Terrain-RGB file. This avoids unsafe overzoom of inland DEM onto offshore water.

### MapLibre GL source in a separate map style/application

~~~javascript
map.addSource('colombia-terrain', {
  type: 'raster-dem',
  tiles: [
    'https://your-domain.example/data/colombia-terrain/{z}/{x}/{y}.png'
  ],
  tileSize: 256,
  minzoom: 0,
  maxzoom: 13,
  encoding: 'mapbox'
});
map.setTerrain({ source: 'colombia-terrain', exaggeration: 1 });
~~~

**Zoom caution:** The finished national product must include z0–13 before using
the above \`minzoom:0\`. For the actual Cartagena test MBTiles, use
\`minzoom:11\` and \`maxzoom:13\` instead. Older MapLibre GL releases may produce
DEM warnings on sparse coastline/HTTP 204. The tested browser path uses MapLibre
GL JS 6.8.0 and checks errors, 3D initialization and real tile requests.

## Sea handling: display only, not elevations or bathymetry

Our opt-in coastal mode \`--coast-render-only-sea-surface\` retains original
Copernicus GLO-30 heights on positive **OSM physical Colombian land**. It emits
0 m on pixels confirmed outside **all OSM physical land** *only to give the 3D
viewer a flat visual water surface*. This is **not a measurement of seabed
depth** and must not be presented as a real terrain DEM outside land.

Every produced tile has a second SQLite \`osm_land_mask\` row containing a
256×256 grayscale PNG (255=true Colombian physical OSM land, 0=outside). This
is for provenance, audits and safe downstream analytic use; TileServer GL does
**not automatically expose or interpret** this custom table as an additional
map layer.

**Important:** TileServer GL has an optional native \`encoding: "mapbox"\`
**server config field** which can enable elevation lookup endpoints. We
intentionally **omit it in the TileServer GL server config** because those
endpoints could report the *render-only sea surface* as factual ocean
elevation. Instead, \`encoding:'mapbox'\` is set **only in the MapLibre
\`raster-dem\` client source**. If a separate elevation API is implemented,
it must check the factual OSM land mask and return NoData outside land. This is
a deliberate data-semantic safety distinction, not a format incompatibility.

## Original evidence and current status

- [Genuine Copernicus + OSM Cartagena coast pilot
  #43628318643](https://github.com/ColombiaTransit/colombia-height/actions/runs/43628318643):
  26 actual PNG tiles including 17 mixed land/sea, 9 fully land; 2 all-offland
  tiles skipped. Real land height samples retained within 0.05 m; 560,938
  sea pixels are exactly visual-only 0m.
- [MapLibre 6.8.0 Chromium rendering
  #43629735031](https://github.com/ColombiaTransit/colombia-height/actions/runs/43629735031):
  successful on the original Cartagena file using the local test server, with
  no DEM/JavaScript errors. This is a **browser decoder** test.
- [Real TileServer GL + MapLibre 6.8 integration run #43630855308](https://github.com/ColombiaTransit/colombia-height/actions/runs/43630855308): **SUCCESS.** The complete full TileServer GL Docker server served **all 26** genuine Cartagena Terrain-RGB tiles with **pixel-identical decoded heights** (HTTP gzip transport did not change pixels); an offland tile correctly returned **HTTP 204**. Chromium / MapLibre GL JS 6.8 enabled native 3D terrain and requested **32 actual HTTP 200 PNGs from TileServer GL `/data/colombia-terrain/…`** with **zero DEM errors and zero JS errors**. [Screenshot and JSON log artifact #14128370862](https://github.com/ColombiaTransit/colombia-height/actions/runs/43630855308/artifacts/14128370862), limited to seven-day retention. The automated test is now manual-only and reuses existing data; it must not trigger a new Copernicus/OSM scan.

The **server compatibility of option 1 is verified** against actual TileServer GL and MapLibre GL JS 6.8. The project must not publish a nationwide or coast-complete MBTiles until
all-zoom, all-islands/borders, full-source and map styling checks pass.
