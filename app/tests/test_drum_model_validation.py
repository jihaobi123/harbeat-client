from app.modules.library.drum_model_validation import (
    class_is_validated,
    resolve_drum_model_validation,
)


def _route(snare_threshold: float = 0.24) -> dict:
    return {
        "status": "ready",
        "result": {
            "engine": "adtof_pytorch_frame_rnn",
            "model_version": "0.1.0",
            "thresholds": {
                "35": 0.22, "38": snare_threshold, "47": 0.32,
                "42": 0.22, "49": 0.30,
            },
        },
    }


def test_exact_model_and_thresholds_resolve_heldout_validation() -> None:
    result = resolve_drum_model_validation(_route())

    assert result["status"] == "matched"
    assert class_is_validated(result, "kick") is True
    assert class_is_validated(result, "high_percussion") is True
    assert class_is_validated(result, "snare") is False


def test_threshold_change_invalidates_benchmark_claim() -> None:
    result = resolve_drum_model_validation(_route(0.05))

    assert result["status"] == "unvalidated"
    assert class_is_validated(result, "kick") is False
