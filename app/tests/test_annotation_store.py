from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, BrokenBarrierError

import pytest
from pydantic import ValidationError

from app.modules.annotations.schemas import AnnotationRecord
from app.modules.annotations.store import (
    AnnotationStore,
    RevisionConflict,
    TimelineConflict,
)


def _record() -> AnnotationRecord:
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
        annotator_id="producer-1",
        annotation_status="annotated",
        annotator_confidence=0.9,
        candidate_source="analysis:phrase_map:v1",
        created_at="2026-08-30T09:00:00Z",
    )


def test_store_round_trip_and_revision(tmp_path) -> None:
    store = AnnotationStore(tmp_path)

    saved = store.save(
        "bar-understanding-1.0.0",
        "track-1",
        expected_revision=0,
        timeline_fingerprint="timeline-a",
        annotations=[_record()],
    )
    loaded = store.load("bar-understanding-1.0.0", "track-1")

    assert saved.revision == 1
    assert loaded.revision == 1
    assert loaded.timeline_fingerprint == "timeline-a"
    assert loaded.annotations[0].value == "intro"
    raw = json.loads(store.path_for("bar-understanding-1.0.0", "track-1").read_text())
    assert raw["schema_name"] == "harbeat.annotation_set"


def test_store_rejects_stale_revision(tmp_path) -> None:
    store = AnnotationStore(tmp_path)
    store.save("bar-understanding-1.0.0", "track-1", 0, "timeline-a", [])

    with pytest.raises(RevisionConflict):
        store.save("bar-understanding-1.0.0", "track-1", 0, "timeline-a", [])


def test_store_rejects_timeline_change_in_same_dataset(tmp_path) -> None:
    store = AnnotationStore(tmp_path)
    store.save("bar-understanding-1.0.0", "track-1", 0, "timeline-a", [])

    with pytest.raises(TimelineConflict):
        store.save("bar-understanding-1.0.0", "track-1", 1, "timeline-b", [])


def test_store_rejects_unsafe_dataset_or_track_ids(tmp_path) -> None:
    store = AnnotationStore(tmp_path)

    with pytest.raises(ValueError):
        store.path_for("../escape", "track-1")
    with pytest.raises(ValueError):
        store.path_for("bar-understanding-1.0.0", "track/1")


def test_annotation_record_rejects_non_half_open_range() -> None:
    with pytest.raises(ValidationError):
        _record().model_copy(update={"end_bar_index": 0}, deep=True).__class__.model_validate(
            {**_record().model_dump(), "end_bar_index": 0}
        )


def test_store_allows_only_one_of_two_concurrent_saves(tmp_path) -> None:
    barrier = Barrier(2)

    class RacingStore(AnnotationStore):
        def load(self, dataset_version: str, track_id: str):
            loaded = super().load(dataset_version, track_id)
            if loaded.revision == 0:
                try:
                    barrier.wait(timeout=0.2)
                except BrokenBarrierError:
                    pass
            return loaded

    stores = [RacingStore(tmp_path), RacingStore(tmp_path)]

    def save(store: AnnotationStore):
        try:
            return store.save("bar-understanding-1.0.0", "track-1", 0, "timeline-a", [])
        except RevisionConflict as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(save, stores))

    assert sum(not isinstance(outcome, Exception) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, RevisionConflict) for outcome in outcomes) == 1
    assert AnnotationStore(tmp_path).load("bar-understanding-1.0.0", "track-1").revision == 1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("annotation_id", "bad id"),
        ("annotator_id", "producer 1"),
        ("created_at", "2026-08-30Z"),
    ],
)
def test_annotation_record_mirrors_json_schema_identity_and_timestamp_rules(
    field: str, value: str
) -> None:
    with pytest.raises(ValidationError):
        AnnotationRecord.model_validate({**_record().model_dump(), field: value})
