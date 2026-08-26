import numpy as np

from app.modules.library.analysis import (
    _choose_downbeat_consensus,
    _downbeat_match_metrics,
)


def _result(values: list[float], engine: str) -> dict:
    return {"downbeats": values, "engine": engine, "confidence": 0.9}


def test_downbeat_matching_uses_seventy_millisecond_window() -> None:
    metrics = _downbeat_match_metrics(
        [0.0, 2.0, 4.0, 6.0],
        [0.05, 2.04, 4.06, 6.08],
        tolerance=0.07,
    )

    assert metrics["matches"] == 3
    assert metrics["f1"] == 0.75
    assert metrics["mean_error_ms"] == 50.0


def test_three_native_models_choose_all_in_one_when_unanimous() -> None:
    base = [float(value) for value in np.arange(0.5, 20.5, 2.0)]
    selected, consensus = _choose_downbeat_consensus(
        {
            "beat_this": _result(base, "beat_this:final0"),
            "all_in_one": _result([value + 0.02 for value in base], "all_in_one:harmonix-all"),
            "madmom": _result([value - 0.02 for value in base], "madmom_infer:rnn_dbn"),
        },
        accent_fallback=base,
    )

    assert selected == [round(value + 0.02, 3) for value in base]
    assert consensus["selected_engine"] == "all_in_one"
    assert consensus["status"] == "unanimous"
    assert consensus["agreement_count"] == 3
    assert consensus["needs_review"] is False


def test_two_models_form_majority_and_choose_native_sequence() -> None:
    base = [float(value) for value in np.arange(0.5, 20.5, 2.0)]
    wrong_phase = [value + 0.5 for value in base]
    selected, consensus = _choose_downbeat_consensus(
        {
            "beat_this": _result(base, "beat_this:final0"),
            "all_in_one": _result([value + 0.03 for value in base], "all_in_one:harmonix-all"),
            "madmom": _result(wrong_phase, "madmom_infer:rnn_dbn"),
        },
        accent_fallback=base,
    )

    assert selected == [round(value + 0.03, 3) for value in base]
    assert consensus["winning_engines"] == ["all_in_one", "beat_this"]
    assert consensus["status"] == "majority"
    assert consensus["needs_review"] is False


def test_accent_route_only_breaks_a_native_model_tie() -> None:
    accent = [float(value) for value in np.arange(0.5, 20.5, 2.0)]
    selected, consensus = _choose_downbeat_consensus(
        {
            "beat_this": _result([value + 0.02 for value in accent], "beat_this:final0"),
            "all_in_one": _result([value + 0.5 for value in accent], "all_in_one:harmonix-all"),
        },
        accent_fallback=accent,
    )

    assert selected == [round(value + 0.02, 3) for value in accent]
    assert consensus["selected_engine"] == "beat_this"
    assert consensus["status"] == "accent_tiebreak"
    assert consensus["needs_review"] is True


def test_local_accent_is_last_fallback_not_a_model_vote() -> None:
    accent = [0.5, 2.5, 4.5]
    selected, consensus = _choose_downbeat_consensus({}, accent_fallback=accent)

    assert selected == accent
    assert consensus["selected_engine"] == "accent_fallback"
    assert consensus["status"] == "fallback"
    assert consensus["available_count"] == 0
    assert consensus["needs_review"] is True


def test_bpm_period_filter_rejects_incompatible_bar_grid() -> None:
    expected = [round(value, 3) for value in np.arange(1.1, 40.0, 4 * 60 / 110)]
    wrong_73_bpm_grid = [round(value, 3) for value in np.arange(2.4, 40.0, 4 * 60 / 73)]
    wrong_double_tempo_grid = [round(value, 3) for value in np.arange(0.2, 40.0, 2 * 60 / 110)]

    selected, consensus = _choose_downbeat_consensus(
        {
            "beat_this": _result(wrong_double_tempo_grid, "beat_this:final0"),
            "all_in_one": _result(wrong_73_bpm_grid, "all_in_one:harmonix-all"),
            "madmom": _result(expected, "madmom_infer:rnn_dbn"),
        },
        accent_fallback=[value + 0.5 for value in expected],
        bpm=110.0,
    )

    assert selected == expected
    assert consensus["selected_engine"] == "madmom"
    assert consensus["status"] == "period_filtered"
    assert consensus["eligible_count"] == 1
    assert consensus["rejected_engines"] == ["all_in_one", "beat_this"]
    assert consensus["period_validation"]["all_in_one"]["issue"] == "three_halves_bar"
    assert consensus["needs_review"] is True


def test_same_period_integer_beat_shift_is_phase_conflict() -> None:
    bar_period = 4 * 60 / 73
    beat_this = [round(value, 4) for value in np.arange(0.12, 45.0, bar_period)]
    all_in_one = [round(value, 4) for value in np.arange(8.32, 45.0, bar_period)]

    selected, consensus = _choose_downbeat_consensus(
        {
            "beat_this": _result(beat_this, "beat_this:final0"),
            "all_in_one": _result(all_in_one, "all_in_one:harmonix-all"),
        },
        accent_fallback=[],
        bpm=73.0,
    )

    assert selected == [round(value, 3) for value in beat_this]
    assert consensus["selected_engine"] == "beat_this"
    assert consensus["status"] == "phase_conflict"
    assert consensus["phase_conflicts"]["all_in_one:beat_this"]["shift_beats"] == 2
    assert consensus["period_validation"]["all_in_one"]["intro_coverage_ok"] is False
    assert consensus["needs_review"] is True


def test_majority_prefers_route_that_covers_the_intro() -> None:
    bar_period = 4 * 60 / 79
    full_song = [round(value, 4) for value in np.arange(0.24, 90.0, bar_period)]
    delayed = [value for value in full_song if value >= 12.0]
    doubled = [round(value, 4) for value in np.arange(0.23, 90.0, bar_period / 2)]

    selected, consensus = _choose_downbeat_consensus(
        {
            "beat_this": _result(full_song, "beat_this:final0"),
            "all_in_one": _result(delayed, "all_in_one:harmonix-all"),
            "madmom": _result(doubled, "madmom_infer:rnn_dbn"),
        },
        accent_fallback=full_song,
        bpm=79.0,
    )

    assert selected == [round(float(value), 3) for value in full_song]
    assert consensus["selected_engine"] == "beat_this"
    assert consensus["status"] == "majority"
    assert consensus["period_validation"]["all_in_one"]["intro_coverage_ok"] is False
    assert consensus["period_validation"]["madmom"]["issue"] == "half_bar"
    assert consensus["needs_review"] is True
