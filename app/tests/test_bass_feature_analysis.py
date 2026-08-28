from __future__ import annotations

import numpy as np

from app.modules.library.bass_feature_analysis import (
    _bass_groove_descriptors,
    _pitch_track,
    analyze_bass_features,
)


def _tone_events(
    *,
    sr: int = 8000,
    duration: float = 8.0,
    slide: bool = False,
) -> tuple[np.ndarray, list[float]]:
    audio = np.zeros(int(sr * duration), dtype=np.float32)
    times = [0.5 + index for index in range(7)]
    event_length = int(0.72 * sr)
    local_time = np.arange(event_length) / sr
    for event_time in times:
        if slide:
            frequency = 48.0 * np.power(2.0, 5.0 * local_time / 0.72 / 12.0)
            phase = 2 * np.pi * np.cumsum(frequency) / sr
        else:
            phase = 2 * np.pi * 48.0 * local_time
        envelope = np.exp(-local_time * 2.4)
        tone = (np.sin(phase) + 0.24 * np.sin(phase * 2)) * envelope * 0.6
        start = int(event_time * sr)
        audio[start:start + event_length] += tone.astype(np.float32)
    return audio, times


def _separate_note_events(sr: int = 8000) -> np.ndarray:
    """Distinct notes create range between events, but no within-event slide."""
    audio = np.zeros(sr * 8, dtype=np.float32)
    frequencies = [40.0, 48.0, 60.0, 72.0, 54.0, 45.0, 67.0]
    event_length = int(0.72 * sr)
    local_time = np.arange(event_length) / sr
    envelope = np.exp(-local_time * 2.4)
    for index, frequency in enumerate(frequencies):
        start = int((0.5 + index) * sr)
        audio[start:start + event_length] += (
            0.6 * np.sin(2 * np.pi * frequency * local_time) * envelope
        ).astype(np.float32)
    return audio


def _drum_track(sr: int, duration: float, times: list[float]) -> np.ndarray:
    audio = np.zeros(int(sr * duration), dtype=np.float32)
    burst_length = int(0.045 * sr)
    rng = np.random.default_rng(7)
    for value in times:
        start = int(value * sr)
        audio[start:start + burst_length] += (
            rng.normal(0, 0.35, burst_length) * np.linspace(1.0, 0.0, burst_length)
        ).astype(np.float32)
    return audio


def test_808_identity_uses_bass_body_and_drum_attack_without_requiring_slide() -> None:
    sr = 8000
    bass, times = _tone_events(sr=sr)
    drums = _drum_track(sr, 8.0, times)
    drum_analysis = {"events": {"kick": [{"time": value} for value in times]}}

    result = analyze_bass_features(
        bass,
        drums,
        sr,
        drum_analysis=drum_analysis,
        beat_points=np.arange(0, 8, 0.5),
        original_audio=bass + drums,
    )

    assert result["features"]["sub_808"]["score"] > 0.55
    assert result["features"]["bass_slide"]["detected"] is False
    assert result["features"]["sliding_808"]["detected"] is False
    assert result["features"]["sub_808"]["sources"] == ["bass_stem", "drums_stem", "full_mix"]
    assert result["features"]["sub_808"]["deprecated_alias_for"] == "808_timbre_candidate"
    assert result["features"]["808_timbre_candidate"]["evidence_level"] in {
        "candidate", "probable", "confirmed",
    }
    assert result["features"]["808_timbre_candidate"]["quality"]["estimator_quality"] == 0.58
    assert "sine_dominance_score" in result["features"]["808_timbre_candidate"]["evidence"]
    assert (
        result["features"]["sustained_harmonic_bass_candidate"]["score"]
        != result["features"]["808_timbre_candidate"]["score"]
    )


def test_bass_slide_is_reported_separately_from_808_identity() -> None:
    sr = 8000
    bass, times = _tone_events(sr=sr, slide=True)
    result = analyze_bass_features(
        bass,
        np.zeros_like(bass),
        sr,
        drum_analysis={"events": {"kick": []}},
        beat_points=np.arange(0, 8, 0.5),
        original_audio=bass,
    )

    assert result["features"]["bass_slide"]["score"] > 0.0
    assert "sub_808_identity_score" in result["features"]["sliding_808"]["evidence"]
    assert result["features"]["kick_bass_alignment"]["detected"] is None
    assert any(event["pitch_method"] == "pyin_candidate_segment" for event in result["events"])
    assert "bass_pitch_spectral_fallback_used" in result["quality_flags"]
    assert "low_frequency_melody" in result["features"]
    assert "bass_reply_pattern" in result["features"]


def test_pitch_range_between_separate_notes_is_not_a_bass_slide() -> None:
    sr = 8000
    bass = _separate_note_events(sr)

    result = analyze_bass_features(
        bass,
        np.zeros_like(bass),
        sr,
        drum_analysis={"events": {"kick": []}},
        beat_points=np.arange(0, 8, 0.5),
        original_audio=bass,
    )

    slide = result["features"]["bass_slide"]
    melody = result["features"]["low_frequency_melody"]
    assert slide["detected"] is False
    assert slide["evidence"]["slide_event_count"] == 0
    assert melody["evidence"]["event_pitch_range_semitones"] > 4.0
    assert "meaningful_interval_fraction" in melody["evidence"]


def test_pyin_tracks_fundamental_when_second_harmonic_is_stronger() -> None:
    sr = 8000
    time = np.arange(sr, dtype=float) / sr
    clip = 0.25 * np.sin(2 * np.pi * 48.0 * time)
    clip += 0.75 * np.sin(2 * np.pi * 96.0 * time)

    track = _pitch_track(clip.astype(np.float32), sr)

    assert track["method"] == "pyin_candidate_segment"
    assert 46.0 <= float(np.median(track["f0_hz"])) <= 50.0
    assert float(np.mean(track["voiced_prob"])) >= 0.60


def test_missing_bass_stem_is_unavailable_not_negative() -> None:
    result = analyze_bass_features(None, None, 22050)

    assert result["status"] == "unavailable"
    assert result["features"]["sub_808"]["availability"] == "unavailable"
    assert result["features"]["sub_808"]["detected"] is None


def test_groove_descriptors_measure_syncopation_octaves_and_riff_recurrence() -> None:
    beats = np.arange(0.0, 8.0, 0.5)
    downbeats = np.arange(0.0, 10.0, 2.0)
    kicks = np.arange(0.0, 8.0, 0.5)
    events = []
    for bar in range(4):
        for offset, frequency in ((0.125, 55.0), (0.625, 110.0), (1.125, 55.0), (1.625, 110.0)):
            events.append({
                "time": bar * 2.0 + offset,
                "decay_sec": 0.16,
                "fundamental_hz": frequency,
                "pitch_method": "pyin_candidate_segment",
                "voiced_strength": 0.9,
            })

    result = _bass_groove_descriptors(events, beats, downbeats, kicks)

    assert result["syncopation_score"] > 0.9
    assert result["staccato_score"] > 0.9
    assert result["octave_score"] > 0.9
    assert result["riff_score"] > 0.9
    assert result["interlock_score"] > 0.7


def test_new_bass_features_are_unknown_without_required_grids() -> None:
    bass, _ = _tone_events()
    result = analyze_bass_features(
        bass, np.zeros_like(bass), 8000,
        drum_analysis={"events": {"kick": []}},
        beat_points=[],
        downbeats=[],
        original_audio=bass,
    )

    assert result["features"]["bass_syncopation"]["detected"] is None
    assert result["features"]["bass_riff_repetition"]["detected"] is None
    assert result["features"]["bass_kick_interlock"]["detected"] is None
    assert result["features"]["bass_staccato_ratio"]["availability"] == "available"
