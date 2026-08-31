"""Stable, mutually exclusive partitions for collaborative section annotation."""

from __future__ import annotations

import secrets
from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any


PARTITION_SCHEMA_VERSION = "harbeat_annotation_partition_v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def annotation_is_reviewed(annotation: Mapping[str, Any]) -> bool:
    return bool(
        annotation.get("human_label")
        or annotation.get("uncertain")
        or annotation.get("boundary_ok") is False
    )


def _balanced_assignments(
    tracks: list[Mapping[str, Any]], partition_count: int
) -> dict[str, str]:
    """Assign whole tracks while balancing each split/style and segment volume."""
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for track in tracks:
        groups[(str(track.get("split") or ""), str(track.get("style") or ""))].append(track)

    assignments: dict[str, str] = {}
    global_segments: Counter[int] = Counter()
    global_tracks: Counter[int] = Counter()
    for group_key in sorted(groups):
        group_segments: Counter[int] = Counter()
        group_tracks: Counter[int] = Counter()
        ordered = sorted(
            groups[group_key],
            key=lambda track: (
                -len(track.get("segments") or []),
                str(track.get("track_id") or ""),
            ),
        )
        for track in ordered:
            partition_index = min(
                range(1, partition_count + 1),
                key=lambda index: (
                    group_tracks[index],
                    global_tracks[index],
                    group_segments[index],
                    global_segments[index],
                    index,
                ),
            )
            track_id = str(track["track_id"])
            assignments[track_id] = f"part-{partition_index}"
            segment_count = len(track.get("segments") or [])
            group_segments[partition_index] += segment_count
            group_tracks[partition_index] += 1
            global_segments[partition_index] += segment_count
            global_tracks[partition_index] += 1
    return assignments


def ensure_annotation_partition(
    payload: dict[str, Any], *, partition_count: int = 2
) -> bool:
    """Create a partition contract once; return whether the payload changed."""
    if partition_count < 2:
        raise ValueError("partition_count must be at least 2")
    existing = payload.get("annotation_partition")
    if existing is not None:
        issues = partition_contract_issues(payload)
        if issues:
            raise ValueError("; ".join(issues))
        if existing.get("partition_count") != partition_count:
            raise ValueError(
                "dataset already has a different partition_count; repartitioning "
                "would invalidate shared links"
            )
        return False

    tracks = list(payload.get("tracks") or [])
    assignments = _balanced_assignments(tracks, partition_count)
    payload["annotation_partition"] = {
        "schema_version": PARTITION_SCHEMA_VERSION,
        "partition_count": partition_count,
        "strategy": "whole_track_balanced_by_split_style_and_segment_count",
        "created_at": _now(),
        "partitions": [
            {
                "id": f"part-{index}",
                "access_key": secrets.token_urlsafe(24),
            }
            for index in range(1, partition_count + 1)
        ],
        "review_access_key": secrets.token_urlsafe(24),
        "assignments": assignments,
    }
    return True


def partition_contract_issues(payload: Mapping[str, Any]) -> list[str]:
    raw = payload.get("annotation_partition")
    if raw is None:
        return []
    if not isinstance(raw, Mapping):
        return ["annotation_partition must be an object"]
    issues: list[str] = []
    if raw.get("schema_version") != PARTITION_SCHEMA_VERSION:
        issues.append(
            f"annotation_partition.schema_version must be {PARTITION_SCHEMA_VERSION}"
        )
    count = raw.get("partition_count")
    if not isinstance(count, int) or count < 2:
        issues.append("annotation_partition.partition_count must be an integer >= 2")
        count = 0
    partitions = raw.get("partitions")
    expected_ids = {f"part-{index}" for index in range(1, count + 1)}
    actual_ids: set[str] = set()
    access_keys: set[str] = set()
    if not isinstance(partitions, list) or len(partitions) != count:
        issues.append("annotation_partition.partitions does not match partition_count")
    else:
        for position, partition in enumerate(partitions):
            if not isinstance(partition, Mapping):
                issues.append(f"annotation_partition.partitions[{position}] must be an object")
                continue
            partition_id = str(partition.get("id") or "")
            access_key = str(partition.get("access_key") or "")
            actual_ids.add(partition_id)
            if len(access_key) < 20 or access_key in access_keys:
                issues.append(
                    f"annotation_partition.partitions[{position}].access_key is invalid"
                )
            access_keys.add(access_key)
    if actual_ids != expected_ids:
        issues.append("annotation_partition partition ids are incomplete")
    review_key = str(raw.get("review_access_key") or "")
    if len(review_key) < 20 or review_key in access_keys:
        issues.append("annotation_partition.review_access_key is invalid")

    track_ids = {
        str(track.get("track_id") or "")
        for track in payload.get("tracks") or []
        if isinstance(track, Mapping)
    }
    assignments = raw.get("assignments")
    if not isinstance(assignments, Mapping):
        issues.append("annotation_partition.assignments must be an object")
    else:
        assignment_ids = {str(track_id) for track_id in assignments}
        if assignment_ids != track_ids:
            missing = sorted(track_ids - assignment_ids)
            extra = sorted(assignment_ids - track_ids)
            issues.append(
                "annotation_partition assignments must cover every track exactly once; "
                f"missing={missing}, extra={extra}"
            )
        invalid_parts = sorted(
            {
                str(partition_id)
                for partition_id in assignments.values()
                if str(partition_id) not in expected_ids
            }
        )
        if invalid_parts:
            issues.append(
                f"annotation_partition assignments use invalid partitions: {invalid_parts}"
            )
    return issues


def resolve_access(payload: Mapping[str, Any], access_key: str) -> tuple[str, bool]:
    """Return (scope, read_only), rejecting unknown capability keys."""
    partition = payload.get("annotation_partition")
    if not isinstance(partition, Mapping):
        raise PermissionError("annotation dataset has not been partitioned")
    if secrets.compare_digest(str(partition.get("review_access_key") or ""), access_key):
        return "all", True
    for item in partition.get("partitions") or []:
        if isinstance(item, Mapping) and secrets.compare_digest(
            str(item.get("access_key") or ""), access_key
        ):
            return str(item["id"]), False
    raise PermissionError("invalid annotation access key")


def partition_summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    partition = payload.get("annotation_partition") or {}
    assignments = partition.get("assignments") or {}
    result: dict[str, Any] = {}
    global_tracks = global_segments = global_reviewed = global_done = 0
    for track in payload.get("tracks") or []:
        track_id = str(track.get("track_id") or "")
        partition_id = str(assignments.get(track_id) or "unassigned")
        segments = list(track.get("segments") or [])
        reviewed = sum(
            annotation_is_reviewed(segment.get("annotation") or {})
            for segment in segments
        )
        bucket = result.setdefault(
            partition_id,
            {"tracks": 0, "completed_tracks": 0, "segments": 0, "reviewed_segments": 0},
        )
        bucket["tracks"] += 1
        bucket["segments"] += len(segments)
        bucket["reviewed_segments"] += reviewed
        bucket["completed_tracks"] += int(bool(segments) and reviewed == len(segments))
        global_tracks += 1
        global_segments += len(segments)
        global_reviewed += reviewed
        global_done += int(bool(segments) and reviewed == len(segments))
    return {
        "partitions": result,
        "global": {
            "tracks": global_tracks,
            "completed_tracks": global_done,
            "segments": global_segments,
            "reviewed_segments": global_reviewed,
        },
    }
