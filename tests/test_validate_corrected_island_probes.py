"""Offline closed-OSM-coastline validation tests: island probes never create land."""
import sys
import unittest
from pathlib import Path

from shapely.geometry import Point

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_corrected_island_probes import (
    bbox_for_probes, parse_osm_coastline_xml, check_candidate,
)


class CorrectedIslandProbeTests(unittest.TestCase):
    def test_small_island_ring_contains_sourced_probe(self):
        osm = b"""<osm version="0.6">
        <node id="1" lat="13.38" lon="-81.38"/>
        <node id="2" lat="13.38" lon="-81.37"/>
        <node id="3" lat="13.39" lon="-81.37"/>
        <node id="4" lat="13.39" lon="-81.38"/>
        <way id="20391863">
          <nd ref="1"/><nd ref="2"/><nd ref="3"/><nd ref="4"/><nd ref="1"/>
          <tag k="natural" v="coastline"/><tag k="place" v="island"/>
        </way></osm>"""
        polygons, ids = parse_osm_coastline_xml(osm, [-81.39, 13.37, -81.36, 13.40])
        self.assertEqual(ids, ["20391863"])
        self.assertEqual(len(polygons), 1)
        self.assertIsNotNone(check_candidate(polygons, -81.37467, 13.38798))
        self.assertIsNone(check_candidate(polygons, -81.40, 13.38798))

    def test_island_name_or_label_only_does_not_make_land(self):
        osm = b"""<osm version="0.6">
        <node id="1" lat="2.94" lon="-78.21">
          <tag k="place" v="island"/><tag k="name" v="Gorgonilla"/>
        </node></osm>"""
        polygons, ids = parse_osm_coastline_xml(osm, [-78.23, 2.92, -78.19, 2.96])
        self.assertFalse(polygons)
        self.assertFalse(ids)

    def test_open_coastline_cannot_be_used_as_land(self):
        osm = b"""<osm version="0.6">
        <node id="1" lat="2.93" lon="-78.22"/>
        <node id="2" lat="2.94" lon="-78.21"/>
        <node id="3" lat="2.94" lon="-78.22"/>
        <way id="123"><nd ref="1"/><nd ref="2"/><nd ref="3"/>
          <tag k="natural" v="coastline"/>
        </way></osm>"""
        polygons, ids = parse_osm_coastline_xml(osm, [-78.23, 2.92, -78.20, 2.95])
        self.assertEqual(len(polygons), 0)
        self.assertEqual(ids, ["123"])

    def test_bbox_cannot_be_unbounded(self):
        with self.assertRaises(ValueError):
            bbox_for_probes([{"lon": -81.1, "lat": 13.2},
                             {"lon": -81.3, "lat": 13.2}], pad=.01)
        bbox = bbox_for_probes([{"lon":-81.37467,"lat":13.38798},
                                {"lon":-81.3789802,"lat":13.3846833}])
        self.assertLess(bbox[0],-81.3808804)
        self.assertGreater(bbox[2],-81.3684559)
        self.assertLess(bbox[1],13.3814495)
        self.assertGreater(bbox[3],13.3945076)


if __name__=="__main__":
    unittest.main()
