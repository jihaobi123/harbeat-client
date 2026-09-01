import json
import sys

import numpy as np

from app.modules.library.section_relabel_dataset import DATASET_SCHEMA_VERSION
from app.modules.library.section_relabeler import (
    SOURCE_STRUCTURE_LABELS,
    STRUCTURE_LABELS,
    feature_names,
    load_relabeler_model,
)
from scripts import train_section_relabeler
from scripts.train_section_relabeler import cross_validate


def test_grouped_training_selects_a_safe_positive_gain_model() -> None:
    rows = []
    targets = []
    originals = []
    groups = []
    probability_offset = 0
    for track_index in range(20):
        for label_index, label in enumerate(STRUCTURE_LABELS):
            vector = np.zeros(len(feature_names()), dtype=np.float64)
            vector[probability_offset + label_index] = 1.0
            vector[8 + label_index] = 0.0
            rows.append(vector)
            targets.append(label)
            originals.append(
                STRUCTURE_LABELS[(label_index + 1) % len(STRUCTURE_LABELS)]
                if track_index % 2 == 0
                else label
            )
            groups.append(f"track-{track_index}")

    _, threshold, _, report = cross_validate(
        np.vstack(rows),
        np.asarray(targets),
        np.asarray(originals),
        np.asarray(groups),
        folds=5,
        minimum_precision=0.8,
    )

    assert threshold <= 1.0
    assert report["folds"] == 5
    assert report["gated_metrics"]["net_gain"] > 0
    assert report["gated_metrics"]["override_precision"] >= 0.8


def _annotation(label: str = "", *, uncertain: bool = False) -> dict:
    return {
        "human_label": label,
        "human_confidence": "high" if label else "",
        "boundary_ok": True,
        "uncertain": uncertain,
        "notes": "",
    }


def _segment(index: int, original: str, target: str, annotation: dict) -> dict:
    return {
        "segment_index": index,
        "start": float(index * 10),
        "end": float((index + 1) * 10),
        "songformer_label": original,
        "structure_label_candidate": original,
        "structure_label_probabilities": {
            label: 1.0 if label == target else 0.0
            for label in SOURCE_STRUCTURE_LABELS
        },
        "songformer_confidence": 1.0,
        "songformer_margin": 1.0,
        "annotation": annotation,
    }


def test_complete_workbench_contract_trains_exports_and_evaluates_once(
    tmp_path, monkeypatch, capsys
) -> None:
    tracks = []
    for track_index in range(20):
        segments = []
        for label_index, target in enumerate(STRUCTURE_LABELS):
            original = (
                STRUCTURE_LABELS[(label_index + 1) % len(STRUCTURE_LABELS)]
                if track_index % 2 == 0
                else target
            )
            segments.append(
                _segment(label_index, original, target, _annotation(target))
            )
        tracks.append(
            {
                "track_id": f"development-{track_index}",
                "split": "development",
                "style": "synthetic",
                "display_name": f"Development {track_index}",
                "audio_path": str(tmp_path / f"development-{track_index}.wav"),
                "duration": 80.0,
                "songformer_status": "complete",
                "segments": segments,
            }
        )

    tracks.append(
        {
            "track_id": "locked-test",
            "split": "test",
            "style": "synthetic",
            "display_name": "Locked test",
            "audio_path": str(tmp_path / "locked-test.wav"),
            "duration": 20.0,
            "songformer_status": "complete",
            "segments": [
                _segment(0, "verse", "chorus", _annotation("chorus")),
                _segment(1, "verse", "verse", _annotation(uncertain=True)),
            ],
        }
    )
    payload = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "track_counts": {
            "development": 20,
            "test": 1,
            "total": 21,
            "pending": 0,
        },
        "tracks": tracks,
    }
    dataset_path = tmp_path / "annotations.json"
    model_path = tmp_path / "model.json"
    report_path = tmp_path / "report.json"
    dataset_path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "train_section_relabeler.py",
            "--dataset",
            str(dataset_path),
            "--model-output",
            str(model_path),
            "--report-output",
            str(report_path),
        ],
    )

    assert train_section_relabeler.main() == 0

    exported_model = load_relabeler_model(model_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    terminal_result = json.loads(capsys.readouterr().out)
    assert exported_model is not None
    assert len(exported_model["feature_names"]) == 52
    assert report["dataset_validation"]["trainable"]["development"] == 160
    assert report["test"]["status"] == "evaluated_once"
    assert report["test"]["reviewed_segments"] == 2
    assert report["test"]["evaluated_segments"] == 1
    assert report["test"]["excluded_segments"] == 1
    assert terminal_result["test_status"] == "evaluated_once"
