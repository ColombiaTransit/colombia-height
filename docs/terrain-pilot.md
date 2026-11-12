# Medellín Terrain-RGB pilot

The manual GitHub Actions workflow `Build Medellin Terrain RGB Pilot` downloads only DEM tiles intersecting a test bounding box around Medellín, produces Mapbox Terrain-RGB PNG tiles for zoom 9–12 (optional 13), and stores them in an MBTiles SQLite database.

It reports source download size, output size, number of tiles per zoom, and validates sample elevation against the source raster. Source TIFFs are **not** uploaded as artifacts. The initial pilot is intentionally regional; it is not a nationwide terrain dataset.

## Run

Actions → **Build Medellin Terrain RGB Pilot** → Run workflow → choose max zoom.

The artifact contains `medellin-terrain-rgb.mbtiles` and `medellin-terrain-report.json`.

## Serving with TileServer GL

Configure the data source explicitly to enable the elevation API:

```json
{
  "options": { "paths": { "root": "/data" } },
  "data": {
    "terrain": {
      "mbtiles": "medellin-terrain-rgb.mbtiles",
      "encoding": "mapbox",
      "tileSize": 256
    }
  }
}
```

TileServer GL can serve the PNG raster-dem tiles via `/data/terrain/{z}/{x}/{y}.png` and can query elevations via `/data/terrain/elevation/{z}/{longitude}/{latitude}`. This is the full TileServer GL, not the Light variant.

MapLibre raster-dem configuration:

```js
map.addSource("terrain", {
  type: "raster-dem",
  url: "https://your-tileserver.example/data/terrain.json",
  tileSize: 256,
  encoding: "mapbox"
});
map.setTerrain({ source: "terrain", exaggeration: 1 });
```

Copernicus DEM GLO-30 is a DSM (surface model), not a surveyed road-level terrain model. The native vertical datum is EGM2008; numerical values reflect the source and resampling. The RGB encoding uses 0.1 m steps but **does not** imply 0.1 m source accuracy.

This pipeline is a proof of method. Country and island coverage, licence/attribution details, sea pixels, tile-edge seam behavior and output format need additional validation before nationwide publication.
