#!/usr/bin/env python3
"""Install published ColombiaTerrain MBTiles by immutable GitHub Release tags.

Usage:
  python3 scripts/install_terrain_release.py --tag v1.0.0 --output /data/colombia-terrain.mbtiles
  python3 scripts/install_terrain_release.py --tag latest --output /data/colombia-terrain.mbtiles

Only standard Python libraries are required. Streaming downloads directly into
one temporary MBTiles avoid storing extra 4.16 GiB parts on disk. Every part
and the COMPLETE MBTiles are verified against a release-asset manifest.
Existing matching output files are reused. No DEM/OSM computation is performed.
"""
import argparse
import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = "ColombiaTransit/colombia-height"
HOST = f"https://github.com/{REPO}/releases"
ASSET_PREFIX = "colombia-terrain.mbtiles.part-"
CHUNK = 1024 * 1024


def download_url(tag, name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", name):
        raise ValueError("Invalid asset name")
    if tag == "latest":
        return f"{HOST}/latest/download/{name}"
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ValueError("Only immutable vX.Y.Z release tags or latest are allowed")
    return f"{HOST}/download/{tag}/{name}"


def retrieve(url):
    return urllib.request.urlopen(
        urllib.request.Request(url, headers={
            "User-Agent": "ColombiaTransit Terrain Release Installer/1.0",
            "Accept": "application/octet-stream",
        }), timeout=120)


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def load_manifest(tag):
    with retrieve(download_url(tag, "colombia-terrain.manifest.json")) as response:
        manifest = json.load(response)
    if manifest.get("schema") != "colombiatransit-terrain-rgb-release-v1":
        raise ValueError("Not a recognized ColombiaTerrain manifest")
    version = manifest.get("release_version")
    if not isinstance(version, str) or not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", version):
        raise ValueError("Invalid version in manifest")
    if tag != "latest" and tag != version:
        raise ValueError("Pinned requested version differs from manifest")
    if manifest.get("format", {}).get("container") != "SQLite MBTiles":
        raise ValueError("Unexpected release container format")
    if manifest.get("format", {}).get("zoom_max") != 13:
        raise ValueError("Unexpected Colombia terrain zoom coverage")
    parts = manifest.get("parts")
    if not isinstance(parts, list) or len(parts) != 3:
        raise ValueError("Expected exactly 3 verified GitHub release parts")
    if [p.get("file") for p in parts] != [
        f"{ASSET_PREFIX}{i:03d}" for i in range(3)
    ]:
        raise ValueError("Unexpected part roster/order")
    if sum(p.get("bytes", -1) for p in parts) != manifest.get("merged_mbtiles_bytes"):
        raise ValueError("Part sizes do not sum to final MBTiles size")
    for part in parts:
        if not isinstance(part.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}",part["sha256"]):
            raise ValueError("Missing required part SHA256")
    if not re.fullmatch(r"[0-9a-f]{64}",manifest.get("merged_mbtiles_sha256", "")):
        raise ValueError("Missing final MBTiles SHA256")
    return manifest


def install(tag, destination, replace=False):
    destination = Path(destination).expanduser().resolve()
    manifest = load_manifest(tag)
    required_hash = manifest["merged_mbtiles_sha256"]
    if destination.exists():
        existing = sha256_file(destination)
        if existing == required_hash:
            print(f"REUSED existing complete validated MBTiles: {destination}")
            return destination
        if not replace:
            raise FileExistsError(
                f"Existing output does not match {manifest['release_version']}; "
                "refusing overwrite without --replace")
    destination.parent.mkdir(parents=True,exist_ok=True)
    filename = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb",prefix=".colombia-terrain-",
                                         suffix=".incomplete",dir=destination.parent,
                                         delete=False) as target:
            filename = Path(target.name)
            total_sha = hashlib.sha256()
            total_bytes = 0
            version = manifest["release_version"]  # resolve latest to versioned immutable assets
            for part in manifest["parts"]:
                name, size, digest = part["file"], part["bytes"], part["sha256"]
                part_hash = hashlib.sha256()
                downloaded = 0
                print(f"Downloading {name} ({size} bytes) from {version}",flush=True)
                with retrieve(download_url(version,name)) as response:
                    while block := response.read(CHUNK):
                        downloaded += len(block)
                        total_bytes += len(block)
                        part_hash.update(block)
                        total_sha.update(block)
                        target.write(block)
                if downloaded != size or part_hash.hexdigest()!=digest:
                    raise ValueError(f"Incorrect size or SHA256 for {name}; file NOT installed")
                print(f"VERIFIED part {name}: SHA256 {digest}",flush=True)
            if total_bytes != manifest["merged_mbtiles_bytes"]:
                raise ValueError("Final MBTiles byte total differs from manifest")
            if total_sha.hexdigest() != required_hash:
                raise ValueError("Final reassembled national MBTiles SHA256 mismatch")
            target.flush()
            os.fsync(target.fileno())
        os.replace(filename,destination)
        filename = None
        print(f"INSTALLED {destination} ({total_bytes} bytes), "
              f"version {version}, SHA256 {required_hash}",flush=True)
        return destination
    finally:
        if filename is not None:
            filename.unlink(missing_ok=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="v1.0.0",
                        help="Pinned vX.Y.Z tag or moving latest (default v1.0.0)")
    parser.add_argument("--output",required=True,
                        help="Destination .mbtiles file; parent directory must have ~4.16GiB available")
    parser.add_argument("--replace",action="store_true",
                        help="Replace mismatched existing file only after new output hashes pass")
    args=parser.parse_args()
    install(args.tag,args.output,args.replace)


if __name__=="__main__":
    main()
