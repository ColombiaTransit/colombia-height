"""No-network installer contract; verify streamed part and full SHA-256 before atomic install."""
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.install_terrain_release import download_url, install


class TestInstallTerrainRelease(unittest.TestCase):
    def setUp(self):
        self.blocks = [b"part0\x00", b"part1\x01", b"part2\x02"]
        joined = b"".join(self.blocks)
        self.manifest = {
            "schema": "colombiatransit-terrain-rgb-release-v1",
            "release_version": "v1.0.0",
            "format": {"container": "SQLite MBTiles", "zoom_max": 13},
            "parts": [
                {"file": f"colombia-terrain.mbtiles.part-{i:03d}",
                 "bytes": len(chunk),
                 "sha256": hashlib.sha256(chunk).hexdigest()}
                for i,chunk in enumerate(self.blocks)
            ],
            "merged_mbtiles_bytes": len(joined),
            "merged_mbtiles_sha256": hashlib.sha256(joined).hexdigest(),
        }

    def test_tag_urls_are_stable_and_pinned(self):
        self.assertEqual(
            download_url("latest","colombia-terrain.manifest.json"),
            "https://github.com/ColombiaTransit/colombia-height/releases/latest/download/colombia-terrain.manifest.json")
        self.assertEqual(
            download_url("v1.0.0","colombia-terrain.mbtiles.part-000"),
            "https://github.com/ColombiaTransit/colombia-height/releases/download/v1.0.0/colombia-terrain.mbtiles.part-000")
        with self.assertRaises(ValueError):
            download_url("main","anything")

    def test_installer_streams_verifies_reuses_and_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest=Path(tmpdir)/"colombia-terrain.mbtiles"
            def fake_retrieve(url):
                index=int(url.rsplit("-",1)[1])
                return io.BytesIO(self.blocks[index])
            with patch("scripts.install_terrain_release.load_manifest",
                       return_value=self.manifest),patch(
                       "scripts.install_terrain_release.retrieve",
                       side_effect=fake_retrieve) as fetch:
                install("v1.0.0",dest)
                self.assertEqual(dest.read_bytes(),b"".join(self.blocks))
                self.assertEqual(fetch.call_count,3)
                install("v1.0.0",dest)
                self.assertEqual(fetch.call_count,3)
                dest.write_bytes(b"local protected existing content")
                with self.assertRaises(FileExistsError):
                    install("v1.0.0",dest)
                self.assertEqual(dest.read_bytes(),b"local protected existing content")
                install("v1.0.0",dest,replace=True)
                self.assertEqual(dest.read_bytes(),b"".join(self.blocks))

    def test_corrupt_download_cannot_publish_partial_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest=Path(tmpdir)/"colombia-terrain.mbtiles"
            def fake_retrieve(url):
                index=int(url.rsplit("-",1)[1])
                return io.BytesIO(b"WRONG" if index==1 else self.blocks[index])
            with patch("scripts.install_terrain_release.load_manifest",
                       return_value=self.manifest),patch(
                       "scripts.install_terrain_release.retrieve",
                       side_effect=fake_retrieve):
                with self.assertRaises(ValueError):
                    install("latest",dest)
                self.assertFalse(dest.exists())
                self.assertEqual(list(dest.parent.glob("*.incomplete")),[])


if __name__=="__main__":
    unittest.main()
