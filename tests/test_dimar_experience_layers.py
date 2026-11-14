"""Offline tests: follow only published public ArcGIS URLs from DIMAR app."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from dimar_experience_layers import crawl_refs, public_arcgis_url, service_reference


class DIMARExperienceTests(unittest.TestCase):
    def test_service_links_are_read_only_known_public_arcgis_hosts(self):
        url="https://services6.arcgis.com/RB7c27NVd25mjSSc/arcgis/rest/services/Test/FeatureServer/0"
        self.assertEqual(service_reference(url),url)
        self.assertIsNone(service_reference("http://services6.arcgis.com/x/FeatureServer"))
        self.assertIsNone(service_reference("https://127.0.0.1/x/MapServer"))
        self.assertIsNone(service_reference("https://evil.com/x/MapServer"))
        self.assertIsNone(service_reference(url+"?token=secret"))
        self.assertIsNone(service_reference("https://services6.arcgis.com/x/MapServer/query"))

    def test_extract_only_public_links_and_known_item_ids(self):
        d={"dataSources":{"abc":{
            "itemId":"0123456789abcdef0123456789abcdef",
            "url":"https://services5.arcgis.com/abc/arcgis/rest/services/Geomorfologia/FeatureServer",
            "credentials":"secret",
            "bad":"https://localhost/admin/FeatureServer"
        }},"items":[{"webMapId":"abcdef0123456789abcdef0123456789",
                      "url":"https://other.com/notallowed/MapServer"}]}
        ids,services=crawl_refs(d)
        self.assertEqual(ids,["0123456789abcdef0123456789abcdef",
                              "abcdef0123456789abcdef0123456789"])
        self.assertEqual(services,[
            "https://services5.arcgis.com/abc/arcgis/rest/services/Geomorfologia/FeatureServer"])

    def test_lone_coastline_or_marine_polygons_cannot_authorize_mask(self):
        # The metadata probe never makes land decisions; even a coastline
        # app linking valid data remains a research input.
        ids,urls=crawl_refs({"url":"https://ide.dimar.mil.co/server/rest/services/coast/MapServer"})
        self.assertEqual(ids,[])
        self.assertEqual(len(urls),1)


if __name__=="__main__":unittest.main()
