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
