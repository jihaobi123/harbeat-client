from __future__ import annotations

import numpy as np

from scripts.evaluate_style_model import _leakage_checks
from scripts.extract_style_embeddings import _downbeat_windows, _fixed_windows
from scripts.train_style_model import _aggregate_track_probabilities, _cross_validate, _sample_weights


def test_downbeat_windows_use_16_bars_with_8_bar_hop():
    core = {
        "downbeats": np.arange(0.0, 66.0, 2.0).tolist(),
        "beat_confidence": 0.95,
        "beat_needs_review": False,
        "time_signature": {
            "needs_review": False,
            "downbeat_consensus": {"needs_review": False},
        },
    }

    windows, flags = _downbeat_windows(core, duration=66.0)

    assert flags == []
    assert windows == [(0.0, 32.0), (16.0, 48.0), (32.0, 64.0)]


def test_unreliable_downbeats_are_rejected_and_fixed_windows_cover_tail():
    core = {
        "downbeats": np.arange(0.0, 66.0, 2.0).tolist(),
        "beat_confidence": 0.95,
        "beat_needs_review": True,
        "time_signature": {"needs_review": True},
    }

    windows, flags = _downbeat_windows(core, duration=66.0)

    assert windows == []
    assert "downbeat_needs_review" in flags
    assert _fixed_windows(66.0) == [(0.0, 30.0), (15.0, 45.0), (30.0, 60.0)]


def test_track_aggregation_does_not_count_segments_as_independent_tracks():
    classes = ["a", "b", "c"]
    rows = [
        {"track_id": "t1", "start_seconds": 0.0, "structural_neutral": False},
        {"track_id": "t1", "start_seconds": 15.0, "structural_neutral": False},
        {"track_id": "t2", "start_seconds": 0.0, "structural_neutral": False},
    ]
    probabilities = np.asarray([
        [0.8, 0.1, 0.1],
        [0.7, 0.2, 0.1],
        [0.1, 0.7, 0.2],
    ])

    track_ids, aggregated, indices = _aggregate_track_probabilities(probabilities, rows, classes)

    assert track_ids == ["t1", "t2"]
    assert aggregated.shape == (2, 3)
    assert int(np.argmax(aggregated[0])) == 0
    assert int(np.argmax(aggregated[1])) == 1
    assert indices["t1"] == [0, 1]


def test_sample_weight_gives_each_track_equal_total_weight_within_class():
    rows = [
        {"track_id": "long", "primary_style": "a"},
        {"track_id": "long", "primary_style": "a"},
        {"track_id": "long", "primary_style": "a"},
        {"track_id": "short", "primary_style": "a"},
        {"track_id": "other", "primary_style": "b"},
    ]

    weights = _sample_weights(rows)

    assert np.isclose(np.sum(weights[:3]), weights[3])


def test_cross_validation_keeps_complete_tracks_in_declared_folds():
    rng = np.random.default_rng(7)
    classes = ["a", "b", "c"]
    rows = []
    vectors = []
    for class_index, label in enumerate(classes):
        for fold in range(4):
            track_id = f"{label}_{fold}"
            for segment in range(2):
                rows.append({
                    "segment_id": f"{track_id}_{segment}",
                    "track_id": track_id,
                    "primary_style": label,
                    "fold": fold,
                    "start_seconds": segment * 15.0,
                    "structural_neutral": False,
                })
                vector = rng.normal(scale=0.05, size=12)
                vector[class_index] += 2.0
                vectors.append(vector)

    summary, oof, predictions = _cross_validate(
        "synthetic", np.asarray(vectors), rows, classes, "logreg",
    )

    assert oof.shape == (24, 3)
    assert len(predictions) == 12
    assert summary["overall"]["top1_accuracy"] == 1.0


def test_leakage_check_rejects_metadata_features_and_cross_fold_artist():
    manifest = [
        {"track_id": "a", "fold": 0, "artist_group": "same"},
        {"track_id": "b", "fold": 1, "artist_group": "same"},
    ]
    segments = [{"segment_id": "a_0", "track_id": "a", "fold": 0}]

    result = _leakage_checks(
        manifest, segments, {"technical": {"names": ["rms_mean", "artist_code"]}},
    )

    assert result["passed"] is False
    assert result["artist_groups_crossing_folds"] == {"same": [0, 1]}
    assert result["forbidden_model_features"] == ["artist_code"]
