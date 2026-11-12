#!/usr/bin/env python3
"""Fail-closed MBTiles merge: reject duplicate z/x/y ownership across regions."""
import argparse
import json
import sqlite3
from pathlib import Path

def merge_mbtiles(inputs, output):
    inputs=[Path(p) for p in inputs]
    output=Path(output)
    if len(inputs)<2:
        raise ValueError("At least two regional files required")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(output)
    try:
        db.execute("CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT)")
        db.execute("CREATE TABLE tiles(zoom_level INTEGER,tile_column INTEGER,tile_row INTEGER,tile_data BLOB, PRIMARY KEY(zoom_level,tile_column,tile_row))")
        entries=0
        minzoom=99
        maxzoom=-1
        for index,path in enumerate(inputs):
            with sqlite3.connect(f"file:{path.resolve()}?mode=ro",uri=True) as src:
                form=src.execute("SELECT value FROM metadata WHERE name='format'").fetchone()
                if form is None or form[0]!="png":
                    raise ValueError(f"Unsupported data format in {path}")
                z0=src.execute("SELECT MIN(zoom_level),MAX(zoom_level) FROM tiles").fetchone()
                if z0[0] is None:
                    raise ValueError(f"Empty source MBTiles {path}")
                minzoom=min(minzoom,z0[0]);maxzoom=max(maxzoom,z0[1])
                for record in src.execute("SELECT zoom_level,tile_column,tile_row,tile_data FROM tiles"):
                    try:
                        db.execute("INSERT INTO tiles VALUES(?,?,?,?)",record)
                    except sqlite3.IntegrityError as e:
                        raise ValueError(f"Duplicate z/x/TMS-y key {record[:3]} in {path}; partition tile ownership first") from e
                    entries+=1
        db.executemany("INSERT INTO metadata VALUES(?,?)", [
            ("name","Colombia Terrain RGB regional merge"),("format","png"),
            ("type","baselayer"),("version","1.0"),("minzoom",str(minzoom)),("maxzoom",str(maxzoom)),
            ("attribution","Contains modified Copernicus DEM data"),
        ])
        db.commit()
        if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
            raise ValueError("Corrupted resulting SQLite")
        return {"inputs":[str(i) for i in inputs],"tiles":entries,"bytes":output.stat().st_size,
                "minzoom":minzoom,"maxzoom":maxzoom}
    except BaseException:
        db.close()
        output.unlink(missing_ok=True)
        raise
    finally:
        db.close()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("inputs",nargs="+",type=Path)
    args=parser.parse_args()
    print(json.dumps(merge_mbtiles(args.inputs,args.output),indent=2))
if __name__=="__main__":
    main()
