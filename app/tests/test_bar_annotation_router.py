from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from app.modules.bar_annotations.pilot import PilotManifest  # noqa: E402
from app.modules.bar_annotations.router import (  # noqa: E402
    get_annotation_workspace_endpoint,
    get_pilot_tracks_endpoint,
    resolve_pilot_media_path,
    router as bar_annotation_router,
    save_annotation_workspace_endpoint,
)
from app.modules.bar_annotations.schemas import (  # noqa: E402
    AnnotationRecord,
    SaveAnnotationWorkspaceRequest,
)
from app.modules.bar_annotations.store import AnnotationStore  # noqa: E402


DATASET_VERSION = "bar-understanding-1.0.0"


def _song(track_id: str = "track-router-1", source_path: str = ""):
    return SimpleNamespace(
        id=track_id,
        user_id=2,
        title="Router Song",
        artist="Router Artist",
        duration=2.0,
        format="wav",
        source_path=source_path,
        stems={},
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
    def __init__(self, songs):
        self.songs = {song.id: song for song in songs}
        self._library_song_model = object

    def get(self, _model, track_id: str):
        return self.songs.get(track_id)


def _manifest(*track_ids: str) -> PilotManifest:
    return PilotManifest(DATASET_VERSION, tuple(track_ids))


def _request(revision: int = 0, value: str = "main") -> SaveAnnotationWorkspaceRequest:
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
        value=value,
        annotator_id="forged-client",
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


def test_bar_annotation_routes_are_registered_under_distinct_paths() -> None:
    paths = {route.path for route in bar_annotation_router.routes}
    assert "/pilot/tracks" in paths
    assert "/tracks/{track_id}/workspace" in paths
    assert "/tracks/{track_id}/audio" in paths
    assert "/tracks/{track_id}/stems/{stem_name}" in paths


def test_catalog_preserves_manifest_order_for_every_authenticated_user() -> None:
    db = FakeDB([_song("track-a"), _song("track-b")])
    response = get_pilot_tracks_endpoint(
        db=db,
        current_user=SimpleNamespace(id=99),
        manifest=_manifest("track-b", "track-a"),
    )
    assert [track.id for track in response.data] == ["track-b", "track-a"]


def test_non_pilot_song_returns_same_not_found_even_when_database_has_it(tmp_path) -> None:
    with pytest.raises(HTTPException) as error:
        get_annotation_workspace_endpoint(
            "private-track",
            DATASET_VERSION,
            FakeDB([_song("private-track")]),
            SimpleNamespace(id=11),
            AnnotationStore(tmp_path),
            _manifest("track-router-1"),
        )
    assert error.value.status_code == 404


def test_router_keeps_revisions_independent_for_two_users(tmp_path) -> None:
    store = AnnotationStore(tmp_path)
    db = FakeDB([_song()])
    manifest = _manifest("track-router-1")

    alice = save_annotation_workspace_endpoint(
        "track-router-1", _request(value="intro"), db, SimpleNamespace(id=11), store, manifest
    )
    bob = save_annotation_workspace_endpoint(
        "track-router-1", _request(value="main"), db, SimpleNamespace(id=12), store, manifest
    )

    assert alice.data.annotations[0].annotator_id == "user:11"
    assert bob.data.annotations[0].annotator_id == "user:12"
    with pytest.raises(HTTPException) as error:
        save_annotation_workspace_endpoint(
            "track-router-1", _request(), db, SimpleNamespace(id=11), store, manifest
        )
    assert error.value.status_code == 409


def test_media_resolver_allows_only_pilot_source_and_fixed_stems(tmp_path) -> None:
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    vocals = tmp_path / "vocals.wav"
    vocals.write_bytes(b"vocals")
    song = _song(source_path=str(source))
    song.stems = {"vocals": str(vocals), "secret": str(source)}
    manifest = _manifest("track-router-1")

    assert resolve_pilot_media_path(song, manifest, None) == str(source)
    assert resolve_pilot_media_path(song, manifest, "vocals") == str(vocals)
    with pytest.raises(HTTPException) as invalid:
        resolve_pilot_media_path(song, manifest, "secret")
    assert invalid.value.status_code == 404
    with pytest.raises(HTTPException) as private:
        resolve_pilot_media_path(_song("private", str(source)), manifest, None)
    assert private.value.status_code == 404
