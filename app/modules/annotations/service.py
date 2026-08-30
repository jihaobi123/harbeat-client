"""Application rules for the assisted Bar annotation workspace."""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from app.modules.annotations.candidates import ELEMENTS, build_candidate_bars
from app.modules.annotations.public_datasets import SECTION_LABELS
from app.modules.annotations.schemas import (
    AnnotationRecord,
    AnnotationWorkspace,
    SaveAnnotationWorkspaceRequest,
)
from app.modules.annotations.store import AnnotationStore, TimelineConflict
from app.modules.library.bar_feature_adapter import CanonicalTimeline, build_canonical_timeline


ELEMENT_STATES = {"absent", "background", "foreground", "entering", "ending", "unknown"}
TIME_TOLERANCE_SEC = 1e-3


class AnnotationValidationError(ValueError):
    """A submitted annotation does not match the frozen task or Bar timeline."""


def timeline_fingerprint(timeline: CanonicalTimeline) -> str:
    """Fingerprint only the facts that control Bar-aligned annotation ranges."""
    payload = {
        "duration_sec": timeline.duration_sec,
        "beat_times_sec": timeline.beat_times_sec,
        "downbeat_times_sec": timeline.downbeat_times_sec,
        "numerator": timeline.numerator,
        "denominator": timeline.denominator,
        "intervals": [
            {
                "start_sec": interval.start_sec,
                "end_sec": interval.end_sec,
                "beat_start_index": interval.beat_start_index,
            }
            for interval in timeline.intervals
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def _workspace(
    song: Any,
    dataset_version: str,
    store: AnnotationStore,
) -> AnnotationWorkspace:
    timeline = build_canonical_timeline(song)
    fingerprint = timeline_fingerprint(timeline)
    stored = store.load(dataset_version, str(song.id))
    if stored.timeline_fingerprint and stored.timeline_fingerprint != fingerprint:
        raise TimelineConflict("timeline changed; create a new Dataset Version before continuing")
    return AnnotationWorkspace(
        dataset_version=dataset_version,
        track_id=str(song.id),
        title=str(getattr(song, "title", "")),
        artist=str(getattr(song, "artist", "")),
        duration_sec=timeline.duration_sec,
        timeline_fingerprint=fingerprint,
        timeline_warnings=list(timeline.warnings),
        revision=stored.revision,
        annotations=stored.annotations,
        bars=build_candidate_bars(song),
        updated_at=stored.updated_at,
    )


def build_annotation_workspace(
    song: Any,
    dataset_version: str,
    store: AnnotationStore,
) -> AnnotationWorkspace:
    return _workspace(song, dataset_version, store)


def _validate_task(record: AnnotationRecord) -> None:
    if record.task_id == "structure.section_label":
        if record.granularity != "section" or record.value not in SECTION_LABELS:
            raise AnnotationValidationError(
                f"{record.annotation_id}: invalid Section task granularity or value"
            )
        return

    prefix = "elements."
    suffix = ".state"
    if record.task_id.startswith(prefix) and record.task_id.endswith(suffix):
        element = record.task_id[len(prefix) : -len(suffix)]
        if (
            element not in ELEMENTS
            or record.granularity != "bar"
            or record.value not in ELEMENT_STATES
        ):
            raise AnnotationValidationError(
                f"{record.annotation_id}: invalid element task granularity or value"
            )
        return
    raise AnnotationValidationError(f"{record.annotation_id}: unsupported task_id {record.task_id}")


def _validate_record(
    record: AnnotationRecord,
    song: Any,
    dataset_version: str,
    timeline: CanonicalTimeline,
) -> None:
    if record.dataset_version != dataset_version:
        raise AnnotationValidationError(
            f"{record.annotation_id}: dataset_version does not match the request"
        )
    if record.track_id != str(song.id):
        raise AnnotationValidationError(f"{record.annotation_id}: track_id does not match the song")
    _validate_task(record)

    start_index = record.start_bar_index
    end_index = record.end_bar_index
    if start_index is None or end_index is None:
        raise AnnotationValidationError(f"{record.annotation_id}: Bar range is required")
    if start_index >= len(timeline.intervals) or end_index > len(timeline.intervals):
        raise AnnotationValidationError(f"{record.annotation_id}: Bar range is outside the timeline")
    expected_start = timeline.intervals[start_index].start_sec
    expected_end = timeline.intervals[end_index - 1].end_sec
    if record.start_sec is None or record.end_sec is None:
        raise AnnotationValidationError(f"{record.annotation_id}: time range is required")
    if (
        abs(record.start_sec - expected_start) > TIME_TOLERANCE_SEC
        or abs(record.end_sec - expected_end) > TIME_TOLERANCE_SEC
    ):
        raise AnnotationValidationError(
            f"{record.annotation_id}: time range does not match the canonical Bar range"
        )


def save_annotation_workspace(
    song: Any,
    request: SaveAnnotationWorkspaceRequest,
    store: AnnotationStore,
) -> AnnotationWorkspace:
    timeline = build_canonical_timeline(song)
    seen: set[str] = set()
    for record in request.annotations:
        if record.annotation_id in seen:
            raise AnnotationValidationError(f"duplicate annotation_id: {record.annotation_id}")
        seen.add(record.annotation_id)
        _validate_record(record, song, request.dataset_version, timeline)

    store.save(
        request.dataset_version,
        str(song.id),
        request.revision,
        timeline_fingerprint(timeline),
        request.annotations,
    )
    return _workspace(song, request.dataset_version, store)
