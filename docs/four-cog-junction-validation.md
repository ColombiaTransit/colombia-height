# Four-source, four-batch DEM/Terrain-RGB junction validation

[Four Copernicus COG Source Junction QA](../.github/workflows/four-cog-junction-validation.yml)
extends the passing two-source test and examines an **inland 2×2 degree COG
junction** at 74° W / 6° N, covering four different Copernicus DEM GLO-30
source cells: N05/N06 × W075/W074.

The actual Web Mercator test bounds follow z10 x=299..303,
y=493..496, enclosing approximately 1.76×1.41 degrees around that
junction. Four independently processed batches divide this 5×4 z10
parent grid into northwest/northeast/southwest/southeast quadrants.
At default zoom 10–11, the planned tiles are 20+80 = **100**.

## Validation

1. Download only the four required original COGs to a temporary
   GitHub runner cache. Each batch independently selects/open sources.
2. Render each Web Mercator tile directly from the actual source
   rasters; **never resample to a clipped geographic intermediate**.
3. Track the source file supplying every pixel and count switches
   between neighboring pixels in **both** east-west and north-south
   directions. The test must find all four native COGs inside the
   same z10 junction tile.
4. Reject source NoData or missing pixels: no artificial -10000m
   trenches or guessed sea level can enter Terrain-RGB.
5. Merge quadrant MBTiles with duplicate-key rejection and SQLite
   integrity checks.
6. Reopen the four original source rasters independently and regenerate
   every cross-batch border tile at the identical output pixel grid.
   Decoded Terrain-RGB must be within **0.16m** of the reference.
7. Report natural elevation gradients along batch boundaries without
   forcing neighboring geographic points to share the same elevation.

Only a compact JSON report is retained for one day; source files and
trial MBTiles are not uploaded or published.

## Limits and decision gate

This validates one selected interior source junction, not all 137
Copernicus files. The reference uses the same GDAL reproject algorithm,
so this does not establish absolute source DEM accuracy. Coastal
masking, island inclusion and full national quality gates are
separate tasks. The national generator should not be published solely
because this local junction test succeeds.
