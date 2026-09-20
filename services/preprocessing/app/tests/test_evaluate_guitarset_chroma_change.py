from scripts.evaluate_guitarset_chroma_change import summarize


def test_chroma_change_summary_keeps_continuous_error_and_binary_scores_separate() -> None:
    result = summarize([
        {"reference_activity": 0.2, "predicted_activity": 0.3},
        {"reference_activity": 0.8, "predicted_activity": 0.9},
    ])
    assert result["binary_metrics"]["accuracy"] == 1.0
    assert result["mean_absolute_error"] == 0.1
    assert result["within_0_20_fraction"] == 1.0
