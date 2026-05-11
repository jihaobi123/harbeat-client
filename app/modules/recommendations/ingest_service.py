"""Spotify track ingestion pipeline: download → analyze → embed → index.

Ported from FinalReco/services/library_service.py, adapted for the main
FastAPI service's existing library/analysis infrastructure.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import librosa
import numpy as np

logger = logging.getLogger(__name__)

YTDLP_TIMEOUT_SECONDS = 120  # per-track download cap

# Default output directory (under the main data/ tree)
_DEFAULT_DOWNLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "music-files", "downloads",
)


def _download_dir() -> Path:
    d = os.environ.get("UPLOAD_DIR", _DEFAULT_DOWNLOAD_DIR)
    path = Path(d)
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value)
    return cleaned.strip("._") or "audio"


def compute_audio_features(audio_path: Path) -> tuple[float, float]:
    """Extract BPM and RMS energy via librosa."""
    signal, sample_rate = librosa.load(audio_path, sr=None, mono=True)
    tempo, _ = librosa.beat.beat_track(y=signal, sr=sample_rate)
    rms = librosa.feature.rms(y=signal)
    energy = float(np.mean(rms))
    safe_tempo = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)
    return safe_tempo, energy


def download_audio(
    track_name: str,
    artist: str,
    spotify_id: str,
) -> Optional[Path]:
    """Download audio via yt-dlp. Skips if file already exists for this spotify_id.

    Returns path to downloaded audio file, or None on failure.
    """
    output_dir = _download_dir()
    existing = sorted(output_dir.glob(f"{sanitize_filename(spotify_id)}.*"))
    if existing:
        logger.info("[ingest] skipping download, file exists: %s", existing[0])
        return existing[0]

    import yt_dlp

    output_template = str(output_dir / f"{sanitize_filename(spotify_id)}.%(ext)s")
    query = f"ytsearch1:{track_name} {artist} audio"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": YTDLP_TIMEOUT_SECONDS,
    }

    temp_dir = Path(tempfile.mkdtemp(prefix="fre-ingest-"))
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=True)
            if "entries" in info:
                entries = [e for e in info["entries"] if e]
                if not entries:
                    return None
                info = entries[0]
            downloaded = Path(ydl.prepare_filename(info))
            if not downloaded.exists():
                matches = sorted(output_dir.glob(f"{sanitize_filename(spotify_id)}.*"))
                downloaded = matches[0] if matches else None
            if downloaded and downloaded.parent != output_dir:
                # yt-dlp may have downloaded to temp dir, move to output
                target = output_dir / downloaded.name
                if not target.exists():
                    shutil.move(str(downloaded), str(target))
                downloaded = target
            return downloaded
    except Exception:
        logger.exception("[ingest] yt-dlp download failed for %s", spotify_id)
        return None
    finally:
        shutil.rmtree(str(temp_dir), ignore_errors=True)


def embed_audio_clap(audio_path: Path) -> Optional[List[float]]:
    """Generate CLAP audio embedding via subprocess. Returns 512-d vector or None."""
    from app.modules.recommendations.vector_store import _run_clap_audio_subprocess as _clap

    try:
        return _clap(str(audio_path))
    except Exception:
        logger.exception("[ingest] CLAP audio embedding failed for %s", audio_path)
        return None


def _normalize_spotify_track(track: dict) -> dict:
    """Normalize Spotify track dict to {spotify_id, track_name, artist}."""
    artists = ", ".join(
        (artist or {}).get("name", "").strip()
        for artist in track.get("artists", [])
        if (artist or {}).get("name")
    ).strip() or "Unknown Artist"
    return {
        "spotify_id": str(track.get("id") or track.get("spotify_id") or ""),
        "track_name": str(track.get("name") or track.get("track_name") or "Unknown Track"),
        "artist": artists if artists else str(track.get("artist") or "Unknown Artist"),
    }


def ingest_spotify_track(
    track_info: dict,
    collection_name: str = "harbeat_clap",
    user_id: Optional[int] = None,
) -> Dict[str, object]:
    """Full pipeline for a single Spotify track: download → analyze → embed → index.

    Returns {"success": True/False, "spotify_id": ..., "track_name": ..., ...}
    """
    normalized = _normalize_spotify_track(track_info)
    spotify_id = normalized["spotify_id"]
    if not spotify_id:
        return {"success": False, "error": "missing spotify_id", "track": normalized}

    # 1. Download audio
    audio_path = download_audio(
        track_name=normalized["track_name"],
        artist=normalized["artist"],
        spotify_id=spotify_id,
    )
    if not audio_path:
        return {"success": False, "error": "download failed", "spotify_id": spotify_id}

    # 2. Extract BPM / energy
    try:
        bpm, energy_val = compute_audio_features(audio_path)
    except Exception:
        logger.warning("[ingest] audio feature extraction failed, using defaults")
        bpm, energy_val = 0.0, 5.0

    # 3. CLAP audio embedding → ChromaDB
    clap_embedding = embed_audio_clap(audio_path)
    if clap_embedding is not None:
        try:
            from app.modules.recommendations.vector_store import get_clap_collection
            col = get_clap_collection()
            doc = f"{normalized['track_name']} - {normalized['artist']}"
            metadata = {
                "spotify_id": spotify_id,
                "track_name": normalized["track_name"],
                "artist": normalized["artist"],
                "bpm": float(bpm),
                "energy": float(energy_val),
            }
            col.upsert(
                ids=[spotify_id],
                embeddings=[clap_embedding],
                metadatas=[metadata],
                documents=[doc],
            )
        except Exception:
            logger.exception("[ingest] ChromaDB upsert failed for %s", spotify_id)

    return {
        "success": True,
        "spotify_id": spotify_id,
        "track_name": normalized["track_name"],
        "artist": normalized["artist"],
        "bpm": float(bpm),
        "energy": float(energy_val),
        "local_path": str(audio_path),
    }


def ingest_spotify_tracks(
    tracks: List[dict],
    collection_name: str = "harbeat_clap",
    user_id: Optional[int] = None,
) -> List[dict]:
    """Batch ingest multiple Spotify tracks."""
    results: List[dict] = []
    for track in tracks:
        results.append(ingest_spotify_track(track, collection_name=collection_name, user_id=user_id))
    return results
