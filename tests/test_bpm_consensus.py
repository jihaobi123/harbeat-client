import threading

import numpy as np

import app.modules.library.analysis as analysis
from app.modules.library.analysis import _choose_bpm_consensus


def _result(bpm: float) -> dict:
    return {"bpm": bpm}


def test_consensus_uses_majority_within_two_bpm() -> None:
    consensus = _choose_bpm_consensus({
        "beat_this": _result(69.77),
        "all_in_one": _result(140.0),
        "essentia": _result(141.0),
    })

    assert consensus["bpm"] == 140.5
    assert consensus["winning_engines"] == ["all_in_one", "essentia"]
    assert consensus["selected_engine"] == "all_in_one"
    assert consensus["status"] == "majority"
    assert consensus["needs_review"] is False


def test_consensus_uses_three_way_median_when_all_agree() -> None:
    consensus = _choose_bpm_consensus({
        "beat_this": _result(140.0),
        "all_in_one": _result(140.8),
        "essentia": _result(141.0),
    })

    assert consensus["bpm"] == 140.8
    assert consensus["agreement_count"] == 3
    assert consensus["status"] == "unanimous"


def test_consensus_keeps_existing_engine_when_all_disagree() -> None:
    consensus = _choose_bpm_consensus({
        "beat_this": _result(70.0),
        "all_in_one": _result(105.0),
        "essentia": _result(140.0),
    })

    assert consensus["bpm"] == 140.0
    assert consensus["selected_engine"] == "essentia"
    assert consensus["status"] == "no_majority"
    assert consensus["needs_review"] is True


def test_consensus_marks_missing_engine_for_review() -> None:
    consensus = _choose_bpm_consensus({
        "beat_this": _result(99.8),
        "essentia": _result(100.1),
    })

    assert consensus["agreement_count"] == 2
    assert consensus["status"] == "degraded_agreement"
    assert consensus["needs_review"] is True


def test_three_engines_are_started_in_parallel(monkeypatch) -> None:
    barrier = threading.Barrier(3, timeout=2.0)

    def fake_result(bpm: float) -> dict:
        barrier.wait()
        return {
            "bpm": bpm,
            "beat_times": np.array([0.0, 0.5, 1.0]),
            "engine": "fake",
        }

    monkeypatch.setattr(analysis, "_analyze_rhythm_beat_this", lambda y, sr: fake_result(120.0))
    monkeypatch.setattr(analysis, "_analyze_rhythm_all_in_one", lambda y, sr: fake_result(120.5))
    monkeypatch.setattr(
        analysis,
        "_analyze_rhythm_essentia",
        lambda y, sr, max_duration=None: fake_result(121.0),
    )

    selected, consensus, results = analysis._analyze_rhythm_parallel(
        np.zeros(22050, dtype=np.float32), 22050,
    )

    assert len(results) == 3
    assert consensus["status"] == "unanimous"
    assert consensus["agreement_count"] == 3
    assert selected["bpm"] == 120.5
