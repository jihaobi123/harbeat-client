import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from harbeat_library_catalog.catalog import CatalogIndex, CatalogMappingError
from harbeat_library_catalog.models import LibrarySong, Playlist

FIXTURES = Path(__file__).parent / "fixtures"

class CatalogTests(unittest.TestCase):
  def _songs(self):
    rows = json.loads((FIXTURES / "library_songs.json").read_text(encoding="utf-8"))
    return [LibrarySong.from_api(row) for row in rows]

  def test_resolves_playlist_by_explicit_catalog_mapping_and_reports_missing(self):
    index = CatalogIndex.build(self._songs())
    playlist = Playlist.from_api(json.loads((FIXTURES / "playlist.json").read_text(encoding="utf-8")))
    resolved, unresolved = index.resolve_playlist(playlist)
    self.assertEqual([item.identity.library_song_id for item in resolved], ["lib-a", "lib-b"])
    self.assertEqual(unresolved, [999])

  def test_does_not_resolve_by_matching_title(self):
    index = CatalogIndex.build(self._songs())
    playlist = Playlist.from_api({"id": 1, "playlist_name": "x", "songs": [{"song_id": 555, "title": "Track A", "artist": "Artist A", "order_index": 0}]})
    resolved, unresolved = index.resolve_playlist(playlist)
    self.assertEqual(resolved, [])
    self.assertEqual(unresolved, [555])

  def test_rejects_ambiguous_catalog_mapping(self):
    songs = self._songs()
    duplicate = LibrarySong.from_api({"id":"lib-d","song_id":101,"title":"D","artist":"D"})
    with self.assertRaises(CatalogMappingError):
      CatalogIndex.build(songs + [duplicate])
