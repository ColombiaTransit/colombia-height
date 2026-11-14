#!/usr/bin/env python3
"""Local-only server for MapLibre QA of already-generated Terrain-RGB MBTiles.

Reads a *supplied* existing MBTiles from disk: no Copernicus downloads,
no global OSM reference fetch, no updates to a real TileServer installation.
Missing/offland XYZ tiles respond HTTP 204 (no DEM), not fake 0 m tiles.
"""
import argparse
import mimetypes
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TILE_RE = re.compile(r"^/tiles/(\d+)/(\d+)/(\d+)\.png$")


def serve(path, port, repo_root):
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    repo_root = Path(repo_root).resolve()
    files = {
        "/": repo_root / "scripts" / "maplibre_coast_preview.html",
        "/maplibre-gl.mjs": repo_root / "node_modules" / "maplibre-gl" / "dist" / "maplibre-gl.mjs",
        "/maplibre-gl-worker.mjs": repo_root / "node_modules" / "maplibre-gl" / "dist" / "maplibre-gl-worker.mjs",
        "/maplibre-gl-shared.mjs": repo_root / "node_modules" / "maplibre-gl" / "dist" / "maplibre-gl-shared.mjs",
        "/maplibre-gl.css": repo_root / "node_modules" / "maplibre-gl" / "dist" / "maplibre-gl.css",
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            tile_match = TILE_RE.fullmatch(self.path)
            if tile_match:
                z, x, y = (int(v) for v in tile_match.groups())
                if not (0 <= z <= 13 and 0 <= x < 1 << z and 0 <= y < 1 << z):
                    self.send_error(400, "invalid tile key")
                    return
                with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
                    row = db.execute(
                        "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
                        (z, x, (1 << z) - 1 - y),
                    ).fetchone()
                if not row:
                    self.send_response(204)
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    return
                blob = row[0]
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
                return
            candidate = files.get(self.path)
            if candidate and candidate.is_file():
                blob = candidate.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", ("application/javascript" if candidate.suffix == ".mjs" else (mimetypes.guess_type(str(candidate))[0] or "text/html")))
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
                return
            self.send_error(404, "Unknown asset (local test server only)")

        def log_message(self, format, *args):
            print("tile-test HTTP", format % args, flush=True)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Serving preexisting real coastal MBTiles {path} on http://127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mbtiles", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    serve(args.mbtiles, args.port, args.repo_root)
