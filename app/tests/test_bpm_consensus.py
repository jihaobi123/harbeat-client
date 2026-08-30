from app.modules.library.analysis import _choose_bpm_consensus


def test_metrical_reference_is_not_outvoted_by_two_half_tempo_routes() -> None:
    result = _choose_bpm_consensus({
        "beat_this": {"bpm": 170.0},
        "all_in_one": {"bpm": 85.0},
        "essentia": {"bpm": 85.2},
    })

    assert result["bpm"] == 170.0
    assert result["selected_engine"] == "beat_this"
    assert result["metrical_level_conflict"] is True
    assert result["selection_strategy"] == "validated_metrical_reference_v1"


def test_same_level_measurement_is_median_smoothed_around_reference() -> None:
    result = _choose_bpm_consensus({
        "beat_this": {"bpm": 130.4},
        "all_in_one": {"bpm": 128.0},
        "essentia": {"bpm": 172.0},
    }, tolerance=3.0)

    assert result["bpm"] == 129.2
    assert result["winning_engines"] == ["beat_this", "all_in_one"]


def test_missing_reference_uses_largest_exact_value_group() -> None:
    result = _choose_bpm_consensus({
        "all_in_one": {"bpm": 124.0},
        "essentia": {"bpm": 125.0},
    })

    assert result["bpm"] == 124.5
    assert result["selection_strategy"] == "degraded_exact_value_group"
    assert result["needs_review"] is True
