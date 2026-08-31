import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.modules.annotations.schemas import PresenceAnnotationBundle
from app.modules.annotations.store import (
    AnnotationStore,
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


def test_rejects_unsafe_track_ids(tmp_path: Path):
    store = AnnotationStore(str(tmp_path))

    with pytest.raises(InvalidTrackId):
        store.read(user_id=7, track_id="../../escape")
