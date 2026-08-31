#!/usr/bin/env python3
"""Combine reviewed Presence bundles into one Pilot JSONL and quality report."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.modules.annotations.schemas import ELEMENT_NAMES, PresenceAnnotationBundle
from app.modules.annotations.store import AnnotationStore


BUNDLE_NAME = "bar-presence-1.0.0.json"
ANNOTATION_RECORD_FIELDS = {
    "schema_name",
    "schema_version",
    "annotation_id",
    "dataset_version",
    "track_id",
    "task_id",
    "granularity",
    "start_sec",
    "end_sec",
    "start_bar_index",
    "end_bar_index",
    "value",
    "annotator_id",
    "annotation_status",
    "annotator_confidence",
    "candidate_source",
    "created_at",
}


def _range_tuple(item: Any) -> tuple[int, int]:
    return item.start_bar_index, item.end_bar_index


def _overlaps(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _validate_export_record(record: dict[str, Any]) -> None:
    """Enforce the Annotation Record V1 constraints used by Presence export."""
    if set(record) != ANNOTATION_RECORD_FIELDS:
        raise ValueError("export record does not match Annotation Record V1 fields")
    if record["schema_name"] != "harbeat.annotation_record":
        raise ValueError("invalid annotation schema_name")
    if record["schema_version"] != "1.0.0" or record["granularity"] != "bar":
        raise ValueError("invalid annotation schema version or granularity")
    if record["annotation_status"] not in {"reviewed", "adjudicated"}:
        raise ValueError("Pilot export only accepts reviewed or adjudicated records")
    if record["value"] is not True:
        raise ValueError("Presence records must have value=true")
    if record["start_bar_index"] < 0:
        raise ValueError("start_bar_index must be non-negative")
    if record["end_bar_index"] <= record["start_bar_index"]:
        raise ValueError("end_bar_index must be greater than start_bar_index")
    if record["end_sec"] <= record["start_sec"]:
        raise ValueError("end_sec must be greater than start_sec")


def _blank_element_stats() -> dict[str, Any]:
    return {
        "candidate_ranges": 0,
        "reviewed_ranges": 0,
        "accepted_candidate_ranges": 0,
        "candidate_acceptance_rate": None,
        "manually_added_ranges": 0,
        "deleted_candidate_ranges": 0,
        "boundary_adjustments": 0,
        "unavailable_tracks": 0,
    }


def _load_bundles(annotation_dir: Path) -> Iterable[PresenceAnnotationBundle]:
    for path in sorted(annotation_dir.glob(f"*/*/{BUNDLE_NAME}")):
        with path.open("r", encoding="utf-8") as handle:
            yield PresenceAnnotationBundle.model_validate(json.load(handle))


def export_presence_pilot(
    *,
    annotation_dir: Path,
    output_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    annotation_dir = Path(annotation_dir)
    output_path = Path(output_path)
    report_path = Path(report_path)
    element_stats = {element: _blank_element_stats() for element in ELEMENT_NAMES}
    records: list[dict[str, Any]] = []
    needs_review: list[dict[str, Any]] = []
    dataset_versions: set[str] = set()
    tracks_total = 0
    tracks_reviewed = 0
    bars_total = 0

    for bundle in _load_bundles(annotation_dir):
        tracks_total += 1
        bars_total += len(bundle.timeline.bars)
        dataset_versions.add(bundle.dataset_version)
        latest = bundle.revisions[-1] if bundle.revisions else None
        reasons: list[str] = []

        if latest is None:
            reasons.append("no_human_revision")
        else:
            tracks_reviewed += 1

        for element in ELEMENT_NAMES:
            candidate = bundle.candidates.elements[element]
            stats = element_stats[element]
            candidate_ranges = [_range_tuple(item) for item in candidate.candidate_ranges]
            stats["candidate_ranges"] += len(candidate_ranges)
            if candidate.availability != "available":
                stats["unavailable_tracks"] += 1
                reasons.append(f"{element}:{candidate.availability}")
            reasons.extend(f"{element}:{warning}" for warning in candidate.warnings)

            if latest is None:
                continue
            review = latest.elements[element]
            if review.review_state != "reviewed":
                reasons.append(f"{element}:{review.review_state}")
                continue
            final_ranges = [_range_tuple(item) for item in review.ranges]
            stats["reviewed_ranges"] += len(final_ranges)
            exact = set(candidate_ranges) & set(final_ranges)
            stats["accepted_candidate_ranges"] += len(exact)
            stats["boundary_adjustments"] += sum(
                item not in exact and any(_overlaps(item, final) for final in final_ranges)
                for item in candidate_ranges
            )
            stats["deleted_candidate_ranges"] += sum(
                not any(_overlaps(item, final) for final in final_ranges)
                for item in candidate_ranges
            )
            stats["manually_added_ranges"] += sum(
                not any(_overlaps(final, item) for item in candidate_ranges)
                for final in final_ranges
            )

        if reasons:
            needs_review.append({"track_id": bundle.track_id, "reasons": sorted(set(reasons))})

        if latest is not None:
            for line in AnnotationStore.export_reviewed_jsonl(bundle).splitlines():
                record = json.loads(line)
                _validate_export_record(record)
                records.append(record)

    for stats in element_stats.values():
        candidate_count = stats["candidate_ranges"]
        stats["candidate_acceptance_rate"] = (
            round(stats["accepted_candidate_ranges"] / candidate_count, 4)
            if candidate_count else None
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_text = "\n".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        for record in records
    )
    output_path.write_text(output_text + ("\n" if output_text else ""), encoding="utf-8")

    report = {
        "schema_name": "harbeat.presence_pilot_report",
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "annotation_dir": str(annotation_dir),
        "output_path": str(output_path),
        "dataset_versions": sorted(dataset_versions),
        "tracks_total": tracks_total,
        "tracks_reviewed": tracks_reviewed,
        "tracks_unreviewed": tracks_total - tracks_reviewed,
        "bars_total": bars_total,
        "records_exported": len(records),
        "elements": element_stats,
        "needs_review": needs_review,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export reviewed Bar-level Presence labels and Pilot metrics.",
    )
    parser.add_argument("--annotation-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    report = export_presence_pilot(
        annotation_dir=args.annotation_dir,
        output_path=args.output,
        report_path=args.report,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
