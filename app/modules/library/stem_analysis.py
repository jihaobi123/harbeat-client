"""DJ-oriented analysis for separated vocals, drums, bass, and other stems."""
from __future__ import annotations

import os
from typing import Any

import numpy as np
import soundfile as sf

STEM_NAMES = ("vocals", "drums", "bass", "other")


def _load_mono(path: str) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    return np.mean(audio, axis=1), int(sr)


def _rms(audio: np.ndarray) -> float:
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))


def _activity_curve(audio: np.ndarray, window_samples: int, count: int) -> list[float]:
    raw = []
    for index in range(count):
        start = index * window_samples
        end = min(start + window_samples, len(audio))
        raw.append(_rms(audio[start:end]))
    reference = float(np.percentile(raw, 95)) if raw else 0.0
    if reference <= 1e-8:
        return [0.0] * count
    return [round(float(np.clip(value / reference, 0.0, 1.0)), 4) for value in raw]


def _reconstruction_score(
    stems: dict[str, np.ndarray],
    original_path: str | None,
    expected_sr: int,
    length: int,
) -> float:
    if not original_path or not os.path.isfile(original_path):
        return 0.75
    original, sr = _load_mono(original_path)
    if sr != expected_sr or len(original) == 0:
        return 0.5
    length = min(length, len(original))
    reconstructed = sum(audio[:length] for audio in stems.values())
    reference = _rms(original[:length]) + 1e-8
    error = _rms(reconstructed - original[:length]) / reference
    return float(np.clip(1.0 - error, 0.0, 1.0))


def analyze_stem_files(
    stem_paths: dict[str, str] | None,
    *,
    original_path: str | None = None,
    window_sec: float = 2.0,
) -> dict[str, Any]:
    """Analyze real separated stems into planner-ready activity metadata."""
    available = {
        name: path for name, path in (stem_paths or {}).items()
        if name in STEM_NAMES and path and os.path.isfile(path)
    }
    loaded: dict[str, np.ndarray] = {}
    sample_rate = 0
    for name in STEM_NAMES:
        path = available.get(name)
        if not path:
            continue
        audio, sr = _load_mono(path)
        if sample_rate and sr != sample_rate:
            continue
        sample_rate = sample_rate or sr
        loaded[name] = audio

    completeness = len(loaded) / len(STEM_NAMES)
    if not loaded or sample_rate <= 0:
        return {
            "has_complete_stems": False,
            "stem_quality_score": 0.0,
            "stem_quality_method": "completeness_reconstruction_proxy",
            "stem_activity": {name: 0.0 for name in STEM_NAMES},
            "stem_activity_windows": [],
            "intro_is_clean": False,
            "outro_is_clean": False,
            "has_drum_loop": False,
        }

    length = min(len(audio) for audio in loaded.values())
    window_samples = max(1, int(sample_rate * window_sec))
    count = max(1, int(np.ceil(length / window_samples)))
    curves = {
        name: _activity_curve(loaded.get(name, np.zeros(length)), window_samples, count)
        for name in STEM_NAMES
    }

    windows = []
    for index in range(count):
        windows.append({
            "start": round(index * window_samples / sample_rate, 3),
            "end": round(min((index + 1) * window_samples, length) / sample_rate, 3),
            **{name: curves[name][index] for name in STEM_NAMES},
        })

    activity = {
        name: round(float(np.mean(curves[name])), 4) if curves[name] else 0.0
        for name in STEM_NAMES
    }
    reconstruction = _reconstruction_score(loaded, original_path, sample_rate, length)
    quality = completeness * (0.75 + 0.25 * reconstruction)
    vocals = curves["vocals"]
    drums = curves["drums"]

    return {
        "has_complete_stems": completeness == 1.0,
        "stem_quality_score": round(float(np.clip(quality, 0.0, 1.0)), 4),
        "stem_quality_method": "completeness_reconstruction_proxy",
        "stem_activity": activity,
        "stem_activity_windows": windows,
        "intro_is_clean": bool(vocals and vocals[0] < 0.25),
        "outro_is_clean": bool(vocals and vocals[-1] < 0.25),
        "has_drum_loop": bool(
            drums and activity["drums"] >= 0.35
            and sum(value >= 0.3 for value in drums) / len(drums) >= 0.6
        ),
    }
