from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError

import pytest
from pydantic import ValidationError

from app.modules.bar_annotations.schemas import AnnotationRecord
from app.modules.bar_annotations.store import (
    AnnotationStore,
    RevisionConflict,
    TimelineConflict,
)


def _record(annotator_id: str = "user:11") -> AnnotationRecord:
    return AnnotationRecord(
        annotation_id="ann-track-1-section-0-2",
        dataset_version="bar-understanding-1.0.0",
        track_id="track-1",
        task_id="structure.section_label",
        granularity="section",
        start_sec=0.0,
        end_sec=4.0,
        start_bar_index=0,
        end_bar_index=2,
        value="intro",
        annotator_id=annotator_id,
        annotation_status="annotated",
        annotator_confidence=0.9,
        candidate_source="analysis:phrase_map:v1",
        created_at="2026-08-30T09:00:00Z",
    )


def test_store_round_trip_and_revision_is_scoped_by_user(tmp_path) -> None:
    store = AnnotationStore(tmp_path)

    alice = store.save(
        "bar-understanding-1.0.0",
        user_id=11,
        track_id="track-1",
        expected_revision=0,
        timeline_fingerprint="timeline-a",
        annotations=[_record("user:11")],
        annotator_id="user:11",
    )
    bob = store.save(
        "bar-understanding-1.0.0",
        user_id=12,
        track_id="track-1",
        expected_revision=0,
        timeline_fingerprint="timeline-a",
        annotations=[_record("user:12")],
        annotator_id="user:12",
    )

    assert alice.revision == bob.revision == 1
    assert store.load("bar-understanding-1.0.0", 11, "track-1").annotator_id == "user:11"
    assert store.load("bar-understanding-1.0.0", 12, "track-1").annotator_id == "user:12"
    assert store.path_for("bar-understanding-1.0.0", 11, "track-1") != store.path_for(
        "bar-understanding-1.0.0", 12, "track-1"
    )
    raw = json.loads(
        store.path_for("bar-understanding-1.0.0", 11, "track-1").read_text()
    )
    assert raw["schema_name"] == "harbeat.annotation_set"
    assert raw["annotator_id"] == "user:11"


def test_store_rejects_stale_revision(tmp_path) -> None:
    store = AnnotationStore(tmp_path)
    store.save("bar-understanding-1.0.0", 11, "track-1", 0, "timeline-a", [], "user:11")

    with pytest.raises(RevisionConflict):
        store.save("bar-understanding-1.0.0", 11, "track-1", 0, "timeline-a", [], "user:11")


def test_store_rejects_timeline_change_in_same_dataset(tmp_path) -> None:
    store = AnnotationStore(tmp_path)
    store.save("bar-understanding-1.0.0", 11, "track-1", 0, "timeline-a", [], "user:11")

    with pytest.raises(TimelineConflict):
        store.save("bar-understanding-1.0.0", 11, "track-1", 1, "timeline-b", [], "user:11")


def test_store_rejects_unsafe_ids_and_invalid_user(tmp_path) -> None:
    store = AnnotationStore(tmp_path)

    with pytest.raises(ValueError):
        store.path_for("../escape", 11, "track-1")
    with pytest.raises(ValueError):
        store.path_for("bar-understanding-1.0.0", 11, "track/1")
    with pytest.raises(ValueError):
        store.path_for("bar-understanding-1.0.0", 0, "track-1")


def test_annotation_record_rejects_non_half_open_range() -> None:
    with pytest.raises(ValidationError):
        AnnotationRecord.model_validate({**_record().model_dump(), "end_bar_index": 0})


def test_store_allows_only_one_of_two_concurrent_saves_for_same_user(tmp_path) -> None:
    barrier = Barrier(2)

    class RacingStore(AnnotationStore):
        def load(self, dataset_version: str, user_id: int, track_id: str):
            loaded = super().load(dataset_version, user_id, track_id)
            if loaded.revision == 0:
                try:
                    barrier.wait(timeout=0.2)
                except BrokenBarrierError:
                    pass
            return loaded

    stores = [RacingStore(tmp_path), RacingStore(tmp_path)]

    def save(store: AnnotationStore):
        try:
            return store.save(
                "bar-understanding-1.0.0", 11, "track-1", 0, "timeline-a", [], "user:11"
            )
        except RevisionConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(save, stores))

    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, RevisionConflict) for outcome in outcomes) == 1
    assert AnnotationStore(tmp_path).load("bar-understanding-1.0.0", 11, "track-1").revision == 1


def test_store_rejects_annotator_identity_mismatch(tmp_path) -> None:
    store = AnnotationStore(tmp_path)
    with pytest.raises(ValueError, match="annotator"):
        store.save(
            "bar-understanding-1.0.0",
            11,
            "track-1",
            0,
            "timeline-a",
            [_record("user:12")],
            "user:11",
        )
