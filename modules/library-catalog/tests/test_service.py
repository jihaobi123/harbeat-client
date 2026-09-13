import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from harbeat_library_catalog.models import LibrarySong, Playlist
from harbeat_library_catalog.service import CatalogService

FIXTURES = Path(__file__).parent / "fixtures"


class MemoryRepository:
  def __init__(self):
    rows=json.loads((FIXTURES/'library_songs.json').read_text(encoding='utf-8'))
    self.songs=[LibrarySong.from_api(row) for row in rows]
    self.playlist=Playlist.from_api(json.loads((FIXTURES/'playlist.json').read_text(encoding='utf-8')))
  def list_library_songs(self): return list(self.songs)
  def get_playlist(self,playlist_id): return self.playlist


class ServiceTests(unittest.TestCase):
  def test_resolves_through_repository_without_database_dependency(self):
    result=CatalogService(MemoryRepository()).resolve_playlist(7)
    self.assertEqual([row.identity.library_song_id for row in result.songs],['lib-a','lib-b'])
    self.assertEqual(result.unresolved_catalog_song_ids,(999,)); self.assertFalse(result.complete)

  def test_rejects_invalid_playlist_id_before_repository_use(self):
    with self.assertRaises(ValueError): CatalogService(MemoryRepository()).resolve_playlist(0)
