"""Offline safeguards for DIMAR ArcGIS coast/island metadata discovery."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from dimar_geoservice_discovery import (
    DIMAR_ROOT, boxes_overlap, extent_hint, list_official_services,
    normalize, scan_services, signals, source_cell, load_study_candidates,
)


class DIMARGeoServiceTests(unittest.TestCase):
    def test_source_coordinates_and_exact_candidate_registry(self):
        self.assertEqual(source_cell("Copernicus_DSM_COG_10_N01_00_W080_00_DEM"),
                         [-80, 1, -79, 2])
        self.assertEqual(source_cell("Copernicus_DSM_COG_10_N03_00_W082_00_DEM"),
                         [-82, 3, -81, 4])
        with self.assertRaises(ValueError):
            source_cell("anything_else")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "registry.json"
            f.write_text(json.dumps({
                "selected_source_cogs_still": 137,
                "cog_candidates": {"identifiers":
                    ["Copernicus_DSM_COG_10_N01_00_W080_00_DEM"]}}))
            with self.assertRaisesRegex(AssertionError, "frozen 52"):
                load_study_candidates(f)

    def test_line_is_never_a_closed_land_polygon(self):
        self.assertEqual(normalize("Línea_de_Costa"), "linea de costa")
        s = signals("Línea_de_Costa", geometry="esriGeometryPolyline")
        self.assertTrue(s["coastline_relevant"])
        self.assertEqual(s["land_mask_status"], "NOT_VALIDATED")
        self.assertEqual(s["classification"], "coastline_line_evidence_only_not_a_land_polygon")

    def test_marine_polygons_and_land_candidates_are_never_approved(self):
        s = signals("Mar territorial colombiano", geometry="esriGeometryPolygon")
        self.assertEqual(s["classification"], "marine_or_bathymetry_layer_forbid_land_mask")
        self.assertEqual(s["land_mask_status"], "NOT_VALIDATED")
        s = signals("Islas y cayos", geometry="esriGeometryPolygon")
        self.assertEqual(s["classification"], "polygon_semantics_unverified_not_a_land_mask")
        self.assertEqual(s["land_mask_status"], "NOT_VALIDATED")
        self.assertTrue(signals("Playas de Colombia")["coastline_relevant"])

    def test_extent_is_only_bbox_hint_not_positive_land_overlap(self):
        target={"tumaco": [-80,1,-79,2], "malpelo": [-82,3,-81,4]}
        info={"fullExtent": {"xmin": -80.2,"ymin": 1.2,"xmax": -79.3,"ymax": 2.5,
                             "spatialReference": {"latestWkid": 4326}}}
        result=extent_hint(info,target)
        self.assertEqual(result["candidate_cog_bbox_hints"], ["tumaco"])
        self.assertTrue(result["bbox_hints_are_not_polygon_or_land_intersections"])
        no_crs={"fullExtent": {"xmin": -9000000,"ymin":1000000,"xmax":-8000000,
                               "ymax":2000000,"spatialReference":{"wkid":3857}}}
        self.assertFalse(extent_hint(no_crs,target)["comparable"])
        self.assertFalse(boxes_overlap([-80,1,-79,2], [-79,1,-78,2]))

    def test_official_folder_listing_and_layer_metadata_are_review_only(self):
        def fake_api(session,url,params=None,timeout=18):
            if url==DIMAR_ROOT:
                return {"folders":["Litorales"],"services":[
                    {"name":"General","type":"MapServer"}]}
            if url==DIMAR_ROOT+"/Litorales":
                return {"services":[{"name":"Litorales/Linea_Costa",
                                     "type":"FeatureServer"}]}
            if url==DIMAR_ROOT+"/Litorales/Linea_Costa/FeatureServer":
                return {"layers":[{"name":"Línea de costa","id":0}]}
            if url==DIMAR_ROOT+"/Litorales/Linea_Costa/FeatureServer/0":
                return {"geometryType":"esriGeometryPolyline",
                        "supportedQueryFormats":"JSON, geoJSON",
                        "extent":{"xmin":-82,"ymin":3,"xmax":-80,"ymax":5,
                                  "spatialReference":{"wkid":4326}}}
            if url==DIMAR_ROOT+"/General/MapServer":
                return {"layers":[{"id":0,"name":"Other"}]}
            raise AssertionError(f"unexpected ArcGIS URL {url}")
        import dimar_geoservice_discovery as d
        from unittest.mock import patch
        with patch.object(d,"api_json",side_effect=fake_api):
            services,folders,errors=list_official_services(Mock())
            layers,errs=scan_services(Mock(),services,DIMAR_ROOT,
                                      {"malpelo":[-82,3,-81,4]})
        self.assertEqual(folders,["Litorales"])
        self.assertEqual(len(services),2)
        self.assertFalse(errors)
        self.assertFalse(errs)
        self.assertEqual(len(layers),1)
        self.assertEqual(layers[0]["geometry_type"],"esriGeometryPolyline")
        self.assertEqual(layers[0]["land_mask_status"],"NOT_VALIDATED")
        self.assertTrue(layers[0]["no_geometry_downloaded"])
        self.assertEqual(layers[0]["extent_candidate_cell_hints_only"]
                         ["candidate_cog_bbox_hints"], ["malpelo"])


if __name__=="__main__":
    unittest.main()
