from __future__ import annotations

import numpy as np

from app.modules.library.acoustic_measurement_analysis import analyze_acoustic_measurements


def test_silence_is_unavailable_instead_of_fictitious_midband_centroid() -> None:
    result = analyze_acoustic_measurements(np.zeros(44_100), 44_100)
    assert result["status"] == "unavailable"


def test_spectral_centroid_tracks_a_pure_tone() -> None:
    sr = 44_100
    time = np.arange(sr * 2) / sr
    result = analyze_acoustic_measurements(0.5 * np.sin(2 * np.pi * 1000 * time), sr)
    assert abs(result["spectral_centroid_hz"] - 1000.0) < 25.0
    assert abs(result["crest_factor"] - np.sqrt(2.0)) < 0.03


def test_high_frequency_ratio_uses_explicit_two_kilohertz_crossover() -> None:
    sr = 44_100
    time = np.arange(sr * 2) / sr
    low = analyze_acoustic_measurements(0.5 * np.sin(2 * np.pi * 500 * time), sr)
    high = analyze_acoustic_measurements(0.5 * np.sin(2 * np.pi * 5000 * time), sr)
    assert low["high_frequency_energy_ratio"] < 0.05
    assert high["high_frequency_energy_ratio"] > 0.95


def test_clipping_ratio_is_absolute_full_scale_measurement() -> None:
    audio = np.full(10_000, 0.25, dtype=float)
    audio[:1000] = 1.0
    result = analyze_acoustic_measurements(audio, 10_000)
    assert abs(result["clipping_candidate_ratio"] - 0.1) < 1e-8
