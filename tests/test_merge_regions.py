import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from merge_regions import merge_mbtiles

def create(path,xy):
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE metadata(name TEXT,value TEXT)")
        c.execute("INSERT INTO metadata VALUES('format','png')")
        c.execute("CREATE TABLE tiles(zoom_level INTEGER,tile_column INTEGER,tile_row INTEGER,tile_data BLOB)")
        c.execute("INSERT INTO tiles VALUES(13,?,?,?)", (xy,200,b'valid png marker placeholder'))

class OwnershipTests(unittest.TestCase):
    def test_nonoverlap_merges(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            create(p/'a.mbtiles',1);create(p/'b.mbtiles',2)
            output=p/'c.mbtiles'
            result=merge_mbtiles([p/'a.mbtiles',p/'b.mbtiles'],output)
            self.assertEqual(result['tiles'],2)
    def test_duplicate_tile_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            create(p/'a.mbtiles',1);create(p/'b.mbtiles',1)
            output=p/'c.mbtiles'
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                merge_mbtiles([p/'a.mbtiles',p/'b.mbtiles'],output)
            self.assertFalse(output.exists())

if __name__=="__main__":
    unittest.main()
