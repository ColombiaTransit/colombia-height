"""OSM-only source scope, true original native OSM-land counts and no sea fill."""
import sys
import unittest
from pathlib import Path

from shapely.geometry import Point, box

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from osm_only_colombia_land_finish import (
    tile_osm_context, categorize, candidate_tiles, geometry_candidates,
    region_bbox,
)
from official_territory_screen import xyz_geometry


class OSMOnlyColombiaLandTests(unittest.TestCase):
    def tile(self):
        return (13,2280,4055)

    def test_non_osm_col_relation_tile_is_not_claimed_colombian_land(self):
        rect=xyz_geometry(*self.tile())
        b=rect.bounds
        col=box(b[0]+1,b[1]+1,b[2]+2,b[3]+2)
        g=tile_osm_context(self.tile(),col,[],[],[])
        self.assertEqual(g["OSM_COL_country_relation_tile_context"],
                         "disjoint_OSM_Colombia_relation")
        self.assertTrue(g["no_coastline_or_named_island_in_tile_does_NOT_certify_ocean"])
        self.assertFalse(g["actual_missing_pixels_inside_OSM_land_proven"])

    def test_full_country_relation_is_not_coastline_proof(self):
        b=xyz_geometry(*self.tile()).bounds
        country=box(b[0]-.1,b[1]-.1,b[2]+.1,b[3]+.1)
        g=tile_osm_context(self.tile(),country,[],[],[])
        self.assertEqual(g["OSM_COL_country_relation_tile_context"],
                         "complete_OSM_Colombia_relation_coverage_tile")
        self.assertFalse(g["actual_missing_pixels_inside_OSM_land_proven"])

    def test_closed_coastline_counterclockwise_land_only(self):
        ccw=[(-79,1),(-78.9,1),(-78.9,1.1),(-79,1.1),(-79,1)]
        cw=list(reversed(ccw))
        el=[{"type":"way","id":1,"tags":{"natural":"coastline"},
             "geometry":[{"lon":x,"lat":y} for x,y in ccw]},
            {"type":"way","id":2,"tags":{"natural":"coastline"},
             "geometry":[{"lon":x,"lat":y} for x,y in cw]}]
        lines,land,isles,hints=geometry_candidates(el)
        self.assertEqual(len(lines),2)
        self.assertEqual(len(land),1)
        self.assertEqual(len(isles),0)

    def test_existing_previous_safeguarded_registry_is_exactly_27_plus_68(self):
        root=Path(__file__).resolve().parents[1]/"data"
        old=__import__("json").loads((root/"staged140-residual-geography-2026-11-14.json").read_text())
        new=__import__("json").loads((root/"tumaco140-new-tiles-geo-reference-2026-11-14.json").read_text())
        older,added=candidate_tiles(old,new)
        self.assertEqual(len(older),27)
        self.assertEqual(len(added),68)
        self.assertEqual(sum(x["old_140_native_missing_pixels"] for x in added),2688103)
        self.assertEqual(sum(x["old_140_OSM_land_native_missing_pixels"] for x in older),394622)
        west,south,east,north=region_bbox(added)
        self.assertGreater(east,west)
        self.assertGreater(north,south)
        self.assertLess(east-west,2)
        self.assertLess(north-south,2)


if __name__=="__main__":
    unittest.main()
