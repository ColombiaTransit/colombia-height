#!/usr/bin/env python3
"""Strict OSM-land-only GLO-30 DEM validity gate.

Only OSM physical land (assembled natural=coastline land polygons) within
the OSM Colombia country boundary requires terrain elevations. All other
pixels are OUT OF SCOPE, never silently assigned an elevation of 0 m.

IMPORTANT: This module validates land masks, but does NOT render PNGs or
claim MapLibre/TileServer GL transparency compatibility. Mixed land/ocean
tiles remain a release-gate problem until the output encoder is tested.
"""
import numpy as np

NODATA=-9999.0
PIXELS_PER_TILE=256*256


def verify_osm_land_only_native_dem(
        native_heights, osm_physical_land_mask, osm_colombia_country_mask,
        nodata=NODATA, fail_on_missing=True):
    """Audit exactly what the project has chosen to publish.

    The OSM coastline mask MUST represent assembled OSM land polygon
    interiors; no OSM country relation (which may cover marine areas) and
    no presence of an island label can substitute for physical land.
    The Colombia mask MUST be from the OSM admin=2 relation, NOT bounding
    boxes of selected COGs, geoBoundaries or maritime sea-level masks.

    Missing elevations over OSM sea/unknown pixels do NOT block source
    land coverage, but those pixel values must not be encoded as terrain.
    The output renderer must handle alpha/missing semantics separately.
    """
    heights=np.asarray(native_heights)
    land=np.asarray(osm_physical_land_mask)
    colombia=np.asarray(osm_colombia_country_mask)
    if not (heights.shape==land.shape==colombia.shape==(256,256)):
        raise ValueError("Exactly aligned 256x256 XYZ native DEM and two OSM masks required")
    if land.dtype!=np.dtype("bool") or colombia.dtype!=np.dtype("bool"):
        raise TypeError("Only positive pixel-accurate boolean OSM land/country masks are accepted")
    required=land & colombia
    valid=np.isfinite(heights) & (heights!=nodata)
    missing=required & ~valid
    required_count=int(np.count_nonzero(required))
    gap_count=int(np.count_nonzero(missing))
    if required_count==0:
        state="skip_tile_no_OSM_Colombia_physical_land"
    elif gap_count:
        state="blocked_missing_native_elevation_on_OSM_Colombia_land"
    else:
        state="all_required_OSM_Colombia_land_pixels_have_valid_native_heights"
    report={
        "land_only_gate":state,
        "OSM_Colombia_physical_land_pixel_centers":required_count,
        "OSM_Colombia_land_pixels_missing_real_native_elevation":gap_count,
        "native_valid_pixel_centers_on_required_OSM_land":required_count-gap_count,
        "not_required_pixels_outside_OSM_Colombia_physical_land":PIXELS_PER_TILE-required_count,
        "marine_bathymetry_study_required":False,
        "unknown_or_ocean_pixels_forbidden_as_synthetic_terrain":True,
        "emit_entirely_ocean_tile":False,
        "ready_for_native_source_land_only_export":bool(required_count and not gap_count),
        "mixed_coast_tile_renderer_alpha_semantics_still_need_validation":bool(
            required_count and required_count<PIXELS_PER_TILE),
    }
    if gap_count and fail_on_missing:
        raise ValueError(
            f"Refuse to export: {gap_count} original Copernicus DEM NoData "
            "pixel centers intersect OSM physical Colombian land")
    return report,required.copy()


def require_renderer_for_mixed_coast_tile(report, transparent_mixed_tile_encoder_verified):
    """Prevent a false -10000m trench when a raster-dem renderer ignores alpha."""
    if report["land_only_gate"]=="blocked_missing_native_elevation_on_OSM_Colombia_land":
        raise RuntimeError("Missing physical Colombian land heights must block output")
    if (report["mixed_coast_tile_renderer_alpha_semantics_still_need_validation"]
            and transparent_mixed_tile_encoder_verified is not True):
        raise RuntimeError("Mixed OSM land/sea tile cannot be published until renderer NoData/alpha behavior is independently verified")
    return report["ready_for_native_source_land_only_export"]
