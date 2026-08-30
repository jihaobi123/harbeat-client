from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.annotations.schemas import AnnotationRecord, SaveAnnotationWorkspaceRequest
from app.modules.annotations.service import (
    AnnotationValidationError,
    build_annotation_workspace,
    save_annotation_workspace,
    timeline_fingerprint,
)
from app.modules.annotations.store import AnnotationStore
from app.modules.library.bar_feature_adapter import build_canonical_timeline


DATASET_VERSION = "bar-understanding-1.0.0"


def _song(**overrides):
    values = {
        "id": "track-service-1",
        "title": "Pilot Song",
        "artist": "Pilot Artist",
        "duration": 4.0,
        "beat_points": [index * 0.5 for index in range(8)],
        "downbeats": [0.0, 2.0],
        "time_signature": {"numerator": 4, "denominator": 4, "confidence": 0.95},
        "bpm": 120.0,
        "beat_confidence": 0.94,
        "stem_activity_windows": [
            {"start": 0.0, "end": 2.0, "vocals": 0.0, "drums": 0.8, "bass": 0.4},
            {"start": 2.0, "end": 4.0, "vocals": 0.8, "drums": 0.75, "bass": 0.7},
        ],
        "energy_curve": [],
        "phrase_map": [
            {"start": 0.0, "end": 2.0, "label": "intro"},
            {"start": 2.0, "end": 4.0, "label": "drop"},
        ],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _annotation(**overrides) -> AnnotationRecord:
    values = {
        "annotation_id": "ann-track-service-1-section-0-1",
        "dataset_version": DATASET_VERSION,
        "track_id": "track-service-1",
        "task_id": "structure.section_label",
        "granularity": "section",
        "start_sec": 0.0,
        "end_sec": 2.0,
        "start_bar_index": 0,
        "end_bar_index": 1,
        "value": "intro",
        "annotator_id": "producer-1",
        "annotation_status": "annotated",
        "annotator_confidence": 0.9,
        "candidate_source": "analysis:phrase_map:v1",
        "created_at": "2026-08-30T09:00:00Z",
    }
    values.update(overrides)
    return AnnotationRecord(**values)


def test_workspace_combines_timeline_candidates_and_saved_annotations(tmp_path) -> None:
    song = _song()
    store = AnnotationStore(tmp_path)

    workspace = build_annotation_workspace(song, DATASET_VERSION, store)

    assert workspace.dataset_version == DATASET_VERSION
    assert workspace.track_id == song.id
    assert workspace.revision == 0
    assert workspace.annotations == []
    assert len(workspace.bars) == 2
    assert workspace.bars[0].section.value == "intro"
    assert workspace.bars[1].elements["vocal"].value == "entering"
    assert len(workspace.timeline_fingerprint) == 64


def test_save_validates_and_increments_workspace_revision(tmp_path) -> None:
    song = _song()
    store = AnnotationStore(tmp_path)
    request = SaveAnnotationWorkspaceRequest(
        dataset_version=DATASET_VERSION,
        revision=0,
        annotations=[_annotation()],
    )

    workspace = save_annotation_workspace(song, request, store)

    assert workspace.revision == 1
    assert workspace.annotations[0].value == "intro"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("end_sec", 3.0),
        ("value", "not-a-section"),
        ("task_id", "elements.other.state"),
        ("track_id", "another-track"),
    ],
)
def test_save_rejects_records_that_do_not_match_the_contract_or_timeline(
    tmp_path, field: str, value: object
) -> None:
    song = _song()
    request = SaveAnnotationWorkspaceRequest(
        dataset_version=DATASET_VERSION,
        revision=0,
        annotations=[_annotation(**{field: value})],
    )

    with pytest.raises(AnnotationValidationError):
        save_annotation_workspace(song, request, AnnotationStore(tmp_path))


def test_timeline_fingerprint_changes_when_bar_grid_changes() -> None:
    first = timeline_fingerprint(build_canonical_timeline(_song()))
    second = timeline_fingerprint(
        build_canonical_timeline(_song(beat_points=[index * 0.4 for index in range(10)]))
    )

    assert first != second

