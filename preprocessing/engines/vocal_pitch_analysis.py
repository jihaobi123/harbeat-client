"""Objective pitch measurements for an isolated vocal signal."""
from __future__ import annotations

from typing import Any

import librosa
import numpy as np


HOP_LENGTH = 256
# Fixed on the 570-clip, song-group-disjoint MIR-1K calibration split.  The
# pYIN voiced flag and adaptive RMS gate remain mandatory, so this threshold
# recovers low-confidence correct pitch without admitting silent frames.
MINIMUM_VOICED_PROBABILITY = 0.10
MAXIMUM_SUSTAIN_GAP_SECONDS = 0.060


def _bridge_short_internal_gaps(
    voiced: np.ndarray,
    active: np.ndarray,
    *,
    maximum_gap_frames: int,
) -> np.ndarray:
    """Bridge only short active gaps bounded by voiced pitch on both sides."""
    result = np.asarray(voiced, dtype=bool).copy()
    active = np.asarray(active, dtype=bool)[:len(result)]
    start = None
    for index, value in enumerate(np.r_[result, True]):
        if not value and start is None:
            start = index
        elif value and start is not None:
            end = index
            bounded = start > 0 and end < len(result)
            if (
                bounded
                and end - start <= maximum_gap_frames
                and np.all(active[start:end])
            ):
                result[start:end] = True
            start = None
    return result


def vocal_pitch_descriptors(
    midi: np.ndarray,
    active: np.ndarray,
    *,
    frame_hop_seconds: float,
) -> dict[str, float]:
    """Measure robust range, contiguous motion, and sustained voiced time."""
    midi = np.asarray(midi, dtype=float)
    active = np.asarray(active, dtype=bool)[:len(midi)]
    voiced = np.isfinite(midi) & (midi > 0) & active
    sustain_voiced = _bridge_short_internal_gaps(
        voiced,
        active,
        maximum_gap_frames=max(1, int(round(
            MAXIMUM_SUSTAIN_GAP_SECONDS / frame_hop_seconds
        ))),
    )
    values = midi[voiced]
    pitch_range = (
        float(np.percentile(values, 90) - np.percentile(values, 10))
        if len(values) >= 4 else 0.0
    )
    # Never bridge an unvoiced pause: that is a phrase boundary, not observed
    # pitch movement.  A 100 ms interval is long enough to describe melodic
    # motion rather than frame jitter or vibrato-tracker noise.
    motion_lag = max(1, int(round(0.10 / frame_hop_seconds)))
    contiguous = (
        np.convolve(
            voiced.astype(int), np.ones(motion_lag + 1, dtype=int), mode="valid",
        ) == motion_lag + 1
        if len(voiced) > motion_lag else np.asarray([], dtype=bool)
    )
    motion = (
        float(np.median(np.abs(midi[motion_lag:] - midi[:-motion_lag])[contiguous]))
        if np.any(contiguous) else 0.0
    )
    runs: list[int] = []
    run = 0
    for value in np.r_[sustain_voiced, False]:
        if value:
            run += 1
        elif run:
            runs.append(run)
            run = 0
    sustained_frames = sum(
        length for length in runs if length * frame_hop_seconds >= 0.25
    )
    # Sustain is a property of the pitched part of a vocal phrase.  Dividing
    # by RMS-active frames would make consonants and breaths change the value.
    sustain_ratio = sustained_frames / max(int(np.sum(sustain_voiced)), 1)
    contour = float(np.clip(
        0.62 * np.clip(pitch_range / 12.0, 0.0, 1.0)
        + 0.38 * np.clip(motion / 2.5, 0.0, 1.0),
        0.0,
        1.0,
    ))
    return {
        "pitch_range_semitones": pitch_range,
        "median_100ms_contiguous_motion_semitones": motion,
        "pitch_sustain_ratio": sustain_ratio,
        "melodic_contour_score": contour,
        "sustained_voiced_frame_count": float(sustained_frames),
        "maximum_bridged_sustain_gap_seconds": MAXIMUM_SUSTAIN_GAP_SECONDS,
    }


def vocal_pitch_view(
    analysis: dict[str, Any], sr: int, *, minimum_voiced_probability: float,
) -> dict[str, Any]:
    """Apply a fixed probability decision to one already-computed pYIN path."""
    f0 = np.asarray(analysis["f0_hz"], dtype=float)
    active = np.asarray(analysis["active"], dtype=bool)
    voiced_flag = np.asarray(analysis["voiced_flag"], dtype=bool)
    voiced_probability = np.asarray(analysis["voiced_probability"], dtype=float)
    length = min(len(f0), len(active))
    f0 = f0[:length]
    voiced_probability = voiced_probability[:length]
    voiced_flag = voiced_flag[:length]
    active = active[:length]
    valid = (
        np.isfinite(f0)
        & voiced_flag
        & (voiced_probability >= float(minimum_voiced_probability))
        & active
    )
    midi = np.zeros(length, dtype=float)
    midi[valid] = librosa.hz_to_midi(f0[valid])
    descriptors = vocal_pitch_descriptors(
        midi, active, frame_hop_seconds=HOP_LENGTH / sr,
    )
    return {
        "f0_hz": f0,
        "midi": midi,
        "valid": valid,
        "descriptors": descriptors,
    }


def analyze_vocal_pitch(
    audio: np.ndarray,
    sr: int,
    *,
    minimum_voiced_probability: float = MINIMUM_VOICED_PROBABILITY,
) -> dict[str, Any]:
    """Run the production pYIN and adaptive-RMS measurement chain."""
    audio = np.asarray(audio, dtype=float)
    rms = librosa.feature.rms(
        y=audio, frame_length=1024, hop_length=HOP_LENGTH,
    )[0]
    low_rms = float(np.percentile(rms, 20))
    high_rms = float(np.percentile(rms, 95))
    rms_gate = max(min(low_rms * 3.0, high_rms * 0.20), high_rms * 0.06, 1e-7)
    active = rms >= rms_gate
    f0, voiced_flag, voiced_probability = librosa.pyin(
        audio,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        sr=sr,
        frame_length=2048,
        hop_length=HOP_LENGTH,
    )
    length = min(len(f0), len(active))
    result = {
        "f0_hz": np.asarray(f0[:length], dtype=float),
        "active": np.asarray(active[:length], dtype=bool),
        "voiced_flag": np.asarray(voiced_flag[:length], dtype=bool),
        "voiced_probability": np.asarray(voiced_probability[:length], dtype=float),
        "rms_gate": rms_gate,
    }
    return {
        **result,
        **vocal_pitch_view(
            result, sr, minimum_voiced_probability=minimum_voiced_probability,
        ),
    }
