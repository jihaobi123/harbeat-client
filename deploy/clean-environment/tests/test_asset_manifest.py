import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "tools" / "build_asset_manifest.py"
SPEC = importlib.util.spec_from_file_location("build_asset_manifest", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AssetManifestTest(unittest.TestCase):
    def test_manifest_is_deterministic_and_excludes_named_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "b").mkdir()
            (root / "skip").mkdir()
            (root / "b" / "two.bin").write_bytes(b"two")
            (root / "one.bin").write_bytes(b"one")
            (root / "skip" / "ignored.bin").write_bytes(b"ignored")

            manifest = MODULE.build_manifest(root, {"skip"})

            self.assertEqual(
                [item["relative_path"] for item in manifest["assets"]],
                ["one.bin", "b/two.bin"],
            )
            self.assertEqual(manifest["file_count"], 2)
            self.assertEqual(manifest["total_size_bytes"], 6)
            self.assertEqual(
                manifest["assets"][0]["sha256"], hashlib.sha256(b"one").hexdigest()
            )
            json.dumps(manifest)


if __name__ == "__main__":
    unittest.main()
