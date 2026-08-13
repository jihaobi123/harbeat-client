import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from harbeat_library_catalog.manifest import AssetManifest, ManifestError

FIXTURE = Path(__file__).parent / "fixtures" / "manifest.json"

class ManifestTests(unittest.TestCase):
  def test_parses_deployed_manifest_shape(self):
    manifest = AssetManifest.from_api(json.loads(FIXTURE.read_text(encoding="utf-8")), "lib-a")
    self.assertEqual(manifest.library_song_id, "lib-a")
    self.assertEqual(manifest.original.format, "wav")

  def test_rejects_request_manifest_identity_mismatch(self):
    with self.assertRaises(ManifestError):
      AssetManifest.from_api(json.loads(FIXTURE.read_text(encoding="utf-8")), "lib-b")

  def test_rejects_missing_original(self):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["files"] = {}
    with self.assertRaises(ManifestError):
      AssetManifest.from_api(raw, "lib-a")
