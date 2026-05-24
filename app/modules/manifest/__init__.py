"""Manifest generation per song / per playlist — download blueprint for RK3588."""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

from app.shared.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _compute_sha256(path: str) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _file_size(path: str) -> int:
    return os.path.getsize(path)


def _format_from_path(path: str) -> str:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    return ext if ext else "wav"


def _asset_url(rel_path: str) -> str:
    """Build a downloadable URL for an asset file."""
    # rel_path is relative to upload_dir, e.g. "stems/htdemucs/song1/vocals.wav"
    return f"/api/assets/{rel_path.lstrip('/')}"


def build_song_manifest(song, base_url: str = "") -> dict[str, Any]:
    """Generate a standard manifest for one song.

    Returns a dict matching the AssetManifest / ManifestTrack schema
    expected by Flutter and sync-worker.
    """
    files: dict[str, Any] = {}

    # Original audio
    if song.source_path and os.path.isfile(song.source_path):
        rel = os.path.relpath(song.source_path, settings.upload_dir)
        files["original"] = {
            "url": f"{base_url}/api/assets/{rel}",
            "size": _file_size(song.source_path),
            "sha256": _compute_sha256(song.source_path),
            "format": _format_from_path(song.source_path),
        }

    # Stems
    stems: dict[str, Any] = {}
    if song.stems and isinstance(song.stems, dict):
        for stem_name in ("vocals", "drums", "bass", "other"):
            stem_path = song.stems.get(stem_name)
            if stem_path and os.path.isfile(stem_path):
                rel = os.path.relpath(stem_path, settings.upload_dir)
                stems[stem_name] = {
                    "url": f"{base_url}/api/assets/{rel}",
                    "size": _file_size(stem_path),
                    "sha256": _compute_sha256(stem_path),
                    "format": _format_from_path(stem_path),
                }
    if stems:
        files["stems"] = stems

    # Quality flags
    quality_flags = {
        "has_stems": bool(stems),
        "stem_model": "htdemucs" if stems else None,
        "bpm_confident": song.bpm is not None,
        "key_confidence": song.key_confidence,
        "has_beatgrid": bool(song.beat_points),
        "has_phrase_map": bool(song.phrase_map),
    }

    # Analysis data
    analysis = {}
    if song.bpm is not None:
        analysis["bpm"] = song.bpm
    if song.key:
        analysis["key"] = song.key
    if song.camelot_key:
        analysis["camelot_key"] = song.camelot_key
    if song.energy is not None:
        analysis["energy"] = song.energy
    if song.beat_points:
        analysis["beat_points"] = song.beat_points
    if song.downbeats:
        analysis["downbeats"] = song.downbeats
    if song.phrase_map:
        analysis["phrase_map"] = song.phrase_map
    if song.cue_points:
        analysis["cue_points"] = song.cue_points

    # Stem activity windows: per-section aggregated stem energy
    # Populated by Jetson analysis when stems are available
    if hasattr(song, "stem_activity_windows") and song.stem_activity_windows:
        analysis["stem_activity_windows"] = song.stem_activity_windows
    else:
        # Default: one window covering the full track
        analysis["stem_activity_windows"] = [{
            "section": "full",
            "start_sec": 0.0,
            "end_sec": song.duration if song.duration else 240.0,
            "vocals_rms": 0.0,
            "drums_rms": 0.0,
            "bass_rms": 0.0,
            "other_rms": 0.0,
        }]

    return {
        "songId": song.id,
        "librarySongId": song.id,
        "title": song.title,
        "artist": song.artist,
        "durationSec": song.duration if song.duration else 0.0,
        "bpm": song.bpm,
        "key": song.key,
        "camelotKey": song.camelot_key,
        "files": files,
        "analysis": analysis,
        "qualityFlags": quality_flags,
        "analysisStatus": song.analysis_status,
        "stemStatus": song.stem_status,
    }


def build_playlist_manifest(
    playlist_id: int,
    db,
    base_url: str = "",
    plan_id: str | None = None,
) -> dict[str, Any]:
    """Generate full manifest for a playlist (or mix plan's tracks).

    Resolves LibrarySongs via: Playlist → PlaylistSong → Song ← LibrarySong.song_id.
    Falls back to all ready LibrarySongs if the playlist is empty or has no matches.
    """
    from app.modules.library.models import LibrarySong
    from app.modules.playlists.models import Song, PlaylistSong

    if plan_id:
        # For mix plans: same resolver path, plan_id is just metadata
        pass

    tracks = []

    # Primary path: join through playlist_songs → songs → library_songs
    songs = (
        db.query(LibrarySong)
        .join(Song, LibrarySong.song_id == Song.id)
        .join(PlaylistSong, PlaylistSong.song_id == Song.id)
        .filter(PlaylistSong.playlist_id == playlist_id)
        .order_by(PlaylistSong.order_index)
        .all()
    )

    if not songs:
        # Fallback: query all ready LibrarySongs
        songs = db.query(LibrarySong).filter(
            LibrarySong.analysis_status.in_(["ready", "completed"])
        ).limit(20).all()

    for song in songs:
        tracks.append(build_song_manifest(song, base_url=base_url))

    return {
        "planId": plan_id,
        "playlistId": playlist_id,
        "tracks": tracks,
    }
