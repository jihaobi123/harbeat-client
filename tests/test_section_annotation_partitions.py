import json

import pytest

from app.modules.library.section_annotation_partitions import (
    ensure_annotation_partition,
    partition_contract_issues,
    partition_summary,
)
from app.modules.library.section_relabel_dataset import DATASET_SCHEMA_VERSION
from app.modules.library.section_relabeler import SOURCE_STRUCTURE_LABELS
from scripts.section_label_workbench import AnnotationConflictError, HTML, Store


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
        label = SOURCE_STRUCTURE_LABELS[
            segment_index % len(SOURCE_STRUCTURE_LABELS)
        ]
        segments.append(
            {
                "segment_index": segment_index,
                "start": float(segment_index * 10),
                "end": float((segment_index + 1) * 10),
                "songformer_label": label,
                "structure_label_candidate": label,
                "structure_label_probabilities": {
                    candidate: 1.0 if candidate == label else 0.0
                    for candidate in SOURCE_STRUCTURE_LABELS
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


def test_workbench_keeps_full_song_playing_during_background_refresh() -> None:
    assert "从头播放整首" in HTML
    assert "function cancelSegmentStop()" in HTML
    assert "if(!background)renderContent()" in HTML
    assert "background&&visibleTrack?visibleTrack" in HTML
    assert "loadData(true,true)" in HTML
    assert "progressChanged" in HTML
    assert "},15000)" in HTML


def test_workbench_keeps_songformer_silence_as_the_human_target() -> None:
    assert "'silence'" in HTML
    assert "const targetLabel=l=>l" in HTML
    assert "silence:'静音'" in HTML
    assert "silence:'Breakdown'" not in HTML


def test_workbench_uses_song_drafts_without_automatic_segment_jump() -> None:
    assert "提交本首歌曲" in HTML
    assert "未修改段落将保存原标签" in HTML
    assert "fetch(appBase+'api/track-submit'" in HTML
    assert "async function fetchDataset()" in HTML
    assert "if(!background||!data)" in HTML
    assert "function setDraft(" in HTML
    assert "i+1<track.segments.length" not in HTML
    assert "scrollIntoView" not in HTML
    assert "结构太混乱，不参与" in HTML
    assert "fetch(appBase+'api/track-exclusion'" in HTML
    assert "const appBase=" in HTML
    assert 'src="${appBase}audio/' in HTML
    assert "恢复参与" in HTML


def test_song_submission_saves_defaults_and_edits_atomically(tmp_path) -> None:
    dataset_path = tmp_path / "annotations.json"
    dataset_path.write_text(json.dumps(_payload(tmp_path)), encoding="utf-8")
    store = Store(dataset_path, partition_count=2)
    partition = store.payload["annotation_partition"]
    first = partition["partitions"][0]
    access_key = first["access_key"]
    track_id = next(
        track_id
        for track_id, part_id in partition["assignments"].items()
        if part_id == first["id"]
    )
    track = store.track(track_id)
    assert track is not None

    submissions = []
    for index, segment in enumerate(track["segments"]):
        label = "chorus" if index == 0 else segment["structure_label_candidate"]
        submissions.append(
            {
                "segment_index": index,
                "expected_revision": 0,
                "annotation": {
                    "human_label": label,
                    "human_confidence": "high",
                    "boundary_ok": True,
                    "uncertain": False,
                    "notes": "",
                },
            }
        )

    result = store.submit_track_annotations(access_key, track_id, submissions)

    assert result["changed_count"] == len(track["segments"])
    assert track["segments"][0]["structure_label_candidate"] == "intro"
    assert track["segments"][0]["annotation"]["human_label"] == "chorus"
    assert all(
        segment["annotation"]["human_label"]
        == (
            "chorus"
            if index == 0
            else segment["structure_label_candidate"]
        )
        for index, segment in enumerate(track["segments"])
    )
    assert all(
        entry.get("action") == "submit_track"
        for entry in store.payload["annotation_review"]["audit_log"]
    )

    conflicting = json.loads(json.dumps(submissions))
    for item in conflicting:
        item["expected_revision"] = 1
    conflicting[0]["annotation"]["human_label"] = "bridge"
    conflicting[-1]["expected_revision"] = 0
    with pytest.raises(AnnotationConflictError):
        store.submit_track_annotations(access_key, track_id, conflicting)
    assert track["segments"][0]["annotation"]["human_label"] == "chorus"


def test_chaotic_track_can_be_excluded_and_restored_without_data_loss(tmp_path) -> None:
    dataset_path = tmp_path / "annotations.json"
    dataset_path.write_text(json.dumps(_payload(tmp_path)), encoding="utf-8")
    store = Store(dataset_path, partition_count=2)
    partition = store.payload["annotation_partition"]
    first = partition["partitions"][0]
    track_id = next(
        track_id
        for track_id, part_id in partition["assignments"].items()
        if part_id == first["id"]
    )
    track = store.track(track_id)
    assert track is not None
    original_segments = json.loads(json.dumps(track["segments"]))

    excluded = store.set_track_excluded(
        first["access_key"], track_id, excluded=True, expected_revision=0
    )
    summary = store.public_payload(first["access_key"])["annotation_progress"]

    assert excluded == {
        "ok": True,
        "changed": True,
        "revision": 1,
        "excluded": True,
    }
    assert track["segments"] == original_segments
    assert track["annotation_exclusion"]["reason"] == "structure_too_chaotic"
    assert summary["global"]["excluded_tracks"] == 1
    with pytest.raises(PermissionError, match="excluded tracks"):
        store.update_annotation(
            first["access_key"], track_id, 0, {"human_label": "verse"}, 0
        )

    restored = store.set_track_excluded(
        first["access_key"], track_id, excluded=False, expected_revision=1
    )

    assert restored["excluded"] is False
    assert track["segments"] == original_segments
    assert store.payload["annotation_review"]["audit_log"][-2]["action"] == (
        "exclude_track"
    )
    assert store.payload["annotation_review"]["audit_log"][-1]["action"] == (
        "restore_track"
    )


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
