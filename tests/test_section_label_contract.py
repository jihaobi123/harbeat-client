import math

import pytest

from app.modules.library.section_contract import (
    LABEL_CONTRACT_VERSION,
    canonical_structure_label,
    enrich_section_segment,
    normalize_structure_probabilities,
)


def test_songformer_inst_is_preserved_and_canonicalized() -> None:
    segment = enrich_section_segment(
        {
            "start": 16.0,
            "end": 32.0,
            "label": "inst",
            "label_probabilities": {
                "intro": 0.01,
                "verse": 0.02,
                "chorus": 0.03,
                "bridge": 0.04,
                "inst": 0.80,
                "outro": 0.05,
                "silence": 0.02,
                "pre-chorus": 0.03,
            },
        },
        source="songformer_functional_segment",
    )

    assert segment["songformer_label"] == "inst"
    assert segment["structure_label_candidate"] == "instrumental"
    assert list(segment["structure_label_probabilities"]) == [
        "intro",
        "verse",
        "chorus",
        "bridge",
        "instrumental",
        "outro",
        "silence",
        "pre-chorus",
    ]
    assert segment["structure_label_probabilities"]["instrumental"] == pytest.approx(0.8)
    assert segment["structure_label_confidence"] == pytest.approx(0.8)
    assert segment["structure_label_margin"] == pytest.approx(0.75)
    assert segment["mix_roles"] == ["instrumental_focus"]
    assert segment["mix_role_scores"] == {"instrumental_focus": 1.0}
    assert segment["label"] == "instrumental"
    assert segment["boundary_source"] == "songformer"
    assert segment["label_status"] == "candidate"
    assert segment["label_contract_version"] == LABEL_CONTRACT_VERSION


def test_pre_chorus_exposes_transition_and_buildup_candidates() -> None:
    segment = enrich_section_segment(
        {"start": 32.0, "end": 40.0, "label": "pre-chorus"},
        source="songformer",
    )

    assert segment["structure_label_candidate"] == "pre-chorus"
    assert segment["mix_roles"] == ["transition", "buildup"]
    assert segment["mix_role_scores"] == {"transition": 1.0, "buildup": 0.7}
    assert segment["label_evidence_status"] == "missing"


def test_candidate_confidence_is_not_replaced_by_another_classes_top_score() -> None:
    segment = enrich_section_segment(
        {
            "start": 8.0,
            "end": 16.0,
            "label": "chorus",
            "label_probabilities": {"verse": 0.6, "chorus": 0.3, "bridge": 0.1},
        },
        source="songformer",
    )

    assert segment["structure_label_confidence"] == pytest.approx(0.3)
    assert segment["structure_label_margin"] == pytest.approx(0.3)


def test_fallback_contract_marks_missing_evidence_without_songformer_label() -> None:
    segment = enrich_section_segment(
        {"start": 0.0, "end": 8.0, "label": "intro"},
        source="all_in_one_functional_segment",
    )

    assert segment["songformer_label"] is None
    assert segment["structure_label_candidate"] == "intro"
    assert segment["structure_label_probabilities"] == {}
    assert segment["structure_label_confidence"] is None
    assert segment["structure_label_margin"] is None
    assert segment["label_evidence_status"] == "missing"
    assert segment["boundary_source"] == "all_in_one"


def test_probability_normalization_merges_aliases_and_rejects_invalid_values() -> None:
    probabilities = normalize_structure_probabilities(
        {
            "INST": 3.0,
            "instrumental": 1.0,
            "chorus": 2.0,
            "bad_nan": math.nan,
            "bad_negative": -1.0,
            "bad_text": "not-a-number",
        }
    )

    assert probabilities == pytest.approx({"instrumental": 2 / 3, "chorus": 1 / 3})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" inst ", "instrumental"),
        ("PRE-CHORUS", "pre-chorus"),
        (None, "unknown"),
    ],
)
def test_canonical_structure_label(raw: object, expected: str) -> None:
    assert canonical_structure_label(raw) == expected
