from app.modules.library.bass_model_validation import (
    capability_is_validated,
    resolve_bass_model_validation,
)


def _route(*, version: str = "0.4.0", model_name: str = "nmp.mlpackage") -> dict:
    return {
        "status": "ready",
        "result": {
            "engine": "spotify_basic_pitch",
            "model_name": model_name,
            "model_version": version,
        },
    }


def test_exact_basic_pitch_artifact_resolves_heldout_validation() -> None:
    result = resolve_bass_model_validation(_route())

    assert result["status"] == "matched"
    assert result["output_confidence_threshold"] == 0.35
    assert capability_is_validated(result, "bass_note_onset_and_pitch") is True
    assert capability_is_validated(result, "pitch_bend_or_slide") is False


def test_changed_model_artifact_is_not_covered() -> None:
    result = resolve_bass_model_validation(_route(model_name="other.onnx"))

    assert result["status"] == "unvalidated"
    assert capability_is_validated(result, "bass_note_onset_and_pitch") is False
