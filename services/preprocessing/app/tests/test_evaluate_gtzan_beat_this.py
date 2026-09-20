from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_gtzan_beat_this.py"
SPEC = spec_from_file_location("evaluate_gtzan_beat_this", SCRIPT)
MODULE = module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_annotations_separate_downbeats(tmp_path: Path) -> None:
    annotation = tmp_path / "piece.beats"
    annotation.write_text("0.1\t1\n0.6\t2\n1.1\t3\n1.6\t4\n2.1\t1\n", encoding="utf-8")

    beats, downbeats = MODULE.read_annotations(annotation)

    assert beats == [0.1, 0.6, 1.1, 1.6, 2.1]
    assert downbeats == [0.1, 2.1]
    assert MODULE.reference_meter(annotation) == 4


def test_official_five_second_trim_applies_to_both_sides() -> None:
    assert MODULE.trim_events([0.2, 4.99, 5.0, 6.2]) == [5.0, 6.2]


def test_event_metrics_are_one_to_one() -> None:
    result = MODULE.event_metrics([5.01, 5.02, 6.04], [5.0, 6.0])
    assert result["matches"] == 2
    assert result["predicted_count"] == 3
    assert result["reference_count"] == 2


def test_release_gate_requires_micro_and_macro_metrics() -> None:
    passing = {
        "track_count": 31,
        "precision": 0.81,
        "recall": 0.82,
        "f1": 0.815,
        "macro_precision": 0.81,
        "macro_recall": 0.82,
        "macro_f1": 0.81,
    }
    assert MODULE.release_gate(passing)["passed"] is True
    failing = {**passing, "macro_recall": 0.79}
    assert MODULE.release_gate(failing)["passed"] is False


def test_meter_gate_requires_both_classes_and_balanced_accuracy() -> None:
    rows = [
        {"reference_meter": meter, "predicted_meter": meter}
        for meter in (3, 4) for _ in range(10)
    ]
    metrics = MODULE.meter_metrics(rows)
    assert metrics["balanced_accuracy"] == 1.0
    assert MODULE.meter_release_gate(metrics)["passed"] is True
