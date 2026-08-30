from app.modules.library.tempo_model_validation import resolve_tempo_model_validation


def test_exact_strategy_and_reference_model_resolve() -> None:
    result = resolve_tempo_model_validation(
        {
            "selection_strategy": "validated_metrical_reference_v1",
            "metrical_reference_engine": "beat_this",
        },
        {"beat_this": {"engine": "beat_this:final0"}},
    )

    assert result["status"] == "matched"
    assert result["validated"] is True
    assert result["accuracy_1"] == 0.8387


def test_changed_reference_model_invalidates_claim() -> None:
    result = resolve_tempo_model_validation(
        {
            "selection_strategy": "validated_metrical_reference_v1",
            "metrical_reference_engine": "beat_this",
        },
        {"beat_this": {"engine": "beat_this:new-model"}},
    )

    assert result["status"] == "unvalidated"
