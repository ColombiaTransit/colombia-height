#!/usr/bin/env python3
"""Persist the genuine OSM Colombia relation geometry for the land-only DEM pilot.

Reuse the existing validated Nominatim lookup; do not substitute an ADM0
boundary or infer coastlines from an administrative relation.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
from shapely.geometry import mapping

from osm_only_colombia_land_finish import get_osm_col_boundary, OSM_COL_RELATION


def save_country_relation(path, session=None):
    country, provenance = get_osm_col_boundary(session or requests.Session())
    document = {
        "source": "OpenStreetMap",
        "OSM_relation_id": OSM_COL_RELATION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "geometry": mapping(country),
        "provenance": provenance,
        "country_relation_is_not_physical_land": True,
        "national_publication_allowed": False,
    }
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    incomplete = target.with_suffix(target.suffix + ".incomplete")
    incomplete.unlink(missing_ok=True)
    try:
        incomplete.write_text(json.dumps(document, separators=(",", ":")) + "\n")
        from generate_osm_land_only_terrain import load_osm_country
        checked = load_osm_country(incomplete)
        if checked.is_empty or not checked.covers(country.representative_point()):
            raise RuntimeError("OSM Colombia relation round-trip check failed")
        incomplete.replace(target)
    finally:
        incomplete.unlink(missing_ok=True)
    print(json.dumps({
        "status": "verified_OSM_Colombia_relation_120027_geometry_only",
        "file": str(target), "bytes": target.stat().st_size,
        "geometry_type": country.geom_type,
        "bounds": list(country.bounds),
        "not_a_coastline_mask": True,
    }, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path("output/osm-country/colombia-relation-120027.json"))
    args = parser.parse_args()
    save_country_relation(args.output)


if __name__ == "__main__":
    main()
