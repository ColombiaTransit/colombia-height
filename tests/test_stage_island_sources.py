"""Fail-closed source selection requires exact two native island COGs and QA evidence."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from stage_island_sources import ALLOWLIST, approved_sources, construct_staging_rows


class TwoIslandStagingTests(unittest.TestCase):
    def reviewed(self):
        return {
            "decision":"allow_exactly_two_verified_COGs_in_separate_reproducible_staging_manifest_only",
            "original_source_count":137,
            "staging_source_count":139,
            "selected_production_source_count_unchanged":137,
            "staged_added_source_count":2,
            "evidence_runs":{
                "island_exact_osm_pixel_recovery":43594868906,
                "minor_islands_and_multi_zoom_cog_seams":43596436204,
                "original_native_30m_source_border":43596823989,
            },
            "staging_constraints":{
                "national_terrain_rgb_publication_allowed":False,
                "quitasueno_explicitly_excluded":True,
                "only_sources_in_explicit_allowlist":True,
                "no_synthetic_ocean_or_height_fill":True,
            },
            "sources":[{
                "name":name,"site":site,
                "source_cell":{"latitude":lat,"longitude":lon},
                "decision_status":"staging_only_approved_not_production",
                "geographic_identity_primary_official":"https://www.parquesnacionales.gov.co/nuestros-parques/park/",
                "native_30m_disproportionate_gt40m_flags":0,
                "source_transition_missing_adjacent_pairs":0,
                "previously_valid_dem_height_max_change_m":0,
                "original_exact_OSM_island_gap_pixels":97,
                "real_native_COG_pixel_gaps_restored":97,
                "native_30m_boundary_samples":350,
            } for name,(lat,lon,site) in ALLOWLIST.items()],
        }

    def test_two_reviewed_original_cogs_accepted_only_for_staging(self):
        approved=approved_sources(self.reviewed())
        self.assertEqual(set(x["name"] for x in approved),set(ALLOWLIST))

    def test_tampered_native_gradient_flags_block_stage(self):
        r=self.reviewed()
        r["sources"][1]["native_30m_disproportionate_gt40m_flags"]=5
        with self.assertRaisesRegex(AssertionError,"not satisfied"):
            approved_sources(r)

    def test_release_permission_cannot_be_true(self):
        r=self.reviewed()
        r["staging_constraints"]["national_terrain_rgb_publication_allowed"]=True
        with self.assertRaisesRegex(AssertionError,"release gates"):
            approved_sources(r)

    def test_missing_audit_run_rejected(self):
        r=self.reviewed()
        r["evidence_runs"]["original_native_30m_source_border"]=0
        with self.assertRaisesRegex(AssertionError,"provenance"):
            approved_sources(r)

    def test_unreviewed_third_cog_rejected(self):
        r=self.reviewed()
        r["sources"].append(dict(r["sources"][0],name="not_approved"))
        with self.assertRaisesRegex(AssertionError,"allowlist"):
            approved_sources(r)

    def test_original_137_order_and_source_integrity_preserved(self):
        original=[{"name":f"original_{i:03d}","latitude":"0","longitude":str(i),
                   "size_bytes":"100","status":"ok","url":f"https://example.org/original_{i:03d}.tif"}
                  for i in range(137)]
        additions=[{"name":name,"latitude":str(lat),"longitude":str(lon),
                    "size_bytes":"1234","status":"ok",
                    "url":f"https://example.org/{name}.tif"}
                   for name,(lat,lon,site) in ALLOWLIST.items()]
        staged=construct_staging_rows(original,additions)
        self.assertEqual(len(staged),139)
        self.assertEqual(len({r["name"] for r in staged}),139)
        self.assertEqual(len(original),137)
        self.assertEqual([s["name"] for s in staged[:137]], [s["name"] for s in original])
        self.assertEqual({s["name"] for s in staged[137:]}, set(ALLOWLIST))
        self.assertFalse(any(s["name"] in ALLOWLIST for s in original))

    def test_candidate_with_invalid_s3_size_rejected(self):
        original=[{"name":f"original_{i:03d}","latitude":"0","longitude":str(i),
                   "status":"ok"} for i in range(137)]
        additions=[{"name":name,"latitude":str(lat),"longitude":str(lon),
                    "size_bytes":"","status":"ok",
                    "url":f"https://example.org/{name}.tif"}
                   for name,(lat,lon,site) in ALLOWLIST.items()]
        with self.assertRaisesRegex(AssertionError,"not verified"):
            construct_staging_rows(original,additions)


if __name__=="__main__":
    unittest.main()
