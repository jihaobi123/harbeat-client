from scripts.evaluate_public_style_benchmark import evaluate


def _track(clip_id: str, top: str, detected: list[str], feature_score: float) -> dict:
    styles = [{"style_id": name, "score": 0.8 if name == top else 0.2} for name in ("funk", "disco", "house")]
    return {
        "file": f"/tmp/{clip_id}.wav",
        "status": "completed",
        "style_analysis": {
            "primary_style_candidate": {"style_id": top},
            "primary_style": {"style_id": detected[0]} if detected else None,
            "detected_styles": [{"style_id": value} for value in detected],
            "styles": styles,
        },
        "stem_analysis": {"feature_analysis": {"feature_groups": {
            "low_frequency": {"bass_syncopation": {"score": feature_score, "reliability": 0.6}},
        }}},
    }


def test_public_evaluator_separates_top_boundary_and_multilabel_hits() -> None:
    manifest = [
        {"clip_id": "one", "expected_styles": ["funk", "disco"]},
        {"clip_id": "two", "expected_styles": ["house"]},
    ]
    results = {"tracks": [
        _track("one", "funk", ["funk"], 0.8),
        _track("two", "disco", [], 0.2),
    ]}

    summary = evaluate(manifest, results)

    assert summary["top_candidate_hit_ratio"] == 0.5
    assert summary["boundary_only_candidate_hit_ratio"] == 0.5
    assert summary["detected_any_expected_ratio"] == 0.5
    assert summary["no_primary_style_count"] == 1
    assert summary["feature_statistics"]["low_frequency.bass_syncopation"]["mean"] == 0.5
