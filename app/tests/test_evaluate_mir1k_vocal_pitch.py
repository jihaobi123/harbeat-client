from __future__ import annotations

import numpy as np

from scripts.evaluate_mir1k_vocal_pitch import (
    align_to_reference,
    song_group,
    split_for,
    summarize,
)
from app.modules.library.vocal_pitch_analysis import vocal_pitch_descriptors


def test_split_keeps_clips_from_one_song_together() -> None:
    assert song_group("amy_4_01") == "amy_4"
    assert split_for("amy_4_01") == split_for("amy_4_12")


def test_reference_alignment_uses_twenty_millisecond_frame_centres() -> None:
    values = np.arange(100, dtype=float)
    aligned = align_to_reference(values, 3)
    # 20, 40 and 60 ms map to the nearest 256/22050 analysis hops.
    assert aligned.tolist() == [2.0, 3.0, 5.0]


def test_pitch_motion_does_not_jump_across_unvoiced_gap() -> None:
    midi = np.asarray([60.0, 60.2, 60.4, 0.0, 72.0, 72.2, 72.4])
    descriptors = vocal_pitch_descriptors(
        midi, np.ones(7, dtype=bool), frame_hop_seconds=0.05,
    )
    assert np.isclose(descriptors["median_100ms_contiguous_motion_semitones"], 0.4)


def test_sustain_bridges_only_short_internal_active_gap() -> None:
    short_gap = vocal_pitch_descriptors(
        np.asarray([60.0] * 8 + [0.0] * 2 + [60.0] * 8),
        np.ones(18, dtype=bool),
        frame_hop_seconds=0.02,
    )
    long_gap = vocal_pitch_descriptors(
        np.asarray([60.0] * 8 + [0.0] * 4 + [60.0] * 8),
        np.ones(20, dtype=bool),
        frame_hop_seconds=0.02,
    )
    assert short_gap["pitch_sustain_ratio"] == 1.0
    assert long_gap["pitch_sustain_ratio"] == 0.0


def test_summary_uses_frame_and_descriptor_ground_truth() -> None:
    reference = np.asarray([False, True, True, False])
    row = {
        "reference_voiced": reference,
        "predicted_voiced": reference.copy(),
        "correct_pitch": np.asarray([False, True, True, False]),
        "reference_descriptors": {
            "pitch_range_semitones": 8.0,
            "median_100ms_contiguous_motion_semitones": 1.2,
            "pitch_sustain_ratio": 0.7,
            "melodic_contour_score": 0.7,
        },
        "predicted_descriptors": {
            "pitch_range_semitones": 8.1,
            "median_100ms_contiguous_motion_semitones": 1.1,
            "pitch_sustain_ratio": 0.68,
            "melodic_contour_score": 0.69,
        },
    }
    result = summarize([row] * 50)
    assert result["frame_metrics"]["raw_pitch_accuracy_50_cent"] == 1.0
    assert result["frame_metrics"]["overall_accuracy_50_cent"] == 1.0
    assert result["descriptor_metrics"]["pitch_sustain_ratio"]["mean_absolute_error"] == 0.02
    assert result["feature_release_gates"]["vocal_pitch_frame_track"]["passed"] is True
    assert result["feature_release_gates"]["pitch_sustain_ratio"]["passed"] is True
