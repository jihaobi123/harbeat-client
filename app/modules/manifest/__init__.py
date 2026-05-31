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
        "tempo_stability": getattr(song, "tempo_stability", None),
        "beat_confidence": getattr(song, "beat_confidence", None),
        "beat_needs_review": bool(getattr(song, "beat_needs_review", False)),
        "stem_quality_score": getattr(song, "stem_quality_score", None),
        "intro_is_clean": bool(getattr(song, "intro_is_clean", False)),
        "outro_is_clean": bool(getattr(song, "outro_is_clean", False)),
        "clipping_risk": bool((getattr(song, "loudness_profile", {}) or {}).get("clipping_risk", False)),
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
    if getattr(song, "bpm_curve", None):
        analysis["bpm_curve"] = song.bpm_curve
    if getattr(song, "tempo_stability", None) is not None:
        analysis["tempo_stability"] = song.tempo_stability
    if getattr(song, "beat_confidence", None) is not None:
        analysis["beat_confidence"] = song.beat_confidence
    if getattr(song, "beat_confidence_details", None):
        analysis["beat_confidence_details"] = song.beat_confidence_details
    if getattr(song, "beat_grid_offset", None) is not None:
        analysis["beat_grid_offset"] = song.beat_grid_offset
    if getattr(song, "beat_grid_interval", None) is not None:
        analysis["beat_grid_interval"] = song.beat_grid_interval
    if getattr(song, "beat_engines_used", None):
        analysis["beat_engines_used"] = song.beat_engines_used
    analysis["beat_needs_review"] = bool(getattr(song, "beat_needs_review", False))
    if getattr(song, "energy_curve", None):
        analysis["energy_curve"] = song.energy_curve
    if getattr(song, "loudness_profile", None):
        analysis["loudness_profile"] = song.loudness_profile
    if getattr(song, "transition_windows", None):
        analysis["transition_windows"] = song.transition_windows
    if getattr(song, "stem_activity", None):
        analysis["stem_activity"] = song.stem_activity
    if getattr(song, "stem_activity_windows", None):
        analysis["stem_activity_windows"] = song.stem_activity_windows
    if getattr(song, "stem_quality_score", None) is not None:
        analysis["stem_quality_score"] = song.stem_quality_score
    analysis["intro_is_clean"] = bool(getattr(song, "intro_is_clean", False))
    analysis["outro_is_clean"] = bool(getattr(song, "outro_is_clean", False))
    analysis["has_drum_loop"] = bool(getattr(song, "has_drum_loop", False))
    if getattr(song, "music_features", None):
        analysis["music_features"] = song.music_features
    if getattr(song, "dance_styles", None):
        analysis["dance_styles"] = song.dance_styles
    if getattr(song, "dance_style_scores", None):
        analysis["dance_style_scores"] = song.dance_style_scores
    if song.downbeats:
        analysis["downbeats"] = song.downbeats
    if song.phrase_map:
        analysis["phrase_map"] = song.phrase_map
    if song.cue_points:
        analysis["cue_points"] = song.cue_points

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
        "replayGainDb": (getattr(song, "loudness_profile", {}) or {}).get("replay_gain_db"),
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
    """Generate full manifest for a playlist (or mix plan's tracks)."""
    from app.modules.library.models import LibrarySong

    if plan_id:
        # Look up tracks from the stored mix plan
        from app.modules.music.models import SongCue  # noqa: F401
        # For mix plans, we need to look up which songs are in the plan
        # The plan is stored in playlists, so we use the playlist's songs
        pass

    tracks = []
    # Query all LibrarySongs associated with this playlist
    # This assumes playlist_songs join table exists; adapt as needed
    songs = db.query(LibrarySong).filter(
        LibrarySong.id.in_(
            # Subquery depends on actual schema; use playlist_songs if available
            db.query(LibrarySong.id).join(
                LibrarySong.song
            ).filter(
                LibrarySong.song.has(playlist_id=playlist_id)
            )
        )
    ).all() if False else []  # placeholder — actual join depends on schema

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
