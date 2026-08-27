from __future__ import annotations

import numpy as np

from app.modules.library.musical_context_feature_analysis import (
    _harmony_features,
    _production_features,
    analyze_musical_context_features,
)


def test_sustained_pitched_vocal_produces_explicit_singing_evidence() -> None:
    sr = 8000
    duration = 6
    time = np.arange(sr * duration) / sr
    vibrato = 220.0 * np.power(2.0, 0.35 * np.sin(2 * np.pi * 5 * time) / 12.0)
    phase = 2 * np.pi * np.cumsum(vibrato) / sr
    vocals = (0.45 * np.sin(phase)).astype(np.float32)
    other = (0.15 * np.sin(2 * np.pi * 330 * time)).astype(np.float32)

    result = analyze_musical_context_features(
        vocals=vocals, other=other, original_audio=vocals + other, sr=sr,
        key_profile={"tonal_clarity": 0.8},
    )

    singing = result["vocal_delivery"]["singing"]
    assert singing["score"] > result["vocal_delivery"]["rap_delivery"]["score"]
    assert singing["evidence"]["voiced_fraction"] > 0.5
    assert singing["sources"] == ["vocals_stem"]
    assert "vocal_density" in result["vocal_delivery"]
    assert "syllabic_activity" in result["vocal_delivery"]
    assert "pitch_sustain_ratio" in result["vocal_delivery"]
    assert "melodic_contour" in result["vocal_delivery"]


def test_production_and_harmony_expose_measured_threshold_evidence() -> None:
    sr = 8000
    time = np.arange(sr * 5) / sr
    other = sum(np.sin(2 * np.pi * frequency * time) for frequency in (220, 277.18, 329.63, 415.3))
    other = (other / 8).astype(np.float32)
    result = analyze_musical_context_features(
        vocals=np.zeros_like(other), other=other, original_audio=other, sr=sr,
        key_profile={"tonal_clarity": 0.7},
    )

    harmony = result["harmony"]["harmonic_complexity"]
    production = result["production"]["electronic_production"]
    assert "mean_active_pitch_classes" in harmony["evidence"]
    assert "spectral_centroid_hz" in production["evidence"]
    assert "clipping_candidate_ratio" in production["evidence"]
    assert "sample_repeat_similarity" in production["evidence"]
    assert harmony["analysis_method"] == "beat_synchronous_chroma_harmony_v2"
    assert "rage_synth_candidate" in result["production"]


def test_missing_sources_stay_unavailable() -> None:
    result = analyze_musical_context_features(
        vocals=None, other=None, original_audio=None, sr=22050,
    )

    assert result["vocal_delivery"]["rap_delivery"]["detected"] is None
    assert result["harmony"]["jazz_soul_harmony"]["detected"] is None
    assert result["production"]["lofi_texture"]["detected"] is None


def test_beat_synchronous_chroma_distinguishes_static_and_changing_chords() -> None:
    sr = 8000
    duration = 12.0
    beats = np.arange(0.0, duration, 0.5)
    time = np.arange(int(sr * duration)) / sr
    static = sum(
        np.sin(2 * np.pi * frequency * time) for frequency in (261.63, 329.63, 392.0)
    ).astype(np.float32) / 3.0
    changing = np.zeros_like(static)
    chords = ((261.63, 329.63, 392.0), (349.23, 440.0, 523.25))
    for index, start_time in enumerate(beats[:-1]):
        start = int(start_time * sr)
        end = int(beats[index + 1] * sr)
        local_time = np.arange(end - start) / sr
        changing[start:end] = sum(
            np.sin(2 * np.pi * frequency * local_time)
            for frequency in chords[index % 2]
        ) / 3.0

    static_features, _ = _harmony_features(static, sr, {}, beats)
    changing_features, _ = _harmony_features(changing, sr, {}, beats)

    static_change = static_features["chord_change_activity"]
    changing_change = changing_features["chord_change_activity"]
    assert static_change["score"] < 0.15
    assert changing_change["score"] > 0.75
    assert changing_change["evidence"]["harmony_sampling_mode"] == "beat_synchronous"


def test_sample_texture_requires_recurrence_across_multiple_bar_lags() -> None:
    sr = 8000
    duration = 24.0
    beats = np.arange(0.0, duration, 0.5)
    periodic = np.zeros(int(sr * duration), dtype=np.float32)
    evolving = np.zeros_like(periodic)
    rng = np.random.default_rng(4)
    for index, start_time in enumerate(beats[:-1]):
        start = int(start_time * sr)
        end = int(beats[index + 1] * sr)
        local_time = np.arange(end - start) / sr
        periodic_frequency = (220.0, 330.0, 440.0, 550.0)[index % 4]
        periodic[start:end] = (
            np.sin(2 * np.pi * periodic_frequency * local_time) * (0.25 + 0.08 * (index % 4))
            + rng.normal(0, 0.01, end - start)
        )
        evolving_frequency = 170.0 + 13.0 * index
        evolving[start:end] = (
            np.sin(2 * np.pi * evolving_frequency * local_time) * (0.20 + 0.003 * index)
            + rng.normal(0, 0.01 + 0.0005 * index, end - start)
        )

    periodic_features, _ = _production_features(periodic, periodic, sr, beats)
    evolving_features, _ = _production_features(evolving, evolving, sr, beats)

    periodic_texture = periodic_features["sample_texture"]
    evolving_texture = evolving_features["sample_texture"]
    assert periodic_texture["score"] > 0.8
    assert evolving_texture["score"] < 0.55
    assert periodic_texture["evidence"]["sample_repeat_sampling_mode"] == "beat_synchronous_lags_4_8_16"
