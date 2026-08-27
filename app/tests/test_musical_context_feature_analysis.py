from __future__ import annotations

import numpy as np

from app.modules.library.musical_context_feature_analysis import analyze_musical_context_features


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
    assert harmony["analysis_method"] == "chroma_harmony_activity_v1"


def test_missing_sources_stay_unavailable() -> None:
    result = analyze_musical_context_features(
        vocals=None, other=None, original_audio=None, sr=22050,
    )

    assert result["vocal_delivery"]["rap_delivery"]["detected"] is None
    assert result["harmony"]["jazz_soul_harmony"]["detected"] is None
    assert result["production"]["lofi_texture"]["detected"] is None
