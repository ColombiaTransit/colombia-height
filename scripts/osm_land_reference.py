#!/usr/bin/env python3
"""Make a temporary Colombia-region OSMCoastline land-polygon reference.

The official FOSSGIS osmdata WGS84 split shapefile is downloaded ONCE.
It is clipped to a study rectangle only (not a sovereignty boundary).
No OSM data is committed or released. OSM land is evidence, not a
certified Colombian territorial or hydrographic land/water mask.
"""
import argparse
import gzip
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import requests
import shapefile
from shapely import wkb
from shapely.geometry import Point, box, shape
from shapely.validation import make_valid

DOWNLOAD = "https://osmdata.openstreetmap.de/download/land-polygons-split-4326.zip"
SOURCE_PAGE = "https://osmdata.openstreetmap.de/data/land-polygons.html"
STUDY_BBOX = (-84.0, -5.0, -66.0, 17.0)
PROBE_POINTS = {
    "bogota_mainland": (-74.072, 4.711),
    "tumaco_approx": (-78.76, 1.81),
    "san_andres_approx": (-81.70, 12.57),
    "providencia_approx": (-81.37, 13.35),
    "malpelo_approx": (-81.606, 4.005),
}
MAX_COMPRESSED = 1_700_000_000
MAX_EXTRACTED = 10_000_000_000
MAX_CLIPPED_GEOMS = 125_000


def polygon_parts(geom):
    """Retain only land polygon components; lines/points never become land."""
    if geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type in ("GeometryCollection", "MultiPolygon"):
        return [piece for sub in geom.geoms for piece in polygon_parts(sub)]
    return []


def validate_download_url(url):
    if url != DOWNLOAD:
        raise ValueError("Only the fixed upstream OSMCoastline land-polygon archive is permitted")
    return url


def fetch_archive(url, target, session=None):
    validate_download_url(url)
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    session = session or requests.Session()
    sha = hashlib.sha256()
    size = 0
    with session.get(url, stream=True, timeout=(20, 120),
                     headers={"User-Agent": "ColombiaTransit-OSM-land-reference/1.0"}) as response:
        response.raise_for_status()
        last_modified = response.headers.get("Last-Modified")
        etag = response.headers.get("ETag")
        with target.open("wb") as dest:
            for chunk in response.iter_content(chunk_size=1024*1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_COMPRESSED:
                    raise RuntimeError("OSM archive exceeds the 1.7GB job safety cap")
                sha.update(chunk)
                dest.write(chunk)
    if size < 100_000:
        raise RuntimeError("OSM archive unexpectedly small; possible error response")
    return {"url": url, "sha256": sha.hexdigest(), "size_bytes": size,
            "http_last_modified": last_modified, "http_etag": etag}


def safe_extract_shapefile(zip_path, root):
    """Extract only expected shapefile components with bounded paths/sizes."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    expected = {".shp", ".shx", ".dbf", ".prj"}
    entries = {}
    with ZipFile(zip_path) as archive:
        for member in archive.infolist():
            filename = Path(member.filename).name
            if filename.lower() == "land_polygons" + Path(filename).suffix.lower():
                suffix = Path(filename).suffix.lower()
                if suffix in expected:
                    if suffix in entries:
                        raise RuntimeError("Duplicated OSM shapefile member")
                    entries[suffix] = member
        if not {".shp", ".shx", ".dbf"}.issubset(entries):
            raise RuntimeError("OSM land_polygons.shp/.shx/.dbf missing")
        if sum(x.file_size for x in entries.values()) > MAX_EXTRACTED:
            raise RuntimeError("Expanded OSM shapefile exceeds the 10GB disk safety cap")
        for ext, member in entries.items():
            dest = root / ("land_polygons" + ext)
            with archive.open(member) as src, dest.open("wb") as tgt:
                shutil.copyfileobj(src, tgt, length=4*1024*1024)
    return root / "land_polygons.shp"


def clip_split_polygons(shp, study_bbox=STUDY_BBOX):
    """BBox-filter stream, clip, and retain overlapping fragments.

    Split polygon files deliberately have overlapping edges. Rasterize
    the union *locally* per tile; do not sum feature area or counts.
    """
    rect = box(*study_bbox)
    selected = []
    read = 0
    with shapefile.Reader(str(shp)) as reader:
        for s in reader.iterShapes(bbox=study_bbox):
            read += 1
            if s.shapeType not in (shapefile.POLYGON, shapefile.POLYGONM,
                                   shapefile.POLYGONZ):
                raise RuntimeError("Global OSM land shapefile contains non-polygon geometry")
            g = shape(s.__geo_interface__)
            if not g.is_valid:
                g = make_valid(g)
            if g.is_empty or not g.intersects(rect):
                continue
            clipped = g.intersection(rect)
            for part in polygon_parts(clipped):
                if part.area > 0:
                    selected.append(part)
            if len(selected) > MAX_CLIPPED_GEOMS:
                raise RuntimeError("Unreasonably many land fragments in Colombia study bbox")
    if not selected:
        raise RuntimeError("Global OSM land layer returned no Colombia-area polygon")
    if not any(p.contains(Point(-74.072, 4.711)) for p in selected):
        raise RuntimeError("Mainland Colombia sanity point not covered in OSM clip")
    return selected, read


def write_clip(polygons, provenance, output):
    """Gzip newline-delimited WKB: one polygon per line, no third-party pickle."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    ref = output / "osm-land-study.wkb.gz"
    with gzip.open(ref, "wt", encoding="ascii", compresslevel=6) as dest:
        for g in polygons:
            dest.write(g.wkb_hex + "\n")
    probes = {}
    for name, (lon, lat) in PROBE_POINTS.items():
        pt = Point(lon, lat)
        probes[name] = any(g.contains(pt) for g in polygons)
    report = {
        "status": "OSMCoastline_WGS84_split_land_clipped_study_reference",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE_PAGE,
        "download_archive_url": DOWNLOAD,
        "archive": provenance,
        "source_geometry_type": "polygon", "source_projection": "EPSG:4326",
        "study_bbox_not_country_border": list(STUDY_BBOX),
        "clipped_polygon_fragments": len(polygons),
        "reference_wkb_file": ref.name,
        "reference_wkb_sha256": hashlib.sha256(ref.read_bytes()).hexdigest(),
        "probe_centers_not_land_truth": probes,
        "odbl_attribution": "© OpenStreetMap contributors; ODbL 1.0; https://www.openstreetmap.org/copyright",
        "odbl_distribution_note": "The temporary reference is derived from OSM; ODbL attribution and any applicable derivative-database sharing obligations must be reviewed before public reuse.",
        "osm_is_not_colombian_jurisdiction": True,
        "quitasueno_never_automatically_selected": True,
        "national_publication_allowed": False,
    }
    (output / "osm-land-study-metadata.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def load_clip(path, expected_hash=None):
    path = Path(path)
    if expected_hash is not None:
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
            raise ValueError("Clipped OSM polygon reference SHA256 mismatch")
    out = []
    with gzip.open(path, "rt", encoding="ascii") as src:
        for line in src:
            if line.strip():
                geom = wkb.loads(bytes.fromhex(line.strip()))
                if geom.geom_type != "Polygon" or not geom.is_valid:
                    raise RuntimeError("Corrupt or non-polygon OSM clip geometry")
                out.append(geom)
                if len(out) > MAX_CLIPPED_GEOMS:
                    raise RuntimeError("Too many land polygons in clipped reference")
    if not out:
        raise ValueError("Empty OSM land polygon clip")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, default=Path("output/osm-reference"))
    a = ap.parse_args()
    work = a.output / "unpacked"
    archive = a.output / "global-land-polygons.zip"
    try:
        info = fetch_archive(DOWNLOAD, archive)
        shp = safe_extract_shapefile(archive, work)
        geom, read_count = clip_split_polygons(shp)
        result = write_clip(geom, info, a.output)
        result["selected_split_shapes_examined"] = read_count
        (a.output / "osm-land-study-metadata.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2), flush=True)
    finally:
        # No global 930MB archive or unpacked global files in the artifact.
        if archive.exists():
            archive.unlink()
        if work.exists():
            shutil.rmtree(work)


if __name__ == "__main__":
    main()
