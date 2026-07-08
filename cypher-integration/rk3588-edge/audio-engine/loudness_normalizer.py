"""Loudness normalization helpers for RK audio-engine playback."""
from __future__ import annotations

import numpy as np

TARGET_LUFS = -14.0


def measure_lufs(audio: np.ndarray, sr: int) -> float:
    """Measure integrated loudness, falling back to RMS dBFS."""
    data = np.asarray(audio, dtype=np.float32)
    if data.size == 0:
        return -70.0
    try:
        import pyloudnorm as pyln

        return float(pyln.Meter(sr).integrated_loudness(data))
    except Exception:
        mono = data.mean(axis=1) if data.ndim == 2 else data
        rms = float(np.sqrt(np.mean(np.square(mono))))
        if rms <= 1e-9:
            return -70.0
        return float(20.0 * np.log10(rms) - 3.0)


def gain_db_for_target(audio: np.ndarray, sr: int, target_lufs: float = TARGET_LUFS) -> float:
    """Return gain in dB needed to hit target LUFS."""
    return float(target_lufs - measure_lufs(audio, sr))


def apply_loudness_norm(
    audio: np.ndarray,
    sr: int,
    target_lufs: float = TARGET_LUFS,
    ceiling: float = 0.999,
) -> tuple[np.ndarray, dict]:
    """Normalize audio and return metadata used by edge-agent responses."""
    data = np.asarray(audio, dtype=np.float32)
    original_lufs = measure_lufs(data, sr)
    gain_db = float(target_lufs - original_lufs)
    normalized = data * float(10.0 ** (gain_db / 20.0))
    normalized = np.clip(normalized, -ceiling, ceiling).astype(np.float32)
    return normalized, {
        "original_lufs": round(original_lufs, 3),
        "target_lufs": round(float(target_lufs), 3),
        "gain_db": round(gain_db, 3),
        "peak": round(float(np.max(np.abs(normalized))) if normalized.size else 0.0, 6),
    }
