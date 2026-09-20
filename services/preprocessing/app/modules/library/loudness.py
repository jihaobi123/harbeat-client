"""Library loudness helpers for Spotify Mix normalization."""
from __future__ import annotations

from typing import Any, Tuple

import numpy as np

from app.modules.dj_control.spotify_mix.loudness import (
    SPOTIFY_TARGET_LUFS,
    calculate_replay_gain,
    detect_clipping,
    measure_lufs,
    normalize_to_lufs,
    peak_dbfs,
)


def loudness_profile(
    audio: np.ndarray,
    sr: int,
    target_lufs: float = SPOTIFY_TARGET_LUFS,
) -> dict[str, Any]:
    """Build a compact loudness profile for a song."""
    measured_lufs = measure_lufs(audio, sr)
    replay_gain_db = target_lufs - measured_lufs
    return {
        "integrated_lufs": round(float(measured_lufs), 3),
        "target_lufs": round(float(target_lufs), 3),
        "replay_gain_db": round(float(replay_gain_db), 3),
        "peak_dbfs": round(float(peak_dbfs(audio)), 3),
        "clipping_risk": detect_clipping(audio),
    }


def normalize_audio_to_lufs(
    audio: np.ndarray,
    sr: int,
    target_lufs: float = SPOTIFY_TARGET_LUFS,
) -> Tuple[np.ndarray, dict[str, Any]]:
    """Normalize audio and return the updated loudness profile."""
    normalized, original_lufs, gain_db = normalize_to_lufs(audio, sr, target_lufs)
    profile = loudness_profile(normalized, sr, target_lufs)
    profile["original_lufs"] = round(float(original_lufs), 3)
    profile["applied_gain_db"] = round(float(gain_db), 3)
    return normalized, profile


__all__ = [
    "SPOTIFY_TARGET_LUFS",
    "calculate_replay_gain",
    "detect_clipping",
    "loudness_profile",
    "measure_lufs",
    "normalize_audio_to_lufs",
    "normalize_to_lufs",
    "peak_dbfs",
]
