from app.modules.library.external_metadata.scorer import fuse_final_style_score


def test_final_style_score_uses_configured_weights():
    score = fuse_final_style_score(
        external_platform_score=0.8,
        local_fingerprint_score=0.6,
        manual_style_score=0.9,
        tunable_adjustment_score=0.7,
        weights={"external": 0.50, "local": 0.35, "manual": 0.10, "tunable": 0.05},
    )

    assert score == round(0.50 * 0.8 + 0.35 * 0.6 + 0.10 * 0.9 + 0.05 * 0.7, 4)


def test_final_style_score_normalizes_missing_components():
    score = fuse_final_style_score(
        external_platform_score=None,
        local_fingerprint_score=0.6,
        manual_style_score=None,
        tunable_adjustment_score=0.8,
        weights={"external": 0.50, "local": 0.35, "manual": 0.10, "tunable": 0.05},
    )

    assert score == round((0.35 * 0.6 + 0.05 * 0.8) / (0.35 + 0.05), 4)

