import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from harbeat_library_catalog.identity import SongIdentity

class IdentityTests(unittest.TestCase):
  def test_rk_asset_id_is_always_library_uuid(self):
    identity = SongIdentity("lib-a", 101)
    self.assertEqual(identity.playback_asset_id, "lib-a")
    self.assertNotEqual(identity.playback_asset_id, str(identity.catalog_song_id))

  def test_rejects_missing_library_id(self):
    with self.assertRaises(ValueError):
      SongIdentity("", 101)
