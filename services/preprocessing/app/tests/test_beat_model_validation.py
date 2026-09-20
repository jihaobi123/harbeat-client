from app.modules.library.beat_model_validation import resolve_beat_model_validation


def _route(confidence: float, *, engine: str = "beat_this:final0") -> dict:
    return {
        "engine": engine,
        "postprocessor": "minimal_50fps_probability_gt_0.5_peak_nms_70ms",
        "downbeat_peak_probability_mean": confidence,
    }


def test_exact_model_high_confidence_downbeats_are_validated() -> None:
    result = resolve_beat_model_validation(_route(0.94))
    assert result["beat_validated"] is True
    assert result["downbeat_validated"] is True
    assert result["meter_validated"] is True
    assert result["downbeat_status"] == "validated"


def test_low_confidence_downbeats_abstain_without_invalidating_beats() -> None:
    result = resolve_beat_model_validation(_route(0.90))
    assert result["beat_validated"] is True
    assert result["downbeat_validated"] is False
    assert result["meter_validated"] is False
    assert result["downbeat_status"] == "abstained_low_confidence"


def test_different_checkpoint_cannot_borrow_final0_validation() -> None:
    result = resolve_beat_model_validation(_route(0.99, engine="beat_this:final1"))
    assert result["status"] == "unvalidated"
    assert result["beat_validated"] is False
