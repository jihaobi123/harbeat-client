import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

import pytest

from app.modules.annotations import store as store_module
from app.modules.annotations.schemas import PresenceAnnotationBundle
from app.modules.annotations.store import (
    AnnotationStore,
    AnnotationStoreError,
    InvalidTrackId,
    RevisionConflict,
)


def _candidate_bundle() -> PresenceAnnotationBundle:
    now = datetime.now(timezone.utc)
    bar = {
        "index": 0,
        "start_sec": 0.0,
        "end_sec": 2.0,
        "beat_start_index": 0,
        "beat_count": 4,
        "is_partial": False,
    }
    element = {
        "availability": "available",
        "requires_review": False,
        "confidence_cap": 1.0,
        "bar_probabilities": [0.9],
        "bar_features": [{"rms_dbfs": -12.0}],
        "candidate_ranges": [
            {"start_bar_index": 0, "end_bar_index": 1, "confidence": 0.9}
        ],
        "warnings": [],
    }
    melody = {
        **element,
        "requires_review": True,
        "confidence_cap": 0.65,
        "bar_probabilities": [0.6],
        "candidate_ranges": [
            {"start_bar_index": 0, "end_bar_index": 1, "confidence": 0.6}
        ],
    }
    return PresenceAnnotationBundle.model_validate(
        {
            "schema_name": "harbeat.presence_annotation_bundle",
            "schema_version": "1.0.0",
            "dataset_version": "bar-presence-pilot-1.0.0",
            "track_id": "track-1",
            "user_id": 7,
            "timeline": {
                "source": "downbeats",
                "meter_numerator": 4,
                "confidence": 0.95,
                "version": "bar_timeline@0.1.0",
                "bars": [bar],
            },
            "candidate_source": "method:bar_presence_candidate@0.1.0",
            "threshold_version": "bar_presence_thresholds@0.1.0",
            "revision": 1,
            "candidates": {
                "sample_rate": 44100,
                "elements": {
                    "vocal": element,
                    "drums": element,
                    "bass": element,
                    "melody": melody,
                },
            },
            "revisions": [],
            "created_at": now,
            "updated_at": now,
        }
    )


def _review_elements():
    reviewed = {
        "review_state": "reviewed",
        "ranges": [
            {"start_bar_index": 0, "end_bar_index": 1, "confidence": None}
        ],
    }
    return {
        "vocal": reviewed,
        "drums": reviewed,
        "bass": reviewed,
        "melody": {"review_state": "unknown", "ranges": []},
    }


def test_review_appends_revision_without_overwriting_candidates(tmp_path: Path):
    store = AnnotationStore(str(tmp_path))
    created = store.create_candidates(user_id=7, bundle=_candidate_bundle())
    original_vocal_ranges = created.candidates.elements["vocal"].candidate_ranges

    reviewed = store.save_review(
        user_id=7,
        track_id="track-1",
        expected_revision=created.revision,
        actor_id="user:7",
        elements=_review_elements(),
    )

    assert reviewed.revision == 2
    assert reviewed.candidates.elements["vocal"].candidate_ranges == original_vocal_ranges
    assert len(reviewed.revisions) == 1
    assert reviewed.revisions[0].elements["vocal"].review_state == "reviewed"
    assert store.read(user_id=7, track_id="track-1") == reviewed


def test_rejects_stale_review_revision(tmp_path: Path):
    store = AnnotationStore(str(tmp_path))
    store.create_candidates(user_id=7, bundle=_candidate_bundle())
    store.save_review(
        user_id=7,
        track_id="track-1",
        expected_revision=1,
        actor_id="user:7",
        elements=_review_elements(),
    )

    with pytest.raises(RevisionConflict):
        store.save_review(
            user_id=7,
            track_id="track-1",
            expected_revision=1,
            actor_id="user:7",
            elements=_review_elements(),
        )


def test_concurrent_reviews_cannot_overwrite_the_same_revision(tmp_path: Path):
    AnnotationStore(str(tmp_path)).create_candidates(
        user_id=7,
        bundle=_candidate_bundle(),
    )
    start = Barrier(2)

    def save_from_independent_worker(_worker: int) -> str:
        store = AnnotationStore(str(tmp_path))
        start.wait()
        try:
            store.save_review(
                user_id=7,
                track_id="track-1",
                expected_revision=1,
                actor_id="user:7",
                elements=_review_elements(),
            )
            return "saved"
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save_from_independent_worker, range(2)))

    assert sorted(outcomes) == ["conflict", "saved"]
    assert AnnotationStore(str(tmp_path)).read(
        user_id=7,
        track_id="track-1",
    ).revision == 2


def test_exports_only_latest_reviewed_ranges_as_annotation_jsonl(tmp_path: Path):
    store = AnnotationStore(str(tmp_path))
    store.create_candidates(user_id=7, bundle=_candidate_bundle())
    reviewed = store.save_review(
        user_id=7,
        track_id="track-1",
        expected_revision=1,
        actor_id="user:7",
        elements=_review_elements(),
    )

    records = [
        json.loads(line)
        for line in store.export_reviewed_jsonl(reviewed).splitlines()
    ]

    assert {record["task_id"] for record in records} == {
        "elements.vocal.presence",
        "elements.drums.presence",
        "elements.bass.presence",
    }
    assert all(record["annotation_status"] == "reviewed" for record in records)
    assert all(record["start_bar_index"] == 0 for record in records)
    assert all(record["end_bar_index"] == 1 for record in records)
    assert all(record["start_sec"] == 0.0 for record in records)
    assert all(record["end_sec"] == 2.0 for record in records)
    assert all(record["candidate_source"].startswith("method:") for record in records)


def test_single_song_export_validates_every_annotation_record(
    tmp_path: Path,
    monkeypatch,
):
    store = AnnotationStore(str(tmp_path))
    store.create_candidates(user_id=7, bundle=_candidate_bundle())
    reviewed = store.save_review(
        user_id=7,
        track_id="track-1",
        expected_revision=1,
        actor_id="user:7",
        elements=_review_elements(),
    )
    validated = []
    monkeypatch.setattr(
        store_module,
        "validate_annotation_record",
        lambda record: validated.append(record),
    )

    store.export_reviewed_jsonl(reviewed)

    assert len(validated) == 3


def test_rejects_unsafe_track_ids(tmp_path: Path):
    store = AnnotationStore(str(tmp_path))

    with pytest.raises(InvalidTrackId):
        store.read(user_id=7, track_id="../../escape")


def test_new_dataset_version_archives_review_history_before_replacement(tmp_path: Path):
    store = AnnotationStore(str(tmp_path))
    store.create_candidates(user_id=7, bundle=_candidate_bundle())
    store.save_review(
        user_id=7,
        track_id="track-1",
        expected_revision=1,
        actor_id="user:7",
        elements=_review_elements(),
    )
    replacement = _candidate_bundle().model_copy(deep=True)
    replacement.dataset_version = "bar-presence-pilot-1.0.1"

    created = store.create_candidates(user_id=7, bundle=replacement)
    archives = list((tmp_path / "7" / "track-1" / "versions").glob("*.json"))

    assert created.dataset_version == "bar-presence-pilot-1.0.1"
    assert created.revision == 1
    assert created.revisions == []
    assert len(archives) == 1
    archived = PresenceAnnotationBundle.model_validate_json(archives[0].read_text())
    assert archived.dataset_version == "bar-presence-pilot-1.0.0"
    assert archived.revision == 2


def test_unavailable_candidate_cannot_be_saved_as_reviewed_truth(tmp_path: Path):
    bundle = _candidate_bundle().model_copy(deep=True)
    bass = bundle.candidates.elements["bass"]
    bass.availability = "unavailable"
    bass.candidate_ranges = []
    bass.bar_probabilities = [0.0]
    bass.bar_features = []
    store = AnnotationStore(str(tmp_path))
    store.create_candidates(user_id=7, bundle=bundle)

    with pytest.raises(AnnotationStoreError, match="unavailable.*unknown"):
        store.save_review(
            user_id=7,
            track_id="track-1",
            expected_revision=1,
            actor_id="user:7",
            elements=_review_elements(),
        )
