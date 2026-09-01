import pytest
import json
from pathlib import Path
from pydantic import ValidationError

from app.modules.edm_structure.schemas import (
    EdmSegmentCandidate,
    EdmStructureAnalysisDocument,
    ExpandedStructureHeadState,
)


def candidate_payload() -> dict:
    return {
        "canonical_section_id": "section-001",
        "start_bar_index": 0,
        "end_bar_index": 4,
        "start_sec": 0.0,
        "end_sec": 8.0,
        "canonical_boundary_source": "songformer_bar_snap_v1",
        "edmformer_label_candidate": "intro",
        "edmformer_label_probabilities": {
            "intro": 0.6,
            "buildup": 0.1,
            "drop": 0.1,
            "breakdown": 0.1,
            "outro": 0.05,
            "silence": 0.05,
        },
        "edmformer_label_max_probabilities": {
            "intro": 0.6,
            "buildup": 0.1,
            "drop": 0.1,
            "breakdown": 0.1,
            "outro": 0.05,
            "silence": 0.05,
        },
        "edmformer_boundary_candidates": [7.8],
        "validation_status": "unreviewed",
    }


def document_payload() -> dict:
    return {
        "schema_name": "harbeat.edm_structure_analysis",
        "schema_version": "0.1.0",
        "track_id": "track-1",
        "status": "ready",
        "duration_sec": 8.0,
        "audio_sha256": "a" * 64,
        "timeline_fingerprint": "b" * 64,
        "songformer_sidecar_sha256": "c" * 64,
        "muq_sha256": "d" * 64,
        "musicfm_sha256": "e" * 64,
        "musicfm_stats_sha256": "f" * 64,
        "edmformer_sha256": "1" * 64,
        "deployment_status": "shadow",
        "aggregation_version": "edmformer_songformer_block_aggregation_v1",
        "runtime_fingerprint": {"runner_version": "test"},
        "segments": [candidate_payload()],
        "expanded_structure_head": {},
        "warnings": [],
        "error": None,
    }


def test_ready_segment_keeps_all_six_probabilities():
    segment = EdmSegmentCandidate.model_validate(candidate_payload())
    assert set(segment.edmformer_label_probabilities) == {
        "intro", "buildup", "drop", "breakdown", "outro", "silence"
    }


def test_expanded_head_is_explicitly_not_installed():
    state = ExpandedStructureHeadState()
    assert state.enabled is False
    assert state.model_status == "not_installed"
    assert state.input_contract_version == "expanded_structure_input_v1"


def test_ready_document_requires_segments_and_shadow_status():
    payload = document_payload()
    payload["segments"] = []
    with pytest.raises(ValidationError):
        EdmStructureAnalysisDocument.model_validate(payload)
    payload = document_payload()
    payload["deployment_status"] = "production"
    with pytest.raises(ValidationError):
        EdmStructureAnalysisDocument.model_validate(payload)


def test_probabilities_must_be_complete_and_normalized():
    payload = candidate_payload()
    payload["edmformer_label_probabilities"].pop("silence")
    with pytest.raises(ValidationError):
        EdmSegmentCandidate.model_validate(payload)

    payload = candidate_payload()
    payload["edmformer_label_probabilities"]["intro"] = 0.9
    with pytest.raises(ValidationError):
        EdmSegmentCandidate.model_validate(payload)


def test_ready_fixture_matches_runtime_contract():
    root = Path(__file__).resolve().parents[2]
    payload = json.loads((root / "app/tests/fixtures/edm-structure-ready.json").read_text())
    assert EdmStructureAnalysisDocument.model_validate(payload).status == "ready"
