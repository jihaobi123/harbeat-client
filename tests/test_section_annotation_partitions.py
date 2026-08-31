import json

import pytest

from app.modules.library.section_annotation_partitions import (
    ensure_annotation_partition,
    partition_contract_issues,
    partition_summary,
)
from app.modules.library.section_relabel_dataset import DATASET_SCHEMA_VERSION
from app.modules.library.section_relabeler import STRUCTURE_LABELS
from scripts.section_label_workbench import Store


def _annotation() -> dict:
    return {
        "human_label": "",
        "human_confidence": "",
        "boundary_ok": True,
        "uncertain": False,
        "notes": "",
    }


def _track(tmp_path, index: int, split: str, style: str, segment_count: int) -> dict:
    audio = tmp_path / f"track-{index}.mp3"
    audio.write_bytes(b"audio")
    segments = []
    for segment_index in range(segment_count):
        label = STRUCTURE_LABELS[segment_index % len(STRUCTURE_LABELS)]
        segments.append(
            {
                "segment_index": segment_index,
                "start": float(segment_index * 10),
                "end": float((segment_index + 1) * 10),
                "songformer_label": label,
                "structure_label_candidate": label,
                "structure_label_probabilities": {
                    candidate: 1.0 if candidate == label else 0.0
                    for candidate in STRUCTURE_LABELS
                },
                "songformer_confidence": 1.0,
                "songformer_margin": 1.0,
                "annotation": _annotation(),
            }
        )
    return {
        "track_id": f"track-{index}",
        "split": split,
        "style": style,
        "display_name": f"Track {index}",
        "audio_path": str(audio),
        "duration": float(segment_count * 10),
        "songformer_status": "complete",
        "segments": segments,
    }


def _payload(tmp_path) -> dict:
    tracks = [
        _track(
            tmp_path,
            index,
            "development" if index < 6 else "test",
            "house" if index % 2 == 0 else "techno",
            2 + (index % 3),
        )
        for index in range(8)
    ]
    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "track_counts": {"development": 6, "test": 2, "total": 8, "pending": 0},
        "tracks": tracks,
    }


def test_two_partitions_are_stable_disjoint_and_cover_every_track(tmp_path) -> None:
    payload = _payload(tmp_path)

    assert ensure_annotation_partition(payload, partition_count=2) is True
    first = dict(payload["annotation_partition"]["assignments"])
    assert ensure_annotation_partition(payload, partition_count=2) is False

    assert payload["annotation_partition"]["assignments"] == first
    assert set(first) == {track["track_id"] for track in payload["tracks"]}
    assert set(first.values()) == {"part-1", "part-2"}
    assert not partition_contract_issues(payload)
    summary = partition_summary(payload)["partitions"]
    assert summary["part-1"]["tracks"] == 4
    assert summary["part-2"]["tracks"] == 4


def test_workbench_enforces_partition_writes_and_shares_live_summary(tmp_path) -> None:
    dataset_path = tmp_path / "annotations.json"
    dataset_path.write_text(json.dumps(_payload(tmp_path)), encoding="utf-8")
    store = Store(dataset_path, partition_count=2)
    partition = store.payload["annotation_partition"]
    keys = {item["id"]: item["access_key"] for item in partition["partitions"]}
    part_1 = store.public_payload(keys["part-1"])
    part_2 = store.public_payload(keys["part-2"])
    review = store.public_payload(partition["review_access_key"])

    ids_1 = {track["track_id"] for track in part_1["tracks"]}
    ids_2 = {track["track_id"] for track in part_2["tracks"]}
    assert ids_1.isdisjoint(ids_2)
    assert ids_1 | ids_2 == {track["track_id"] for track in review["tracks"]}
    assert review["access"] == {
        "scope": "all",
        "review_mode": True,
        "read_only": False,
    }

    track_id = part_1["tracks"][0]["track_id"]
    with pytest.raises(PermissionError, match="after its initial annotation"):
        store.update_annotation(
            partition["review_access_key"],
            track_id,
            0,
            {"human_label": "verse", "human_confidence": "high"},
            0,
        )
    store.update_annotation(
        keys["part-1"],
        track_id,
        0,
        {
            "human_label": "chorus",
            "human_confidence": "high",
            "boundary_ok": True,
            "uncertain": False,
        },
        0,
    )
    refreshed = store.public_payload(partition["review_access_key"])
    assert refreshed["annotation_progress"]["global"]["reviewed_segments"] == 1
    assert next(
        track for track in refreshed["tracks"] if track["track_id"] == track_id
    )["segments"][0]["annotation"]["human_label"] == "chorus"

    store.update_annotation(
        partition["review_access_key"],
        track_id,
        0,
        {
            "human_label": "verse",
            "human_confidence": "high",
            "boundary_ok": True,
            "uncertain": False,
        },
        1,
    )
    corrected = store.public_payload(partition["review_access_key"])
    corrected_segment = next(
        track for track in corrected["tracks"] if track["track_id"] == track_id
    )["segments"][0]
    assert corrected_segment["annotation"]["human_label"] == "verse"
    assert corrected_segment["annotation_revision"] == 2
    audit = store.payload["annotation_review"]["audit_log"]
    assert [entry["actor"] for entry in audit] == ["part-1", "review"]
    assert audit[-1]["before"]["human_label"] == "chorus"
    assert audit[-1]["after"]["human_label"] == "verse"

    with pytest.raises(PermissionError, match="belongs to"):
        store.update_annotation(
            keys["part-2"], track_id, 0, {"human_label": "verse"}, 2
        )
    with pytest.raises(RuntimeError, match="revision 1 to 2"):
        store.update_annotation(
            keys["part-1"], track_id, 0, {"human_label": "chorus"}, 1
        )
