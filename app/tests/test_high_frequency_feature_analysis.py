from __future__ import annotations

import numpy as np

from app.modules.library.high_frequency_feature_analysis import analyze_high_frequency_features


def test_pipeline_combines_existing_music_context_and_time_frequency_modules() -> None:
    sr = 8000
    duration = 10
    time = np.arange(sr * duration) / sr
    stems = {
        "bass": (0.3 * np.sin(2 * np.pi * 55 * time)).astype(np.float32),
        "drums": np.zeros(sr * duration, dtype=np.float32),
        "vocals": (0.2 * np.sin(2 * np.pi * 220 * time)).astype(np.float32),
        "other": (0.1 * np.sin(2 * np.pi * 440 * time)).astype(np.float32),
    }
    kick_times = np.arange(0, duration, 0.5)
    stems["drums"][(kick_times * sr).astype(int)] = 0.8
    analysis = {"events": {
        "kick": [{"time": float(value)} for value in kick_times],
        "snare": [{"time": float(value)} for value in np.arange(0.5, duration, 1.0)],
        "hihat": [{"time": float(value)} for value in np.arange(0.25, duration, 0.5)],
    }}
    beats = np.arange(0, duration, 0.5)
    downbeats = np.arange(0, duration + 0.01, 2.0)

    result = analyze_high_frequency_features(
        stems, sr, bpm=120.0, beat_points=beats.tolist(), downbeats=downbeats.tolist(),
        drum_analysis=analysis, key_profile={"tonal_clarity": 0.8},
    )

    assert result["version"] == "pre_style_evidence_v4"
    assert result["music_context"]["bpm"] == 120.0
    assert result["music_context"]["tempo_family"] == {
        "status": "candidate_levels_only",
        "half": 60.0,
        "base": 120.0,
        "double": 240.0,
        "octave_relation_detected": False,
    }
    assert result["music_context"]["analysis_sample_rate"] == 22050
    assert result["music_context"]["high_frequency_sample_rate"] == sr
    assert result["analysis_modules"]["percussion"]["analysis_sample_rate"] == sr
    assert result["feature_groups"]["rhythm_grammar"]["four_on_floor"]["availability"] == "available"
    assert "sub_808" in result["feature_groups"]["low_frequency"]
    assert "wide_clap" in result["feature_groups"]["percussion_timbre"]
    assert "singing" in result["feature_groups"]["vocal_delivery"]
    assert "harmonic_complexity" in result["feature_groups"]["harmony"]
    assert "lofi_texture" in result["feature_groups"]["production"]


def test_pipeline_missing_audio_is_explicitly_unavailable() -> None:
    result = analyze_high_frequency_features({}, 0)

    assert result["status"] == "unavailable"
    assert result["feature_groups"]["low_frequency"]["analysis"]["detected"] is None
