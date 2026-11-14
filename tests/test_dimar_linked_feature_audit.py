"""No-network safeguards for linked DIMAR field metadata and count-only queries."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from dimar_linked_feature_audit import SOURCES, SITE_WINDOWS, build_query, inspect


class DIMARLinkedFeatureTests(unittest.TestCase):
    def test_fixed_queries_are_count_only(self):
        q=build_query([-81.66,3.96,-81.55,4.06])
        self.assertEqual(q["returnCountOnly"],"true")
        self.assertEqual(q["geometryType"],"esriGeometryEnvelope")
        self.assertEqual(q["inSR"],"4326")
        self.assertNotIn("outFields",q)
        with self.assertRaises(ValueError):
            build_query([0,0,0,1])

    def test_untrusted_layer_urls_not_fetched(self):
        with self.assertRaises(ValueError):
            inspect(None,"fake","http://localhost/private/FeatureServer/0")

    def test_geomorphology_polygon_not_approved_as_land(self):
        url=SOURCES["rasgos_geomorfologicos"]
        def response(session,u,params):
            if u==url:
                return {"name":"Rasgos_geomorfologicos",
                        "geometryType":"esriGeometryPolygon",
                        "fields":[{"name":"ObjectID","type":"esriFieldTypeOID"}],
                        "capabilities":"Query"}
            self.assertEqual(u,url+"/query")
            self.assertEqual(params["returnCountOnly"],"true")
            return {"count":0}
        with patch("dimar_linked_feature_audit.request_json",side_effect=response):
            result=inspect(None,"rasgos_geomorfologicos",url)
        self.assertEqual(result["metadata_status"],"readable")
        self.assertFalse(result["production_land_mask_verified"])
        self.assertTrue(result["no_emerged_land_polygon_inferred"])
        self.assertEqual(set(result["site_window_counts"]),set(SITE_WINDOWS))
        self.assertTrue(all(v["intersecting_feature_count"]==0 for v in
                            result["site_window_counts"].values()))


if __name__=="__main__":
    unittest.main()
