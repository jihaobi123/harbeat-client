from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine, text

REPO_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(Path(__file__).parents[1]))
for module_src in (REPO_ROOT / "modules").glob("*/src"):
    sys.path.insert(0, str(module_src))

from adapters.postgres import (
    DatabaseAdapterError,
    PostgresCatalogRepository,
    ShadowAnalysisRepository,
    database_url_from_env,
)
from harbeat_library_catalog.service import CatalogService


class FakeCatalog:
    def load_song(self, song_id: str) -> dict:
        return {"id": song_id, "music_features": {"existing": True}}


class PostgresAdapterTests(unittest.TestCase):
    def test_catalog_repository_resolves_real_schema_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "catalog.sqlite"
            engine = create_engine(f"sqlite:///{database}")
            with engine.begin() as connection:
                connection.execute(text("""
                    CREATE TABLE library_songs (
                        id TEXT PRIMARY KEY, song_id INTEGER, title TEXT, artist TEXT,
                        duration REAL, analysis_status TEXT, created_at TEXT
                    )
                """))
                connection.execute(text("CREATE TABLE playlists (id INTEGER PRIMARY KEY, playlist_name TEXT)"))
                connection.execute(text("CREATE TABLE songs (id INTEGER PRIMARY KEY, title TEXT, artist TEXT)"))
                connection.execute(text("""
                    CREATE TABLE playlist_songs (
                        id INTEGER PRIMARY KEY, playlist_id INTEGER,
                        song_id INTEGER, order_index INTEGER
                    )
                """))
                connection.execute(text("INSERT INTO songs VALUES (7, 'Track', 'Artist')"))
                connection.execute(text("INSERT INTO library_songs VALUES ('lib-7', 7, 'Track', 'Artist', 123.4, 'completed', '2026-01-01')"))
                connection.execute(text("INSERT INTO playlists VALUES (1, 'test')"))
                connection.execute(text("INSERT INTO playlist_songs VALUES (1, 1, 7, 0)"))

            repository = PostgresCatalogRepository(f"sqlite:///{database}", root)
            try:
                result = CatalogService(repository).resolve_playlist(1)
                self.assertTrue(result.complete)
                self.assertEqual(result.songs[0].identity.library_song_id, "lib-7")
            finally:
                repository.engine.dispose()
                engine.dispose()

    def test_asset_resolution_uses_configured_root_not_stored_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = root / "shared"
            shared.mkdir()
            expected = shared / "song.mp3"
            expected.write_bytes(b"audio")
            repository = PostgresCatalogRepository("sqlite://", root)
            try:
                resolved = repository.resolve_audio_path("/untrusted/legacy/song.mp3")
                self.assertEqual(resolved, expected.resolve())
            finally:
                repository.engine.dispose()

    def test_shadow_analysis_persistence_never_writes_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = ShadowAnalysisRepository(FakeCatalog(), Path(directory))
            self.assertEqual(repository.load_features("song-1"), {"existing": True})
            repository.save_features("song-1", {"dj_structure_v2": {"version": "dj_structure_v2"}})
            self.assertEqual(
                repository.load_features("song-1"),
                {"dj_structure_v2": {"version": "dj_structure_v2"}},
            )
            self.assertTrue((Path(directory) / "analysis-overrides" / "song-1.json").is_file())

    def test_database_secret_is_environment_only(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(DatabaseAdapterError):
                database_url_from_env()
        with patch.dict(os.environ, {"HARBEAT_DATABASE_URL": "sqlite://"}, clear=True):
            self.assertEqual(database_url_from_env(), "sqlite://")


if __name__ == "__main__":
    unittest.main()
