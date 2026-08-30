"""Objective spectral and level measurements shared by semantic feature rules.

This module deliberately emits physical/numerical observations only.  A high
spectral centroid can support a later brightness model, but it is not by itself
proof that listeners would label the mix "bright".
"""
from __future__ import annotations

from typing import Any

import librosa
import numpy as np


ACOUSTIC_MEASUREMENT_VERSION = "acoustic_measurements_v1"


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    if not len(values) or not np.any(weights > 0):
        return 0.0
    return float(np.average(values, weights=weights))


def analyze_acoustic_measurements(
    audio: np.ndarray | None,
    sr: int,
    *,
    n_fft: int = 2048,
    hop_length: int | None = None,
    high_frequency_crossover_hz: float = 2000.0,
) -> dict[str, Any]:
    """Measure active-frame spectrum and digital level without semantic labels."""
    if audio is None or sr <= 0:
        return {"version": ACOUSTIC_MEASUREMENT_VERSION, "status": "unavailable"}
    samples = np.asarray(audio, dtype=float).reshape(-1)
    samples = np.nan_to_num(samples, nan=0.0, posinf=0.0, neginf=0.0)
    if len(samples) < 32 or not np.any(np.abs(samples) > 1e-10):
        return {
            "version": ACOUSTIC_MEASUREMENT_VERSION,
            "status": "unavailable",
            "reason": "silent_or_too_short",
        }
    resolved_fft = int(min(n_fft, 2 ** int(np.floor(np.log2(len(samples))))))
    resolved_fft = max(32, resolved_fft)
    hop = int(hop_length or max(16, resolved_fft // 4))
    magnitude = np.abs(librosa.stft(
        samples, n_fft=resolved_fft, hop_length=hop, center=True,
    ))
    power = np.square(magnitude)
    frame_power = np.sum(power, axis=0)
    peak_power = float(np.max(frame_power)) if len(frame_power) else 0.0
    # Ignore frames at least 60 dB below the loudest frame.  Adding epsilon to
    # an all-zero spectrum would otherwise create a fictitious Nyquist/2
    # centroid in silent intros, gaps and outros.
    active = frame_power >= max(peak_power * 1e-6, np.finfo(float).tiny)
    if not np.any(active):
        return {
            "version": ACOUSTIC_MEASUREMENT_VERSION,
            "status": "unavailable",
            "reason": "no_active_spectral_frames",
        }
    active_weights = frame_power[active]
    centroid_frames = librosa.feature.spectral_centroid(
        S=magnitude, sr=sr,
    )[0]
    rolloff_frames = librosa.feature.spectral_rolloff(
        S=magnitude, sr=sr, roll_percent=0.85,
    )[0]
    flatness_frames = librosa.feature.spectral_flatness(S=magnitude)[0]
    zcr_frames = librosa.feature.zero_crossing_rate(
        samples, frame_length=resolved_fft, hop_length=hop, center=True,
    )[0]
    frequencies = librosa.fft_frequencies(sr=sr, n_fft=resolved_fft)
    audible = frequencies >= 20.0
    high = frequencies >= float(high_frequency_crossover_hz)
    audible_energy = float(np.sum(power[audible][:, active]))
    high_energy = float(np.sum(power[high][:, active])) if np.any(high) else 0.0
    high_ratio = high_energy / max(audible_energy, np.finfo(float).tiny)

    frame_rms = librosa.feature.rms(
        y=samples, frame_length=resolved_fft, hop_length=hop, center=True,
    )[0]
    active_rms = frame_rms[active]
    active_dbfs = 20.0 * np.log10(np.maximum(active_rms, 1e-12))
    rms = float(np.sqrt(np.mean(np.square(samples))))
    peak = float(np.max(np.abs(samples)))
    crest = peak / max(rms, np.finfo(float).tiny)
    clipping = np.abs(samples) >= 0.999
    derivative = np.abs(np.diff(samples, prepend=samples[0]))
    return {
        "version": ACOUSTIC_MEASUREMENT_VERSION,
        "status": "ready",
        "sample_rate": int(sr),
        "n_fft": resolved_fft,
        "hop_length": hop,
        "frame_count": int(len(frame_power)),
        "active_frame_count": int(np.sum(active)),
        "active_frame_fraction": round(float(np.mean(active)), 6),
        "active_frame_floor_db": -60.0,
        "spectral_centroid_hz": round(_weighted_mean(
            centroid_frames[active], active_weights,
        ), 6),
        "spectral_rolloff_85_hz": round(_weighted_mean(
            rolloff_frames[active], active_weights,
        ), 6),
        "spectral_flatness": round(_weighted_mean(
            flatness_frames[active], active_weights,
        ), 8),
        "high_frequency_crossover_hz": round(float(high_frequency_crossover_hz), 3),
        "high_frequency_energy_ratio": round(float(np.clip(high_ratio, 0.0, 1.0)), 8),
        "zero_crossing_rate": round(_weighted_mean(zcr_frames[active], active_weights), 8),
        "rms_dbfs": round(20.0 * np.log10(max(rms, 1e-12)), 6),
        "peak_dbfs": round(20.0 * np.log10(max(peak, 1e-12)), 6),
        "crest_factor": round(crest, 6),
        "crest_factor_db": round(20.0 * np.log10(max(crest, 1e-12)), 6),
        "active_rms_dynamic_range_db": round(
            float(np.percentile(active_dbfs, 95) - np.percentile(active_dbfs, 10)), 6,
        ),
        "clipping_candidate_ratio": round(float(np.mean(clipping)), 8),
        "flat_top_clipping_ratio": round(float(np.mean(
            clipping & (derivative <= 1e-5)
        )), 8),
        "definitions": {
            "spectral_aggregation": "frame_power_weighted_mean_over_active_frames",
            "high_frequency_energy_ratio": "STFT power >= crossover / STFT power >= 20 Hz",
            "active_frame": "frame power within 60 dB of track maximum",
            "clipping_candidate": "absolute digital sample >= 0.999 full scale",
        },
    }
