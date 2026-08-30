from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.modules.annotations.router import (  # noqa: E402
    get_annotation_workspace_endpoint,
    router as annotation_router,
    save_annotation_workspace_endpoint,
)
from app.modules.annotations.schemas import (  # noqa: E402
    AnnotationRecord,
    SaveAnnotationWorkspaceRequest,
)
from app.modules.annotations.store import AnnotationStore  # noqa: E402


DATASET_VERSION = "bar-understanding-1.0.0"


def _song(user_id: int = 7):
    return SimpleNamespace(
        id="track-router-1",
        user_id=user_id,
        title="Router Song",
        artist="Router Artist",
        duration=2.0,
        beat_points=[0.0, 0.5, 1.0, 1.5],
        downbeats=[0.0],
        time_signature={"numerator": 4, "denominator": 4, "confidence": 0.9},
        bpm=120.0,
        beat_confidence=0.9,
        stem_activity_windows=[],
        energy_curve=[],
        phrase_map=[],
    )


class FakeDB:
    def __init__(self, song):
        self.song = song

    def get(self, _model, track_id: str):
        return self.song if self.song and self.song.id == track_id else None


def _request(revision: int = 0) -> SaveAnnotationWorkspaceRequest:
    annotation = AnnotationRecord(
        annotation_id="ann-track-router-1-section-0-1",
        dataset_version=DATASET_VERSION,
        track_id="track-router-1",
        task_id="structure.section_label",
        granularity="section",
        start_sec=0.0,
        end_sec=2.0,
        start_bar_index=0,
        end_bar_index=1,
        value="main",
        annotator_id="producer-7",
        annotation_status="annotated",
        annotator_confidence=0.9,
        candidate_source=None,
        created_at="2026-08-30T09:00:00Z",
    )
    return SaveAnnotationWorkspaceRequest(
        dataset_version=DATASET_VERSION,
        revision=revision,
        annotations=[annotation],
    )


def test_annotation_routes_are_registered() -> None:
    paths = {route.path for route in annotation_router.routes}

    assert "/tracks/{track_id}/workspace" in paths


def test_get_workspace_enforces_song_ownership(tmp_path) -> None:
    with pytest.raises(HTTPException) as error:
        get_annotation_workspace_endpoint(
            "track-router-1",
            DATASET_VERSION,
            FakeDB(_song(user_id=8)),
            SimpleNamespace(id=7),
            AnnotationStore(tmp_path),
        )

    assert error.value.status_code == 403


def test_router_maps_stale_revision_to_conflict(tmp_path) -> None:
    store = AnnotationStore(tmp_path)
    db = FakeDB(_song())
    user = SimpleNamespace(id=7)
    first = save_annotation_workspace_endpoint("track-router-1", _request(), db, user, store)

    assert first.data.revision == 1
    assert first.data.annotations[0].annotator_id == "user:7"
    with pytest.raises(HTTPException) as error:
        save_annotation_workspace_endpoint("track-router-1", _request(), db, user, store)

    assert error.value.status_code == 409
