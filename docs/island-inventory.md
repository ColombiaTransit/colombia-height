# Colombia island coverage and extended GLO-30 inventory

## Why

The original GLO-30 inventory found 130 degree tiles by intersecting
geoBoundaries Colombia ADM0. A subsequent seven-location audit confirmed DEM
sources for San Andrés, Providencia and Malpelo, **but** the supplied country
polygon classified those three sampled areas as outside its land boundary.
Therefore, the original 130 is not accepted as a complete national source list.

## Reference sources

- Copernicus public GLO-30 source index:
  https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com/tileList.txt
- geoBoundaries `gbOpen/COL/ADM0`: baseline country polygon and licence as
  recorded in the inventory JSON.
- Natural Earth 1:10m **Land** and **Minor Islands**:
  https://www.naturalearthdata.com/downloads/10m-physical-vectors/
  Public-domain map reference, not an authoritative jurisdictional boundary.
- Colombian IGAC open geographic datasets:
  https://www.igac.gov.co/datos-abiertos/datos-abiertos-geoespaciales
  Candidate source for later validation of legal boundaries/official shapes.

## Implemented audit

`data/colombia-island-probes.json` provides an explicitly annotated list of
approximate sampling coordinates, covering San Andrés, Providencia,
Santa Catalina, Malpelo, Gorgona, Gorgonilla, Isla Fuerte, Rosario, San
Bernardo, Barú, Tierra Bomba and a number of offshore cays/banks. Points
are **not** authoritative island geometries: some bank centers are at sea, and
all candidate locations and jurisdiction should be reviewed before a release.

The [Extended Colombia DEM and Island Inventory](../.github/workflows/extended-inventory.yml)
workflow performs:

1. Run the original boundary-based inventory; preserve the 130-tile baseline.
2. Load the currently published Copernicus GLO-30 source index.
3. For every nominated island/cay/bank sampling location, test whether a
   corresponding GLO-30 **one-degree source tile** exists.
4. Download Natural Earth 1:10m land and minor-island shapes (~a few MB), and
   compare *sample-point classification* with geoBoundaries.
5. Union the source tiles nominated by island probes with the original
   boundary-based inventory (deduplicating by COG source name).
6. HEAD-check added source tile sizes, write a new extended CSV and a
   structured coverage report. **No DEM rasters are downloaded.**
7. Upload the compact data as an ephemeral Action artifact (one-day retention).

Outputs:
- `colombia_dem_manifest.csv`: original boundary-based baseline
- `colombia_dem_manifest_extended.csv`: unique union with selection reasons
- `colombia_dem_summary.json`: baseline statistics
- `colombia_island_coverage_report.json`: added tiles, gaps, probe
  classifications, provenance and remaining uncertainties

### Publication gates (not yet satisfied)

- This registration is a **targeted island audit**, not a complete proof of
  offshore national coverage. Further systematic official island geometry
  comparison is required.
- A matching one-degree source tile does not prove native GLO-30 coverage of
  *every land pixel*. Sample actual COG masks/heights before final release.
- Natural Earth's land/marine polygons cannot prove which country owns a cay.
  Nor does being outside geoBoundaries imply ocean.
- Identify remaining unregistered islands with official IGAC/department
  inventories and compare the resulting polygon coverage against the extended
  tile manifest, including small and distant cays.
- Establish proper ocean/no-data handling without inventing -10,000 m trenches
  or filling all missing source values with zero.
- Complete nationwide tile ownership, seam testing, size budgeting, and
  reproducible publication workflow.

This phase produces a repeatable evidence-driven manifest; it does not yet
declare a production-ready national mask or Terrain-RGB release.
