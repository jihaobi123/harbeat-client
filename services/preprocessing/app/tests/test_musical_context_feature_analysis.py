from __future__ import annotations

import numpy as np

from app.modules.library.feature_calibration import apply_feature_calibration
from app.modules.library.musical_context_feature_analysis import (
    _harmony_features,
    _production_features,
    _vocal_features,
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
    assert "vocal_pitch_range" in result["vocal_delivery"]
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
    measurements = result["objective_production_measurements"]
    assert measurements["status"] == "ready"
    assert measurements["high_frequency_crossover_hz"] == 2000.0
    assert measurements["definitions"]["active_frame"] == "frame power within 60 dB of track maximum"
    assert harmony["analysis_method"] == "beat_synchronous_chroma_harmony_v4"
    assert "rage_synth_candidate" in result["production"]


def test_missing_sources_stay_unavailable() -> None:
    result = analyze_musical_context_features(
        vocals=None, other=None, original_audio=None, sr=22050,
    )

    assert result["vocal_delivery"]["rap_delivery"]["detected"] is None
    assert result["harmony"]["jazz_soul_harmony"]["detected"] is None
    assert result["production"]["lofi_texture"]["detected"] is None


def test_validated_yamnet_route_replaces_only_vocal_density_measurement() -> None:
    route = {
        "status": "ready",
        "engine": "essentia_yamnet_voice_instrumental",
        "license": "test-model-license",
        "result": {
            "engine": "essentia_yamnet_voice_instrumental",
            "model_version": "test",
            "duration_seconds": 12.0,
            "frame_count": 12,
            "patch_window_seconds": 0.96,
            "patch_hop_seconds": 0.93,
            "voice_decision_threshold": 0.88,
            "vocal_activity_fraction": 0.5,
            "vocal_density": 0.42,
            "calibration": {"version": "jamendo_svd_valid16_platt_v1"},
            "time_ranges": [{"start": 1.0, "end": 3.0}],
        },
    }

    features, quality, _ = _vocal_features(None, 8000, vocal_activity_route=route)
    density = features["vocal_density"]

    assert density["score"] == 0.42
    assert density["analysis_method"] == "essentia_yamnet_voice_activity_jamendo_v1"
    assert density["time_ranges"] == [{"start": 1.0, "end": 3.0}]
    assert features["singing"]["availability"] == "unavailable"
    assert quality > 0


def test_unbenchmarked_vocal_route_is_not_accepted_as_validated_density() -> None:
    route = {
        "status": "ready",
        "result": {
            "engine": "unknown_voice_model",
            "vocal_density": 0.9,
            "calibration": {"version": "unknown"},
        },
    }
    features, quality, _ = _vocal_features(None, 8000, vocal_activity_route=route)
    assert features["vocal_density"]["availability"] == "unavailable"
    assert quality == 0.0


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

    periodic_features, _, _ = _production_features(periodic, periodic, sr, beats)
    evolving_features, _, _ = _production_features(evolving, evolving, sr, beats)

    periodic_texture = periodic_features["sample_texture"]
    evolving_texture = evolving_features["sample_texture"]
    assert periodic_texture["score"] > 0.8
    assert evolving_texture["score"] < 0.55
    assert periodic_texture["evidence"]["sample_repeat_sampling_mode"] == "beat_synchronous_lags_4_8_16"


def test_chord_model_segments_replace_chroma_distance_for_change_rate() -> None:
    sr = 8000
    duration = 8.0
    time = np.arange(sr * duration) / sr
    audio = np.sin(2 * np.pi * 220.0 * time).astype(np.float32)
    beats = np.arange(0.0, duration, 0.5)
    route = {
        "status": "ready",
        "engine": "madmom_cnn_crf_chords",
        "result": {
            "segments": [
                {"start": 0.0, "end": 2.0, "label": "C:maj"},
                {"start": 2.0, "end": 4.0, "label": "F:maj"},
                {"start": 4.0, "end": 6.0, "label": "G:maj"},
                {"start": 6.0, "end": 8.0, "label": "C:maj"},
            ],
        },
    }

    features, _ = _harmony_features(audio, sr, {}, beats, route)
    change = features["chord_change_activity"]

    assert change["evidence"]["chord_change_count"] == 3
    assert change["evidence"]["chord_changes_per_four_beats"] == 0.8
    assert change["evidence"]["harmony_sampling_mode"] == "madmom_cnn_crf_chord_segments_per_four_beats"
    assert "chord_transcription" in change["sources"]
    assert change["quality"]["reliability_cap"] == 0.85
    assert change["analysis_method"] == "cnn_crf_chord_change_activity_other_stem_v2"
    calibrated = apply_feature_calibration(
        change, group="harmony", name="chord_change_activity",
    )
    assert calibrated["validation_status"] == "provisional"
    assert calibrated["calibration_method_supported"] is False


def test_chroma_fallback_keeps_failed_guitarset_metrics_visible() -> None:
    sr = 8000
    duration = 5.0
    time = np.arange(int(sr * duration)) / sr
    audio = np.sin(2 * np.pi * 220.0 * time).astype(np.float32)

    features, _ = _harmony_features(audio, sr, {}, np.arange(0.0, duration, 0.5))
    change = features["chord_change_activity"]
    validation = change["evidence"]["chroma_change_heldout_validation"]

    assert change["analysis_method"] == "beat_synchronous_chroma_harmony_v4"
    assert validation["status"] == "failed_validation"
    assert validation["f1"] == 0.5238
    assert validation["mean_absolute_error"] == 0.291


def test_vocal_chop_requires_repetition_and_beat_grid_alignment() -> None:
    sr = 8000
    duration = 6.0
    audio = np.zeros(sr * 6, dtype=np.float32)
    rng = np.random.default_rng(21)
    for start in np.arange(0.25, duration - 0.2, 0.5):
        index = int(start * sr)
        length = int(0.16 * sr)
        audio[index:index + length] = (
            rng.normal(0, 0.2, length) * np.hanning(length)
        ).astype(np.float32)
    beats = np.arange(0.0, duration, 0.5)

    features, _, _ = _vocal_features(audio, sr, beats)
    chop = features["vocal_chop"]

    assert chop["evidence"]["beat_grid_alignment"] > 0.6
    assert chop["quality"]["reliability_cap"] == 0.68


def test_clipping_measurement_uses_digital_full_scale_not_relative_track_peak() -> None:
    sr = 8000
    time = np.arange(sr * 4) / sr
    normal = (0.5 * np.sin(2 * np.pi * 220.0 * time)).astype(np.float32)
    clipped = np.clip(2.0 * np.sin(2 * np.pi * 220.0 * time), -1.0, 1.0).astype(np.float32)

    normal_features, _, _ = _production_features(normal, normal, sr)
    clipped_features, _, _ = _production_features(clipped, clipped, sr)

    assert normal_features["distortion"]["evidence"]["clipping_candidate_ratio"] == 0.0
    assert clipped_features["distortion"]["evidence"]["clipping_candidate_ratio"] > 0.1
