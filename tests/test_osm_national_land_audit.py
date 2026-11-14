"""Offline safety/unit tests for OSMCoastline native DEM comparison."""
import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

import numpy as np
import shapefile
from shapely.geometry import GeometryCollection, LineString, Polygon, box

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from osm_land_reference import (
    DOWNLOAD, STUDY_BBOX, clip_split_polygons, load_clip, polygon_parts,
    safe_extract_shapefile, validate_download_url, write_clip,
)
from osm_national_land_audit import (
    PolygonMask, cell_pixel_counts, classify_candidate, exact_categories,
)


class OSMLandReferenceTests(unittest.TestCase):
    def test_osm_shapefile_must_have_fixed_upstream_url(self):
        self.assertEqual(validate_download_url(DOWNLOAD), DOWNLOAD)
        with self.assertRaises(ValueError):
            validate_download_url("http://localhost/osm.zip")
        self.assertEqual(STUDY_BBOX, (-84, -5, -66, 17))

    def test_polygon_parts_cannot_convert_lines_into_land(self):
        parts=polygon_parts(GeometryCollection([
            LineString([(0,0),(1,1)]),box(0,0,1,1)]))
        self.assertEqual(len(parts),1)
        self.assertEqual(parts[0].area,1)
        self.assertEqual(polygon_parts(LineString([(0,0),(2,2)])),[])

    def test_end_to_end_clip_from_valid_mock_shapefile_and_sha(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with shapefile.Writer(str(root/"land_polygons"),shapeType=shapefile.POLYGON) as w:
                w.field("name", "C")
                w.poly([[[-79,6],[-70,6],[-70,2],[-79,2],[-79,6]]])
                w.record("synthetic Colombian mainland")
                w.poly([[[-20,6],[-19,6],[-19,5],[-20,5],[-20,6]]])
                w.record("unrelated distant land")
            zip_path=root/"sample.zip"
            with ZipFile(zip_path,"w") as z:
                for ext in (".shp",".shx",".dbf"):
                    z.write(root/("land_polygons"+ext),arcname="land-polygons-split-4326/land_polygons"+ext)
            shp=safe_extract_shapefile(zip_path,root/"unpack")
            shapes,scanned=clip_split_polygons(shp)
            self.assertEqual(len(shapes),1)
            self.assertGreater(scanned,0)
            meta=write_clip(shapes,{"sha256":"abc123","size_bytes":200000},
                            root/"reference")
            self.assertFalse(meta["national_publication_allowed"])
            self.assertIn("OpenStreetMap",meta["odbl_attribution"])
            self.assertEqual(len(load_clip(root/"reference"/"osm-land-study.wkb.gz",
                                          meta["reference_wkb_sha256"])),1)
            with self.assertRaisesRegex(ValueError,"SHA256"):
                load_clip(root/"reference"/"osm-land-study.wkb.gz","bad")

    def test_masks_align_and_split_polygon_overlaps_do_not_double_count(self):
        lon=np.full((256,256), -78.76)
        lat=np.full((256,256), 1.81)
        lon[0,0]=-76.0
        lat[0,0]=10
        from official_territory_screen import xyz_geometry
        import mercantile
        tile=mercantile.tile(-78.76,1.81,11)
        mask=PolygonMask([box(-78.78,1.79,-78.74,1.83),
                          box(-78.77,1.8,-78.75,1.82)])
        out=mask.mask((11,tile.x,tile.y),lon,lat)
        self.assertEqual(out.shape,(256,256))
        self.assertEqual(out.sum(),65535)

    def test_disjoint_native_missing_osm_land_and_unknown(self):
        valid=np.ones((256,256),bool)
        osm=valid.copy()
        igac=np.zeros((256,256),bool)
        ne=np.zeros((256,256),bool)
        gb=np.zeros((256,256),bool)
        valid[1,1:5]=False
        osm[1,4]=False
        igac[1,1:3]=True
        ne[1,3]=True
        row=exact_categories(valid,osm,igac,ne,gb)
        self.assertEqual(row["native_missing_dem_pixels"],4)
        self.assertEqual(row["missing_inside_osm_land"],3)
        self.assertEqual(row["missing_outside_osm_land_UNKNOWN_not_confirmed_ocean"],1)
        self.assertEqual(row["missing_osm_land_and_igac_department"],2)
        self.assertEqual(row["missing_osm_land_outside_igac_department"],1)
        self.assertEqual(row["missing_osm_land_outside_igac_and_natural_earth"],0)

    def test_candidate_cog_only_counts_exact_missing_native_pixels(self):
        name="Copernicus_DSM_COG_10_N01_00_W080_00_DEM"
        lon=np.full((256,256),-79.5)
        lat=np.full((256,256),1.5)
        missing=np.zeros((256,256),bool)
        missing[0,0:2]=True
        osm=np.zeros((256,256),bool)
        osm[0,0]=True
        igac=osm.copy()
        values=cell_pixel_counts(missing,osm,igac,lon,lat,[name])
        self.assertEqual(values[name]["native_missing_pixel_cell_hits"],2)
        self.assertEqual(values[name]["osm_land_missing_pixel_cell_hits"],1)
        self.assertEqual(values[name]["outside_osm_missing_cell_hits_UNKNOWN"],1)
        self.assertFalse(values[name]["eligible_for_automatic_inclusion"])
        self.assertTrue(classify_candidate(values[name]).startswith("A_"))
        with self.assertRaisesRegex(AssertionError,"no actual missing"):
            cell_pixel_counts(np.zeros_like(missing),osm,igac,lon,lat,[name])


if __name__=="__main__":
    unittest.main()
