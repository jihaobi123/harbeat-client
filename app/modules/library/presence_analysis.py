"""Generate provisional Bar-level element presence from separated Stems."""
from __future__ import annotations

import math
import os
from typing import Any, Iterable

import numpy as np
import soundfile as sf

from app.modules.library.bar_timeline import BarWindow


ELEMENT_TO_STEM = {
    "vocal": "vocals",
    "drums": "drums",
    "bass": "bass",
    "melody": "other",
}

THRESHOLDS = {
    "vocal": {"enter": 0.24, "exit": 0.14},
    "drums": {"enter": 0.20, "exit": 0.12},
    "bass": {"enter": 0.22, "exit": 0.13},
    "melody": {"enter": 0.38, "exit": 0.24},
}

CANDIDATE_VERSION = "method:bar_presence_candidate@0.1.0"
THRESHOLD_VERSION = "bar_presence_thresholds@0.1.0"


class PresenceAnalysisError(ValueError):
    pass


def _load_mono(path: str) -> tuple[np.ndarray, int]:
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    return np.mean(audio, axis=1), int(sample_rate)


def _rms(audio: np.ndarray) -> float:
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))


def _dbfs(value: float) -> float:
    return 20.0 * math.log10(max(value, 1e-8))


def _coverage(audio: np.ndarray, sample_rate: int, gate: float) -> float:
    frame_size = max(1, int(sample_rate * 0.05))
    frames = []
    for start in range(0, len(audio), frame_size):
        frame = audio[start:start + frame_size]
        if len(frame):
            frames.append(_rms(frame))
    if not frames:
        return 0.0
    return float(np.mean(np.asarray(frames) >= gate))


def _transient_strength(audio: np.ndarray) -> float:
    if len(audio) < 2:
        return 0.0
    return float(np.mean(np.abs(np.diff(audio))))


def _band_ratio(audio: np.ndarray, sample_rate: int, low: float, high: float) -> float:
    if len(audio) < 8:
        return 0.0
    spectrum = np.abs(np.fft.rfft(audio))
    total = float(np.sum(spectrum))
    if total <= 1e-10:
        return 0.0
    frequencies = np.fft.rfftfreq(len(audio), d=1.0 / sample_rate)
    mask = (frequencies >= low) & (frequencies <= high)
    return float(np.sum(spectrum[mask]) / total)


def _harmonicity(audio: np.ndarray) -> float:
    if len(audio) < 8 or _rms(audio) <= 1e-8:
        return 0.0
    spectrum = np.abs(np.fft.rfft(audio)) + 1e-10
    flatness = float(np.exp(np.mean(np.log(spectrum))) / np.mean(spectrum))
    return float(np.clip(1.0 - flatness, 0.0, 1.0))


def _normalize(values: list[float]) -> list[float]:
    if not values:
        return []
    peak = float(np.percentile(values, 95))
    if peak <= 1e-7:
        return [0.0 for _ in values]
    return [float(np.clip(value / peak, 0.0, 1.0)) for value in values]


def _ranges_from_probabilities(
    probabilities: list[float],
    *,
    enter: float,
    exit: float,
) -> list[dict[str, Any]]:
    ranges: list[dict[str, Any]] = []
    start: int | None = None
    for index, probability in enumerate(probabilities):
        if start is None and probability >= enter:
            start = index
        elif start is not None and probability < exit:
            confidence = float(np.mean(probabilities[start:index]))
            ranges.append(
                {
                    "start_bar_index": start,
                    "end_bar_index": index,
                    "confidence": round(confidence, 4),
                }
            )
            start = None
    if start is not None:
        confidence = float(np.mean(probabilities[start:]))
        ranges.append(
            {
                "start_bar_index": start,
                "end_bar_index": len(probabilities),
                "confidence": round(confidence, 4),
            }
        )
    return ranges


def _element_probabilities(
    element: str,
    audio: np.ndarray,
    sample_rate: int,
    bars: tuple[BarWindow, ...],
) -> tuple[list[float], list[dict[str, float]]]:
    segments = [
        audio[
            max(0, int(round(bar.start_sec * sample_rate))):
            min(len(audio), int(round(bar.end_sec * sample_rate)))
        ]
        for bar in bars
    ]
    rms_values = [_rms(segment) for segment in segments]
    activity = _normalize(rms_values)
    peak = max(rms_values, default=0.0)
    gate = max(1e-6, peak * 0.03)
    coverage = [_coverage(segment, sample_rate, gate) for segment in segments]
    transients = _normalize([_transient_strength(segment) for segment in segments])
    low_band = [
        _band_ratio(segment, sample_rate, 20.0, min(250.0, sample_rate / 2.0))
        for segment in segments
    ]
    harmonics = [_harmonicity(segment) for segment in segments]

    probabilities: list[float] = []
    features: list[dict[str, float]] = []
    for index, segment in enumerate(segments):
        if element == "drums":
            probability = 0.72 * activity[index] + 0.28 * transients[index]
        elif element == "bass":
            probability = 0.80 * activity[index] + 0.20 * low_band[index]
        elif element == "melody":
            probability = min(
                0.65,
                0.50 * activity[index] + 0.15 * harmonics[index],
            )
        else:
            probability = 0.85 * activity[index] + 0.15 * coverage[index]
        probabilities.append(round(float(np.clip(probability, 0.0, 1.0)), 4))
        features.append(
            {
                "rms_dbfs": round(_dbfs(rms_values[index]), 4),
                "coverage": round(coverage[index], 4),
                "transient_strength": round(transients[index], 4),
                "low_frequency_ratio": round(low_band[index], 4),
                "harmonicity": round(harmonics[index], 4),
                "sample_count": float(len(segment)),
            }
        )
    return probabilities, features


def analyze_bar_presence(
    stem_paths: dict[str, str] | None,
    bars: Iterable[BarWindow],
) -> dict[str, Any]:
    """Analyze available Demucs Stems against a trusted Bar timeline."""
    bar_windows = tuple(bars)
    if not bar_windows:
        raise PresenceAnalysisError("Bar timeline is empty")

    available_paths = {
        name: path
        for name, path in (stem_paths or {}).items()
        if name in ELEMENT_TO_STEM.values() and path and os.path.isfile(path)
    }
    loaded: dict[str, np.ndarray] = {}
    sample_rate: int | None = None
    expected_length: int | None = None
    for stem_name, path in available_paths.items():
        audio, current_rate = _load_mono(path)
        if sample_rate is not None and current_rate != sample_rate:
            raise PresenceAnalysisError("Stem sample rate mismatch")
        sample_rate = sample_rate or current_rate
        if expected_length is not None and abs(len(audio) - expected_length) > max(1, int(current_rate * 0.05)):
            raise PresenceAnalysisError("Stem length mismatch")
        expected_length = expected_length if expected_length is not None else len(audio)
        loaded[stem_name] = audio

    if sample_rate is not None:
        required_samples = int(math.ceil(bar_windows[-1].end_sec * sample_rate))
        if any(len(audio) + int(sample_rate * 0.05) < required_samples for audio in loaded.values()):
            raise PresenceAnalysisError("Stem is shorter than the Bar timeline")

    elements: dict[str, dict[str, Any]] = {}
    for element, stem_name in ELEMENT_TO_STEM.items():
        audio = loaded.get(stem_name)
        if audio is None or sample_rate is None:
            elements[element] = {
                "availability": "unavailable",
                "requires_review": True,
                "confidence_cap": 0.65 if element == "melody" else 1.0,
                "bar_probabilities": [0.0 for _ in bar_windows],
                "bar_features": [],
                "candidate_ranges": [],
                "warnings": [f"{stem_name} Stem is unavailable"],
            }
            continue

        probabilities, features = _element_probabilities(
            element,
            audio,
            sample_rate,
            bar_windows,
        )
        threshold = THRESHOLDS[element]
        elements[element] = {
            "availability": "available",
            "requires_review": element == "melody",
            "confidence_cap": 0.65 if element == "melody" else 1.0,
            "bar_probabilities": probabilities,
            "bar_features": features,
            "candidate_ranges": _ranges_from_probabilities(
                probabilities,
                enter=threshold["enter"],
                exit=threshold["exit"],
            ),
            "warnings": (
                ["Melody is inferred from the other Stem and requires review"]
                if element == "melody"
                else []
            ),
        }

    return {
        "candidate_source": CANDIDATE_VERSION,
        "threshold_version": THRESHOLD_VERSION,
        "sample_rate": sample_rate,
        "elements": elements,
    }
