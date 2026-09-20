"""LUFS loudness normalization.

Normalizes audio to a target integrated loudness (default -14 LUFS,
matching Spotify's playback target).
"""
from __future__ import annotations

import numpy as np
from typing import Tuple


SPOTIFY_TARGET_LUFS = -14.0


def measure_lufs(audio: np.ndarray, sr: int) -> float:
    """Measure integrated LUFS of audio.

    Args:
        audio: Audio samples
        sr: Sample rate

    Returns:
        Integrated LUFS value (negative dB)
    """
    try:
        import pyloudnorm as pyln
    except ImportError:
        # Fallback: compute approximate RMS-based loudness
        return _rms_loudness_approximation(audio)

    try:
        meter = pyln.Meter(sr)
        return meter.integrated_loudness(audio)
    except Exception:
        return _rms_loudness_approximation(audio)


def _rms_loudness_approximation(audio: np.ndarray) -> float:
    """Approximate loudness using RMS when pyloudnorm unavailable.

    Not LUFS-accurate but gives reasonable normalization target.
    """
    if len(audio) == 0:
        return -70.0
    rms = float(np.sqrt(np.mean(audio ** 2)))
    if rms < 1e-9:
        return -70.0
    # Convert RMS to dBFS, then approximate to LUFS (~-3dB offset)
    db = 20 * np.log10(rms)
    return float(db - 3.0)  # Rough LUFS approximation


def normalize_to_lufs(
    audio: np.ndarray,
    sr: int,
    target_lufs: float = SPOTIFY_TARGET_LUFS,
) -> Tuple[np.ndarray, float, float]:
    """Normalize audio to target LUFS.

    Args:
        audio: Audio samples
        sr: Sample rate
        target_lufs: Target loudness (default -14 LUFS)

    Returns:
        (normalized_audio, original_lufs, gain_db_applied)
    """
    if len(audio) == 0:
        return audio, target_lufs, 0.0

    original_lufs = measure_lufs(audio, sr)
    gain_db = target_lufs - original_lufs

    try:
        import pyloudnorm as pyln
        normalized = pyln.normalize.loudness(audio, original_lufs, target_lufs)
    except Exception:
        # Fallback: linear gain
        gain_linear = 10 ** (gain_db / 20)
        normalized = audio * gain_linear
        # Soft clip to prevent overflow
        normalized = np.clip(normalized, -1.0, 1.0)

    return normalized, original_lufs, gain_db


def calculate_replay_gain(audio: np.ndarray, sr: int) -> float:
    """Calculate ReplayGain in dB.

    Args:
        audio: Audio samples
        sr: Sample rate

    Returns:
        Gain in dB to apply for normalization
    """
    lufs = measure_lufs(audio, sr)
    return SPOTIFY_TARGET_LUFS - lufs


def detect_clipping(audio: np.ndarray, threshold: float = 0.99) -> bool:
    """Detect if audio is clipped.

    Args:
        audio: Audio samples (must be in [-1, 1])
        threshold: Clipping threshold

    Returns:
        True if clipping detected
    """
    if len(audio) == 0:
        return False
    clipped = np.abs(audio) >= threshold
    if not bool(np.any(clipped)):
        return False
    clip_ratio = float(np.mean(clipped))
    if clip_ratio >= 0.1:
        return True
    if len(clipped) >= 3:
        signs = np.sign(audio)
        same_sign = (signs[:-2] == signs[1:-1]) & (signs[1:-1] == signs[2:])
        runs = clipped[:-2] & clipped[1:-1] & clipped[2:] & same_sign
        if bool(np.any(runs)):
            return True
    return False


def peak_dbfs(audio: np.ndarray) -> float:
    """Compute peak level in dBFS."""
    if len(audio) == 0:
        return -70.0
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-9:
        return -70.0
    return 20 * np.log10(peak)
