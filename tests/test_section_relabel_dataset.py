import json

import numpy as np
import pytest

from app.modules.library.section_relabel_dataset import (
    DATASET_SCHEMA_VERSION,
    DatasetValidationError,
    validate_annotation,
    validate_dataset,
)
from app.modules.library.section_relabeler import (
    SOURCE_STRUCTURE_LABELS,
    feature_names,
)
from scripts.section_label_workbench import Store
from scripts.train_section_relabeler import collect_rows


def _segment(index: int, label: str, annotation: dict | None = None) -> dict:
    return {
        "segment_index": index,
        "start": float(index * 10),
        "end": float((index + 1) * 10),
        "songformer_label": label,
        "structure_label_candidate": label,
        "structure_label_probabilities": {
            candidate: 1.0 if candidate == label else 0.0
            for candidate in SOURCE_STRUCTURE_LABELS
        },
        "songformer_confidence": 1.0,
        "songformer_margin": 1.0,
        "annotation": annotation
        or {
            "human_label": "",
            "human_confidence": "",
            "boundary_ok": True,
            "uncertain": False,
            "notes": "",
        },
    }


def _dataset(audio_path: str) -> dict:
    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "track_counts": {"development": 1, "test": 0, "total": 1, "pending": 0},
        "tracks": [
            {
                "track_id": "track-1",
                "split": "development",
                "style": "test",
                "display_name": "Track 1",
                "audio_path": audio_path,
                "duration": 20.0,
                "songformer_status": "complete",
                "segments": [_segment(0, "chorus"), _segment(1, "verse")],
            }
        ],
    }


def test_pending_dataset_contract_is_valid_and_reports_progress(tmp_path) -> None:
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"test-audio")

    report = validate_dataset(_dataset(str(audio)), require_audio=True)

    assert report["tracks"] == {"development": 1, "test": 0}
    assert report["segments"] == {"development": 2, "test": 0}
    assert report["reviewed"]["development"] == 0
    assert report["feature_count"] == len(feature_names()) == 1100


def test_structurally_chaotic_track_is_excluded_from_completion_and_training(
    tmp_path,
) -> None:
    payload = _dataset(str(tmp_path / "track.mp3"))
    payload["tracks"][0]["annotation_exclusion"] = {
        "excluded": True,
        "reason": "structure_too_chaotic",
        "actor": "part-1",
        "updated_at": "2026-09-01T00:00:00+00:00",
        "revision": 1,
    }

    report = validate_dataset(
        payload, require_complete_splits=("development",)
    )
    x, y, _, _, _ = collect_rows(
        payload, "development", include_low_confidence=False
    )

    assert report["tracks"]["development"] == 1
    assert report["excluded_tracks"]["development"] == 1
    assert report["segments"]["development"] == 0
    assert report["reviewed"]["development"] == 0
    assert x.shape == (0, 1100)
    assert y.size == 0


def test_human_silence_annotation_keeps_the_original_label() -> None:
    annotation = validate_annotation(
        {
            "human_label": "silence",
            "human_confidence": "high",
            "boundary_ok": True,
            "uncertain": False,
            "notes": "legacy value",
        }
    )

    assert annotation["human_label"] == "silence"


def test_workbench_output_round_trips_directly_into_training_input(tmp_path) -> None:
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"test-audio")
    dataset_path = tmp_path / "annotations.json"
    dataset_path.write_text(
        json.dumps(_dataset(str(audio)), ensure_ascii=False), encoding="utf-8"
    )
    store = Store(dataset_path)
    access_key = store.payload["annotation_partition"]["partitions"][0]["access_key"]

    store.update_annotation(
        access_key,
        "track-1",
        0,
        {
            "human_label": "chorus",
            "human_confidence": "high",
            "boundary_ok": True,
            "uncertain": False,
        },
        0,
    )
    store.update_annotation(
        access_key,
        "track-1",
        1,
        {
            "human_label": "pre-chorus",
            "human_confidence": "medium",
            "boundary_ok": True,
            "uncertain": False,
        },
        0,
    )

    saved = json.loads(dataset_path.read_text(encoding="utf-8"))
    report = validate_dataset(
        saved, require_audio=True, require_complete_splits=("development",)
    )
    x, y, originals, groups, records = collect_rows(
        saved, "development", include_low_confidence=False
    )

    assert store.backup_path.is_file()
    assert report["reviewed"]["development"] == 2
    assert report["trainable"]["development"] == 2
    assert x.shape == (2, 1100)
    assert np.all(np.isfinite(x))
    assert y.tolist() == ["chorus", "pre-chorus"]
    assert originals.tolist() == ["chorus", "verse"]
    assert groups.tolist() == ["track-1", "track-1"]
    assert [record["segment_index"] for record in records] == [0, 1]


def test_reviewed_uncertain_and_boundary_errors_are_excluded_not_invalid(tmp_path) -> None:
    payload = _dataset(str(tmp_path / "missing.mp3"))
    payload["tracks"][0]["segments"][0]["annotation"].update(
        {"uncertain": True}
    )
    payload["tracks"][0]["segments"][1]["annotation"].update(
        {"boundary_ok": False}
    )

    report = validate_dataset(
        payload, require_complete_splits=("development",)
    )
    x, y, _, _, _ = collect_rows(
        payload, "development", include_low_confidence=False
    )

    assert report["reviewed"]["development"] == 2
    assert report["trainable"]["development"] == 0
    assert report["excluded"]["development"] == {
        "uncertain": 1,
        "boundary_error": 1,
        "low_confidence": 0,
    }
    assert x.shape == (0, 1100)
    assert y.size == 0


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (
            lambda payload: payload["tracks"][0]["segments"][0][
                "structure_label_probabilities"
            ].pop("verse"),
            "probability labels mismatch",
        ),
        (
            lambda payload: payload["tracks"][0]["segments"][0]["annotation"].update(
                {
                    "human_label": "chorus",
                    "human_confidence": "high",
                    "uncertain": True,
                }
            ),
            "cannot have both human_label and uncertain=true",
        ),
        (
            lambda payload: payload["tracks"][0]["segments"][0]["annotation"].update(
                {"uncertain": True, "boundary_ok": False}
            ),
            "cannot be both uncertain and a boundary error",
        ),
        (
            lambda payload: payload["tracks"].append(dict(payload["tracks"][0])),
            "duplicate track_id",
        ),
    ],
)
def test_contract_rejects_data_that_training_cannot_trust(
    tmp_path, mutation, expected
) -> None:
    payload = _dataset(str(tmp_path / "track.mp3"))
    mutation(payload)

    with pytest.raises(DatasetValidationError, match=expected):
        validate_dataset(payload)
