import numpy as np

from app.modules.library.section_relabeler import (
    RELABELER_SCHEMA_VERSION,
    SOURCE_STRUCTURE_LABELS,
    STRUCTURE_LABELS,
    apply_section_relabeler,
    build_track_feature_matrix,
    feature_names,
)


def _segments():
    return [
        {
            "start": 0.0,
            "end": 12.0,
            "label": "intro",
            "songformer_label": "intro",
            "structure_label_candidate": "intro",
            "structure_label_probabilities": {"intro": 0.8, "verse": 0.2},
        },
        {
            "start": 12.0,
            "end": 36.0,
            "label": "chorus",
            "songformer_label": "chorus",
            "structure_label_candidate": "chorus",
            "structure_label_probabilities": {"verse": 0.45, "chorus": 0.55},
        },
    ]


def _force_verse_model():
    feature_count = len(feature_names())
    intercept = np.zeros(len(STRUCTURE_LABELS))
    intercept[STRUCTURE_LABELS.index("verse")] = 10.0
    return {
        "schema_version": RELABELER_SCHEMA_VERSION,
        "model_version": "test-force-verse",
        "feature_names": feature_names(),
        "labels": list(STRUCTURE_LABELS),
        "feature_mean": [0.0] * feature_count,
        "feature_scale": [1.0] * feature_count,
        "coefficients": np.zeros((len(STRUCTURE_LABELS), feature_count)).tolist(),
        "intercept": intercept.tolist(),
        "override_threshold": 0.8,
    }


def test_feature_matrix_contains_context_without_changing_boundaries() -> None:
    segments = _segments()
    matrix = build_track_feature_matrix(segments)

    assert matrix.shape == (2, len(feature_names()))
    assert np.all(np.isfinite(matrix))
    assert segments[0]["start"] == 0.0
    assert segments[1]["end"] == 36.0


def test_active_relabeler_changes_only_labels_and_preserves_songformer_evidence() -> None:
    segments, metadata = apply_section_relabeler(
        _segments(), model=_force_verse_model(), shadow_mode=False
    )

    assert [(item["start"], item["end"]) for item in segments] == [
        (0.0, 12.0),
        (12.0, 36.0),
    ]
    assert [item["songformer_label"] for item in segments] == ["intro", "chorus"]
    assert [item["structure_label"] for item in segments] == ["verse", "verse"]
    assert metadata["changed_count"] == 2


def test_shadow_mode_records_proposal_but_keeps_product_label() -> None:
    segments, metadata = apply_section_relabeler(
        _segments(), model=_force_verse_model(), shadow_mode=True
    )

    assert segments[0]["relabeler_label_candidate"] == "verse"
    assert segments[0]["structure_label"] == "intro"
    assert segments[0]["label"] == "intro"
    assert segments[0]["label_change_proposed"] is True
    assert segments[0]["label_changed"] is False
    assert metadata["status"] == "shadow"


def test_missing_model_fails_closed() -> None:
    original = _segments()
    segments, metadata = apply_section_relabeler(original, model=None, enabled=False)

    assert segments == original
    assert metadata["status"] == "disabled"


def test_songformer_silence_is_a_source_feature_but_breakdown_is_the_target() -> None:
    source = {
        "start": 0.0,
        "end": 16.0,
        "songformer_label": "silence",
        "structure_label_candidate": "silence",
        "structure_label_probabilities": {
            label: 1.0 if label == "silence" else 0.0
            for label in SOURCE_STRUCTURE_LABELS
        },
    }
    model = _force_verse_model()
    model["override_threshold"] = 1.0

    segments, _ = apply_section_relabeler(
        [source], model=model, shadow_mode=False
    )

    assert "prob_silence" in feature_names()
    assert "prob_breakdown" not in feature_names()
    assert "breakdown" in STRUCTURE_LABELS
    assert "silence" not in STRUCTURE_LABELS
    assert segments[0]["structure_label"] == "silence"
    assert segments[0]["label_change_proposed"] is True
