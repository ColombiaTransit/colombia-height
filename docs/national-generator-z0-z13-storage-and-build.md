# Colombia national Terrain-RGB generator, all zoom levels 0–13

**Build implementation:** Complete source/mask/shard/merge code exists in
[scripts/consolidated_terrain_pipeline.py](../scripts/consolidated_terrain_pipeline.py).
The original 140-source manifest and OSM polygon/country relation are reused.
**Production status:** a complete national MBTiles has NOT yet been generated
or published. Do not confuse completed code with a finished release.

## Runner storage actually observed, not assumed

The project measured the disk on the same free public GitHub Linux runners:
- [Antioquia #43188143857](https://github.com/ColombiaTransit/colombia-height/actions/runs/43188143857): root filesystem **145 GB total, 88 GB available**.
- [Real OSM inland #43624636935](https://github.com/ColombiaTransit/colombia-height/actions/runs/43624636935): **145 GB total, 85 GB available**.
- The GitHub documentation lists 14 GB for standard Linux runners, so **85 GB
  cannot be relied on without a live check**. The generator checks actual
  free disk using shutil.disk_usage: shard starts at >=25 GiB and reserves
  >=10 GiB, while full merge starts at >=35 GiB.

The original 137 preapproved Copernicus COGs total about **5.184 GiB**;
the staged manifest adds three previously checked coastal/island sources.
The real Antioquia multi-source pilot generated 1,057 Terrain-RGB tiles in
about 85.8 MiB (~81 KiB per tile). Applied to the older nationwide
96,751 candidate z0–13 tiles this implies approximately **7.7 GiB**
of source RGB/SQLite, before country mask filtering and regional differences.
This is an **estimate, not the measured final national MBTiles size**.

**Working budget:** final Terrain-RGB with OSM masks roughly 5–10 GiB,
source COG cache up to 5–6 GiB, and at merge time another 10–20 GiB for
incoming shard archives and the assembled SQLite. Reserve **35–45 GiB** if
you wish to assemble on one runner. In prior real project runs ~85–88 GB
free was available. Full build jobs must abort if the actual runner differs.

## Exact physical-land policy at every zoom

True input heights: Copernicus DEM GLO-30, only where both OSMCoastline
physical land polygons and OSM Colombia relation 120027 are positive.
Any missing native elevation **on Colombian land** blocks that tile.

For MapLibre raster-dem, the off-scope visual background is explicitly
flat 0 metres, **NOT** bathymetry, fake Copernicus measurements or a factual
DEM outside Colombia:
- Physical sea (OSM offland): 0 m display surface.
- Foreign physical land outside Colombia: 0 m OUT-OF-SCOPE country-clipped
  background, never labelled sea or measured foreign elevation.

The 140-source real OSM audit for z0–8
[#43634723596](https://github.com/ColombiaTransit/colombia-height/actions/runs/43634723596)
found **85 mixed low-zoom tiles** also containing foreign physical land.
The implementation therefore requires two explicit switches for national
display mode: --coast-render-only-sea-surface and
--render-flat-outside-colombia. Original sea-only strict mode still blocks
foreign land. Every output PNG has an accompanying exact 256x256 factual
Colombian land mask in the SQLite osm_land_mask table, and metadata explicitly
states foreign_land_is_sea=false.

## Manual full-country build without Action artifact storage quota

Workflow: [National Colombia z0–13 DRAFT Generator](../.github/workflows/national-terrain-draft-build.yml).
Click Actions > Run workflow and select the stage and unique draft release tag.

1. **prepare**: reuse the actual existing OSM and 140-source artifact from
   successful run #43624636935 before its 7-day artifact retention expires;
   create one immutable z0–13 source-cell XYZ plan with unique ownership,
   32 geographic shards, 250 tiles per subchunk. Preserve the original
   preprocessed OSM geometry, country relation, source CSV and plan as
   assets of an **unpublished GitHub draft release**.
2. **build-all**: run 32 geographic shard jobs (max four parallel), using
   the previously saved small draft source and plan assets. Native 5.2 GiB
   of COGs is NOT downloaded on every step: each job shares a local source
   cache across all its assigned 250-tile chunks and does not repeat
   national source research. Every successful shard writes an archive to
   the draft release. Use the GitHub rerun-failed-jobs command to retry
   only unsuccessful shards.
3. **merge**: download all expected shard assets, verify the exact plan,
   manifest SHA256, geometry SHA256, positive OSM masks, all tile counts,
   database integrity, and unique XYZ ownership. Preserve original factual
   mask PNGs. Create a single final colombia-terrain.mbtiles, then split
   into **1,536 MiB** parts plus a full SHA256 and store them on the same
   unpublished draft release.

Why use draft releases: official
[GitHub Release limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
allow files under 2 GiB with no aggregate release-size cap, while the
repository has only 7-day Actions artifact retention. Drafts avoid falsely
publishing incomplete terrain. A draft release is storage for build input,
not a public national release.

To reconstruct on your TileServer GL host, download the numbered parts,
then run these commands:

~~~bash
cat colombia-terrain.mbtiles.part-* > colombia-terrain.mbtiles
sha256sum -c colombia-terrain.mbtiles.sha256
~~~

For TileServer GL add the data entry in
[deploy/tileserver-gl/config.json](../deploy/tileserver-gl/config.json).
The MapLibre consumer uses raster-dem, encoding mapbox, tileSize 256.

## Local operation and restarting a shard

The consolidated CLI has commands: plan, shard, render (one chunk), merge.
- plan is deterministic and does NOT download COGs.
- shard has a real disk preflight and shares OSM reference + original COG
  cache across its assigned chunks.
- shard verifies hashes and SQLite counts when resuming an earlier chunk;
  completed chunks are reused rather than regenerated.
- merge refuses incomplete/missing/altered chunks or a partial national
  product; never labels a draft as ready for public release.

Next accepted gate: real native low-zoom z0–3 pilot using the existing
input bundle, followed by a full national generation and border/island
quality report. Source QA, 997 original false land gaps, 68 Tumaco tiles
and previously successful Cartagena/COG seams are NOT to be repeated.
