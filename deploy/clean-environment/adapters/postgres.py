from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping


class DatabaseAdapterError(RuntimeError):
    pass


def database_url_from_env(name: str = "HARBEAT_DATABASE_URL") -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise DatabaseAdapterError(f"database URL environment variable is missing: {name}")
    return value


def _engine(database_url: str):
    try:
        from sqlalchemy import create_engine
    except ImportError as exc:  # pragma: no cover - target dependency
        raise DatabaseAdapterError("SQLAlchemy is unavailable") from exc
    return create_engine(database_url, pool_pre_ping=True)


class PostgresCatalogRepository:
    def __init__(self, database_url: str, asset_root: Path) -> None:
        self.engine = _engine(database_url)
        self.asset_root = asset_root.resolve()

    def list_library_songs(self) -> list[Any]:
        from harbeat_library_catalog.models import LibrarySong
        from sqlalchemy import text

        query = text("""
            SELECT id, song_id, title, artist, duration, analysis_status
            FROM library_songs
            ORDER BY created_at, id
        """)
        with self.engine.connect() as connection:
            rows = connection.execute(query).mappings().all()
        return [LibrarySong.from_api(dict(row)) for row in rows]

    def get_playlist(self, playlist_id: int) -> Any:
        from harbeat_library_catalog.models import Playlist
        from sqlalchemy import text

        playlist_query = text("SELECT id, playlist_name FROM playlists WHERE id = :playlist_id")
        songs_query = text("""
            SELECT ps.song_id, s.title, s.artist, ps.order_index
            FROM playlist_songs ps
            JOIN songs s ON s.id = ps.song_id
            WHERE ps.playlist_id = :playlist_id
            ORDER BY ps.order_index, ps.id
        """)
        with self.engine.connect() as connection:
            playlist = connection.execute(playlist_query, {"playlist_id": playlist_id}).mappings().first()
            if playlist is None:
                raise DatabaseAdapterError(f"playlist not found: {playlist_id}")
            songs = connection.execute(songs_query, {"playlist_id": playlist_id}).mappings().all()
        return Playlist.from_api({**dict(playlist), "songs": [dict(row) for row in songs]})

    def load_song(self, song_id: str) -> dict[str, Any]:
        from sqlalchemy import text

        query = text("""
            SELECT id, song_id, title, artist, duration, format, source_path,
                   bpm, key, camelot_key, energy, music_features, dance_styles,
                   dance_style_scores, dance_style_status, analysis_status,
                   beat_points, bpm_curve, tempo_stability, beat_confidence,
                   beat_grid_offset, beat_grid_interval, energy_curve,
                   loudness_profile, time_signature, groove_score, groove_profile,
                   danceability_score, dancefloor_profile, dj_hot_cues,
                   vocal_events, bass_risk_windows, transition_windows,
                   transition_recommendations, stem_activity,
                   stem_activity_windows, stem_quality_score,
                   stem_quality_profile, intro_is_clean, outro_is_clean,
                   intro_clean_score, outro_clean_score, has_drum_loop,
                   cue_points, downbeats, phrase_map, key_confidence,
                   key_profile, genre_profile, stems
            FROM library_songs
            WHERE id = :song_id
        """)
        with self.engine.connect() as connection:
            row = connection.execute(query, {"song_id": song_id}).mappings().first()
        if row is None:
            raise DatabaseAdapterError(f"library song not found: {song_id}")
        payload = dict(row)
        payload["source_path"] = str(self.resolve_audio_path(payload.get("source_path")))
        return payload

    def resolve_audio_path(self, stored_path: Any) -> Path:
        raw = str(stored_path or "").strip()
        if not raw:
            raise DatabaseAdapterError("song source_path is empty")
        source = Path(raw)
        candidates: tuple[Path, ...] = (
            source,
            self.asset_root / "shared" / source.name,
            self.asset_root / source.name,
        )
        for candidate in candidates:
            if not candidate.is_file():
                continue
            resolved = candidate.resolve()
            try:
                resolved.relative_to(self.asset_root)
            except ValueError:
                continue
            return resolved
        raise DatabaseAdapterError(f"song asset is absent from configured root: {source.name}")


class ShadowAnalysisRepository:
    """Read PostgreSQL features and persist recomputations outside production."""

    def __init__(self, catalog: PostgresCatalogRepository, state_root: Path) -> None:
        self.catalog = catalog
        self.override_root = state_root.resolve() / "analysis-overrides"

    def load_song(self, song_id: str) -> dict[str, Any]:
        return self.catalog.load_song(song_id)

    def load_features(self, song_id: str) -> Mapping[str, Any]:
        override = self._override_path(song_id)
        if override.is_file():
            return _read_json(override)
        return dict(self.load_song(song_id).get("music_features") or {})

    def save_features(self, song_id: str, features: Mapping[str, Any]) -> None:
        destination = self._override_path(song_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".json.part")
        temporary.write_text(
            json.dumps(dict(features), ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)

    def _override_path(self, song_id: str) -> Path:
        safe = "".join(ch for ch in song_id if ch.isalnum() or ch in ("-", "_"))
        if not safe or safe != song_id:
            raise DatabaseAdapterError("invalid library song id")
        return self.override_root / f"{safe}.json"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DatabaseAdapterError(f"invalid shadow analysis state: {path.name}") from exc
    if not isinstance(value, dict):
        raise DatabaseAdapterError(f"invalid shadow analysis state: {path.name}")
    return value
