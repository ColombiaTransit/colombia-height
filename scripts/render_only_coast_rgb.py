#!/usr/bin/env python3
"""Explicit, reversible *render-only* zero-surface for sea pixels in Terrain-RGB.

Native Copernicus elevations are required exactly on OSM physical Colombian
land. Only confirmed OSM physical water/offland may receive the MapLibre
visualization surface at zero elevation. A foreign-country *land* pixel must
NEVER be silently called sea or set to zero: that case blocks.

The 0m sea surface is a 3-D visual datum, NOT bathymetry, a measurement of
ocean depth, or a height for analysis. Encode a separate exact OSM land mask
tile with each RGB tile to prevent the rendering-only values being mistaken
for ground truth. MapLibre's default DEMData lacks a per-pixel NoData mask.
"""
import io

import numpy as np
from PIL import Image

from medellin_terrain import rgb_encode

TILE_SIZE = (256, 256)
NODATA = -9999.0
SEA_SURFACE_RENDER_M = 0.0
COAST_MODE = "surface_zero_visual_only_osm_landmask_v1"


def decode_terrain_rgb(png):
    with Image.open(io.BytesIO(png)) as im:
        if im.format != "PNG" or im.size != TILE_SIZE:
            raise AssertionError("Terrain RGB must be a native 256x256 PNG")
        rgb = np.asarray(im.convert("RGB"), dtype=np.int64)
    return -10000 + (rgb[..., 0] * 65536 +
                      rgb[..., 1] * 256 + rgb[..., 2]) / 10.0


def decode_mask_png(png):
    with Image.open(io.BytesIO(png)) as im:
        if im.format != "PNG" or im.size != TILE_SIZE or im.mode != "L":
            raise AssertionError("OSM land mask must be 256x256 L PNG")
        gray = np.asarray(im, dtype=np.uint8)
    if np.any((gray != 0) & (gray != 255)):
        raise AssertionError("OSM land mask pixels must be exact 0 or 255")
    return gray == 255


def encode_coast_render_only(heights, colombian_land, physical_osm_land):
    """Return RGB tile, accompanying factual OSM mask, and exact QA statistics.

    Never interpolate/fill a native land elevation. Reject foreign physical
    land, including at administrative borders: 0m is ONLY for OSM sea.
    """
    heights = np.asarray(heights)
    required = np.asarray(colombian_land)
    physical = np.asarray(physical_osm_land)
    if not (heights.shape == required.shape == physical.shape == TILE_SIZE):
        raise ValueError("Expected 256x256 height, Colombia-land and physical-land grids")
    if required.dtype != np.dtype("bool") or physical.dtype != np.dtype("bool"):
        raise TypeError("Masks must be exact boolean arrays")
    if np.any(required & ~physical):
        raise ValueError("Colombian land may not be outside physical OSM land")
    foreign_land = physical & ~required
    if foreign_land.any():
        raise ValueError(
            f"{int(foreign_land.sum())} foreign/out-of-country physical OSM land "
            "pixels: zero sea rendering is prohibited here")
    n_land = int(required.sum())
    if n_land == 0:
        raise ValueError("Do not emit a zero-only sea Terrain-RGB tile")
    valid = np.isfinite(heights) & (heights != NODATA)
    missing = required & ~valid
    if missing.any():
        raise ValueError(
            f"{int(missing.sum())} missing true native Colombian land heights")
    if np.any(heights[required] < -10000) or np.any(heights[required] > 1667721.5):
        raise ValueError("True native land elevations exceed Terrain-RGB representable range")
    visual = np.where(required, heights, SEA_SURFACE_RENDER_M).astype(np.float64)
    rgb_image = Image.fromarray(rgb_encode(visual), mode="RGB")
    buf = io.BytesIO()
    rgb_image.save(buf, format="PNG", optimize=True)
    terrain_png = buf.getvalue()

    mask_image = Image.fromarray(np.where(required, 255, 0).astype(np.uint8), mode="L")
    buf = io.BytesIO()
    mask_image.save(buf, format="PNG", optimize=True)
    mask_png = buf.getvalue()

    decoded = decode_terrain_rgb(terrain_png)
    recovered_mask = decode_mask_png(mask_png)
    if not np.array_equal(recovered_mask, required):
        raise AssertionError("Round-trip OSM mask differs; product is not reversible")
    maximum_land_error = float(np.max(np.abs(decoded[required] - heights[required])))
    if maximum_land_error > 0.051:
        raise AssertionError(f"Original land DEM changed by {maximum_land_error}m")
    if not np.all(decoded[~required] == SEA_SURFACE_RENDER_M):
        raise AssertionError("Some sea render-only cells are not exact zero")
    if np.any(np.all(np.asarray(rgb_image) == 0, axis=2)):
        raise AssertionError("Forbidden RGB(0,0,0) produces -10000m fake trenches")
    info = {
        "policy": COAST_MODE,
        "original_valid_colombian_land_pixels": n_land,
        "render_only_OSM_sea_surface_pixels": int((~required).sum()),
        "foreign_land_pixels_encoded_as_sea": 0,
        "original_land_error_max_m": maximum_land_error,
        "auxiliary_factual_OSM_mask": "PNG grayscale (255=Colombian OSM land; 0=not Colombian OSM land)",
        "sea_surface_height_is_not_bathymetry": True,
    }
    return terrain_png, mask_png, info
