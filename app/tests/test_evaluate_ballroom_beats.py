from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evaluate_ballroom_beats.py"
SPEC = spec_from_file_location("evaluate_ballroom_beats", SCRIPT)
MODULE = module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_unannotated_intro_and_outro_predictions_are_trimmed() -> None:
    assert MODULE.trim_to_annotated_interval([0.2, 1.0, 2.0, 3.0], [1.0, 2.0]) == [1.0, 2.0]


def test_event_metrics_match_each_reference_once() -> None:
    result = MODULE.event_metrics([1.01, 1.02, 2.04], [1.0, 2.0])
    assert result["matches"] == 2
    assert result["predicted_count"] == 3
    assert result["reference_count"] == 2
