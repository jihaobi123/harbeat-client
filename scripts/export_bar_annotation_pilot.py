#!/usr/bin/env python3
"""Export every valid public Pilot annotation while preserving annotator identity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.bar_annotations.pilot import PilotManifest
from app.modules.bar_annotations.schemas import StoredAnnotationSet


def _annotation_files(root: Path, dataset_version: str) -> Iterable[Path]:
    yield from sorted((root / dataset_version / "users").glob("*/*.json"))


def export_bar_annotation_pilot(
    *,
    root: str | Path,
    dataset_version: str,
    output_path: str | Path,
    report_path: str | Path,
    expected_track_ids: list[str],
) -> dict[str, Any]:
    root = Path(root)
    output_path = Path(output_path)
    report_path = Path(report_path)
    records: list[dict[str, Any]] = []
    parse_errors: list[dict[str, str]] = []
    annotator_tracks: dict[str, set[str]] = {}
    track_annotators: dict[str, set[str]] = {}

    for path in _annotation_files(root, dataset_version):
        try:
            saved = StoredAnnotationSet.model_validate_json(path.read_text(encoding="utf-8"))
            if saved.dataset_version != dataset_version:
                raise ValueError("dataset_version does not match export target")
            expected_user_dir = saved.annotator_id.removeprefix("user:")
            if path.parent.name != expected_user_dir:
                raise ValueError("annotator_id does not match user directory")
        except Exception as exc:
            parse_errors.append({"path": str(path), "error": str(exc)})
            continue

        annotator_tracks.setdefault(saved.annotator_id, set()).add(saved.track_id)
        track_annotators.setdefault(saved.track_id, set()).add(saved.annotator_id)
        for annotation in saved.annotations:
            record = annotation.model_dump(mode="json")
            record["annotation_set_revision"] = saved.revision
            records.append(record)

    records.sort(
        key=lambda row: (
            row["track_id"],
            row["annotator_id"],
            row["task_id"],
            row.get("start_bar_index") or 0,
            row["annotation_id"],
        )
    )
    expected_count = len(expected_track_ids)
    report: dict[str, Any] = {
        "schema_name": "harbeat.bar_annotation_pilot_report",
        "schema_version": "1.0.0",
        "dataset_version": dataset_version,
        "annotators_total": len(annotator_tracks),
        "tracks_total": len(track_annotators),
        "records_exported": len(records),
        "completion_by_annotator": {
            annotator: {
                "tracks_completed": len(tracks),
                "tracks_expected": expected_count,
            }
            for annotator, tracks in sorted(annotator_tracks.items())
        },
        "annotators_by_track": {
            track_id: sorted(annotators)
            for track_id, annotators in sorted(track_annotators.items())
        },
        "parse_errors": parse_errors,
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_text = "\n".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        for record in records
    )
    output_path.write_text(output_text + ("\n" if output_text else ""), encoding="utf-8")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Export public Bar annotation Pilot data")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    manifest = PilotManifest.load(args.manifest)
    report = export_bar_annotation_pilot(
        root=args.root,
        dataset_version=manifest.dataset_version,
        output_path=args.output,
        report_path=args.report,
        expected_track_ids=list(manifest.track_ids),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
