from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_bass_transcriber.py"
SPEC = spec_from_file_location("evaluate_bass_transcriber", SCRIPT)
MODULE = module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_note_metrics_matches_once_with_onset_and_pitch_tolerance():
    reference = [
        {"start": 1.0, "end": 1.4, "midi": 36.0},
        {"start": 2.0, "end": 2.4, "midi": 48.0},
    ]
    predicted = [
        {"start": 1.03, "end": 1.3, "midi": 36.4},
        {"start": 1.04, "end": 1.3, "midi": 36.0},
        {"start": 2.01, "end": 2.3, "midi": 49.0},
    ]
    result = MODULE.note_metrics(reference, predicted)
    assert result["true_positive"] == 1
    assert result["false_positive"] == 2
    assert result["false_negative"] == 1
    assert result["precision"] == 0.3333
    assert result["recall"] == 0.5


def test_split_id_is_deterministic_and_disjoint():
    assert MODULE._split_id("Track00001/S03") == MODULE._split_id("Track00001/S03")
    assert MODULE._split_id("Track00001/S03") in {"calibration", "heldout"}


def test_combining_metrics_cannot_cross_match_tracks():
    result = MODULE._combine_track_metrics([
        MODULE.note_metrics([{"start": 1, "end": 2, "midi": 36}], []),
        MODULE.note_metrics([], [{"start": 1, "end": 2, "midi": 36}]),
    ])
    assert result["true_positive"] == 0
    assert result["false_positive"] == 1
    assert result["false_negative"] == 1


def test_groove_events_use_sounding_midi_and_confidence_gate():
    result = MODULE._groove_events([
        {"start": 1.0, "end": 1.25, "midi": 45, "confidence": 0.44},
        {"start": 2.0, "end": 2.50, "midi": 33, "confidence": 0.80},
    ], confidence_threshold=0.45)

    assert len(result) == 1
    assert result[0]["time"] == 2.0
    assert result[0]["note_duration_sec"] == 0.5


def test_descriptor_release_gate_requires_all_accuracy_dimensions():
    passing = {
        "sample_count": 80,
        "positive_count": 30,
        "negative_count": 50,
        "within_0_20_fraction": 0.86,
        "accuracy": 0.87,
        "precision": 0.84,
        "recall": 0.82,
        "f1": 0.83,
    }
    assert MODULE._descriptor_release_gate(passing, track_count=8)["passed"] is True
    failed = MODULE._descriptor_release_gate({**passing, "precision": 0.79}, track_count=8)
    assert failed["passed"] is False
    assert "precision_below_0_80" in failed["reasons"]
