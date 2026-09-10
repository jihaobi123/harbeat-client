from __future__ import annotations

from scripts.calibrate_drum_pair_thresholds import audit_split, calibrate, evaluate


def test_calibration_recovers_separated_three_band_data() -> None:
    rows = [
        {"score": 0.20, "human_band": "fx_transition"},
        {"score": 0.40, "human_band": "fx_transition"},
        {"score": 0.72, "human_band": "standard_mix"},
        {"score": 0.80, "human_band": "standard_mix"},
        {"score": 0.90, "human_band": "harmonic_check"},
        {"score": 0.96, "human_band": "harmonic_check"},
    ]

    low, high, category_weight, metrics = calibrate(rows)

    assert 0.40 < low <= 0.72
    assert 0.80 <= high < 0.90
    assert category_weight is None
    assert metrics["macro_f1"] == 1.0


def test_calibration_can_optimize_component_weight() -> None:
    rows = [
        {
            "score": 0.0,
            "category_overlap_score": 0.10,
            "rhythm_landing_similarity_score": 0.20,
            "human_band": "fx_transition",
        },
        {
            "score": 0.0,
            "category_overlap_score": 0.90,
            "rhythm_landing_similarity_score": 0.42,
            "human_band": "standard_mix",
        },
        {
            "score": 0.0,
            "category_overlap_score": 0.95,
            "rhythm_landing_similarity_score": 0.96,
            "human_band": "harmonic_check",
        },
    ]

    _, _, category_weight, metrics = calibrate(rows)

    assert category_weight is not None
    assert metrics["macro_f1"] == 1.0


def test_evaluation_reports_every_class() -> None:
    rows = [
        {"score": 0.50, "human_band": "fx_transition"},
        {"score": 0.75, "human_band": "standard_mix"},
        {"score": 0.90, "human_band": "harmonic_check"},
    ]

    metrics = evaluate(rows, 0.70, 0.85)

    assert metrics["accuracy"] == 1.0
    assert set(metrics["classes"]) == {
        "fx_transition",
        "standard_mix",
        "harmonic_check",
    }


def test_split_audit_rejects_song_leakage() -> None:
    train = [
        {"song_a_id": "a", "song_b_id": "b", "human_band": label}
        for label in ("fx_transition", "standard_mix", "harmonic_check")
    ]
    test = [
        {"song_a_id": "b", "song_b_id": "c", "human_band": label}
        for label in ("fx_transition", "standard_mix", "harmonic_check")
    ]

    audit = audit_split(train, test)

    assert audit["song_disjoint"] is False
    assert audit["overlapping_song_ids"] == ["b"]
