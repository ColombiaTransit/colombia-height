"""Offline tests for provenance-safe discovery of DIMAR ArcGIS Hub datasets."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from dimar_hub_discovery import HUB_URL, OFFICIAL_LINKED_EXPERIENCE_ID, experience_identity, portal_identity_from_items, shortlist


class DIMARHubTests(unittest.TestCase):
    def test_same_keyword_cannot_steal_dimar_organization_identity(self):
        entries=[
          {"url":"https://fake.hub.arcgis.com","orgId":"FAKE","type":"Hub Site Application"},
          {"url":HUB_URL, "type":"Feature Service","orgId":"NOT_SITE"},
          {"url":HUB_URL + "/", "type":"Hub Site Application","orgId":"DIMAR_ORG",
           "owner":"owner_d","id":"abc"},
        ]
        result=portal_identity_from_items(entries)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["org_id"],"DIMAR_ORG")

    def test_only_verified_hub_org_gets_same_org_provenance(self):
        identity=[{"org_id":"DIMAR_ORG","url":HUB_URL,"item_id":"abc"}]
        items=[
            {"id":"1","title":"Línea de Costa","type":"Feature Service",
             "orgId":"DIMAR_ORG","owner":"a"},
            {"id":"2","title":"Línea de Costa","type":"Feature Service",
             "orgId":"other","owner":"notdimar","tags":["DIMAR"]},
            {"id":"3","title":"Porto statistics","type":"Feature Service",
             "orgId":"DIMAR_ORG"},
        ]
        records=shortlist(items,identity)
        self.assertEqual(len(records),2)
        self.assertEqual(records[0]["provenance"],
             "ARCGIS_ORG_MATCH_TO_OFFICIAL_DIMAR_HUB_SITE")
        self.assertEqual(records[1]["provenance"],
             "ARCGIS_SEARCH_ONLY_PUBLISHER_UNVERIFIED")
        self.assertTrue(all(x["land_mask_status"]=="NOT_VERIFIED_NO_GEOMETRY" for x in records))

    def test_no_identity_means_no_official_datasets_even_named_dimar(self):
        data=[{"id":"a", "title":"DIMAR islas", "type":"Feature Service",
               "orgId":"any", "tags":["DIMAR"]}]
        records=shortlist(data,[])
        self.assertEqual(len(records),1)
        self.assertTrue(records[0]["provenance"].endswith("UNVERIFIED"))

    def test_direct_dimar_portal_linked_experience_proves_org_lead(self):
        class Response:
            def raise_for_status(self):
                return None
            def json(self):
                return {"id":OFFICIAL_LINKED_EXPERIENCE_ID,
                        "orgId":"RB7c27NVd25mjSSc","owner":"esricol_DIMAR"}
        class Session:
            def get(self, url, **kwargs):
                self.url=url
                return Response()
        session=Session()
        identity=experience_identity(session)
        self.assertEqual(identity[0]["org_id"],"RB7c27NVd25mjSSc")
        self.assertIn(OFFICIAL_LINKED_EXPERIENCE_ID,session.url)

    def test_conflicting_organization_identity_fails_closed(self):
        entries=[{"url":HUB_URL,"orgId":"A","type":"Hub Site Application"},
                 {"url":HUB_URL,"orgId":"B","type":"Hub Site Application"}]
        with self.assertRaisesRegex(RuntimeError,"Conflicting"):
            portal_identity_from_items(entries)


if __name__ == "__main__":
    unittest.main()
