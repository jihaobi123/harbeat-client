from app.modules.library.key_model_validation import resolve_key_model_validation


def _route(confidence: float, *, version: str = "0.16.1") -> dict:
    return {
        "engine": "madmom_cnn",
        "model_version": version,
        "worker_engine": "madmom_cnn_key_recognition",
        "key_confidence": confidence,
    }


def test_locked_high_confidence_route_is_validated() -> None:
    result = resolve_key_model_validation(_route(0.82))
    assert result["validated"] is True
    assert result["heldout_exact_accuracy"] == 0.8367


def test_low_confidence_route_abstains() -> None:
    result = resolve_key_model_validation(_route(0.79))
    assert result["validated"] is False
    assert result["decision"] == "abstained_low_confidence"


def test_unknown_model_version_cannot_borrow_validation() -> None:
    result = resolve_key_model_validation(_route(0.99, version="different"))
    assert result["status"] == "unvalidated"
