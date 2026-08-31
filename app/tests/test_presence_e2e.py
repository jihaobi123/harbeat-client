import json
from copy import copy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf

from app.modules.annotations.schemas import PresenceReviewRequest
from app.modules.annotations.service import PresenceAnnotationService
from app.modules.annotations.store import AnnotationStore
from scripts.export_presence_pilot import export_presence_pilot


def _synthetic_four_bar_song(tmp_path: Path):
    sample_rate = 1000
    duration = 8
    time = np.arange(sample_rate * duration) / sample_rate
    stems = {}
    for name, frequency in {
        "vocals": 220,
        "drums": 7,
        "bass": 60,
        "other": 330,
    }.items():
        audio = np.zeros(sample_rate * duration, dtype=np.float32)
        audio[sample_rate * 2:sample_rate * 6] = (
            0.35 * np.sin(2 * np.pi * frequency * time[:sample_rate * 4])
        )
        path = tmp_path / f"{name}.wav"
        sf.write(path, audio, sample_rate)
        stems[name] = str(path)
    return SimpleNamespace(
        id="pilot-track-1",
        user_id=7,
        duration=float(duration),
        downbeats=[0.0, 2.0, 4.0, 6.0],
        beat_points=[index * 0.5 for index in range(16)],
        time_signature={"numerator": 4, "denominator": 4, "confidence": 0.95},
        beat_confidence=0.95,
        beat_needs_review=False,
        stems=stems,
    )


def _accept_candidates(candidate):
    elements = {}
    for element, result in candidate.candidates.elements.items():
        if result.availability != "available":
            elements[element] = {"review_state": "unknown", "ranges": []}
            continue
        elements[element] = {
            "review_state": "reviewed",
            "ranges": [
                {
                    "start_bar_index": item.start_bar_index,
                    "end_bar_index": item.end_bar_index,
                    "confidence": None,
                }
                for item in result.candidate_ranges
            ],
        }
    return elements


def test_candidate_review_export_and_pilot_report_round_trip(tmp_path: Path):
    annotation_dir = tmp_path / "annotations"
    song = _synthetic_four_bar_song(tmp_path)
    service = PresenceAnnotationService(AnnotationStore(str(annotation_dir)))

    candidate = service.generate_for_song(
        song=song,
        requesting_user_id=song.user_id,
    )
    reviewed = service.review(
        song=song,
        requesting_user_id=song.user_id,
        actor_id="user:7",
        payload=PresenceReviewRequest(
            expected_revision=candidate.revision,
            elements=_accept_candidates(candidate),
        ),
    )
    incomplete_song = copy(song)
    incomplete_song.id = "pilot-track-incomplete"
    incomplete_candidate = service.generate_for_song(
        song=incomplete_song,
        requesting_user_id=incomplete_song.user_id,
    )
    incomplete_elements = _accept_candidates(incomplete_candidate)
    incomplete_elements["vocal"] = {"review_state": "unknown", "ranges": []}
    service.review(
        song=incomplete_song,
        requesting_user_id=incomplete_song.user_id,
        actor_id="user:7",
        payload=PresenceReviewRequest(
            expected_revision=incomplete_candidate.revision,
            elements=incomplete_elements,
        ),
    )
    single_records = [
        json.loads(line)
        for line in service.export(
            song=song,
            requesting_user_id=song.user_id,
        ).splitlines()
    ]

    output_path = tmp_path / "pilot.jsonl"
    report_path = tmp_path / "pilot-report.json"
    report = export_presence_pilot(
        annotation_dir=annotation_dir,
        output_path=output_path,
        report_path=report_path,
    )
    batch_records = [json.loads(line) for line in output_path.read_text().splitlines()]

    assert reviewed.revision == 2
    assert {record["task_id"] for record in single_records} >= {
        "elements.vocal.presence",
        "elements.drums.presence",
        "elements.bass.presence",
    }
    assert all(record["annotation_status"] == "reviewed" for record in single_records)
    assert batch_records == single_records
    assert report["tracks_total"] == 2
    assert report["tracks_reviewed"] == 1
    assert report["tracks_unreviewed"] == 1
    assert report["bars_total"] == 8
    assert report["records_exported"] == len(single_records)
    assert report["elements"]["vocal"]["candidate_acceptance_rate"] == 1.0
    assert report["needs_review"] == [
        {"track_id": "pilot-track-incomplete", "reasons": ["vocal:unknown"]}
    ]
    assert json.loads(report_path.read_text())["dataset_versions"] == [
        "bar-presence-pilot-1.0.0"
    ]
