from scripts.evaluate_groove_percussion_timbre import _gate


def test_percussion_release_gate_requires_balanced_heldout_quality() -> None:
    passing = {
        "positive_count": 100,
        "negative_count": 100,
        "accuracy": 0.86,
        "precision": 0.84,
        "recall": 0.82,
        "f1": 0.83,
    }
    assert _gate(passing, track_count=40)["passed"] is True
    assert _gate({**passing, "recall": 0.79}, track_count=40)["passed"] is False
