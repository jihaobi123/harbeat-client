from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_giantsteps_key.py"
SPEC = spec_from_file_location("evaluate_giantsteps_key", SCRIPT)
MODULE = module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_mirex_key_relations() -> None:
    assert MODULE.mirex_key_score(("C", "major"), ("C", "major")) == ("exact", 1.0)
    assert MODULE.mirex_key_score(("C", "major"), ("G", "major")) == ("fifth", 0.5)
    assert MODULE.mirex_key_score(("C", "major"), ("A", "minor")) == ("relative", 0.3)
    assert MODULE.mirex_key_score(("C", "major"), ("C", "minor")) == ("parallel", 0.2)


def test_flat_annotation_normalizes_to_sharp() -> None:
    assert MODULE.parse_key("Bb minor") == ("A#", "minor")


def test_confidence_gate_reports_coverage_and_exact_accuracy() -> None:
    rows = [
        {
            "reference": ["C", "major"],
            "madmom": ["C", "major"] if index < 8 else ["C#", "major"],
            "route_confidences": {"madmom": 0.9},
        }
        for index in range(10)
    ] + [{
        "reference": ["C", "major"],
        "madmom": ["C#", "major"],
        "route_confidences": {"madmom": 0.5},
    }]
    metrics = MODULE.confidence_gated_key_metrics(rows, "madmom", threshold=0.8)
    assert metrics["sample_count"] == 10
    assert metrics["exact_accuracy"] == 0.8
    assert metrics["coverage"] == 0.9091
