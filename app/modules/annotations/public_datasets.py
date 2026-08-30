"""Deterministic mappings from public annotation taxonomies to HarBeat V1."""
from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
import re
from typing import Any

from app.modules.annotations.schemas import AnnotationRecord


SECTION_LABELS = {"intro", "main", "build", "breakdown", "outro", "unknown"}


def _normalize_label(label: str) -> str:
    value = re.sub(r"[\s_]+", "-", str(label or "").strip().lower())
    value = re.sub(r"-?\d+$", "", value)
    return value.strip("-")


def map_raveform_section_label(label: str) -> str:
    """Map Raveform's EDM functions to the frozen coarse HarBeat taxonomy."""
    normalized = _normalize_label(label)
    if normalized in {"intro", "ambient-intro"}:
        return "intro"
    if normalized in {"buildup", "build-up", "build"}:
        return "build"
    if normalized in {"breakdown", "ambient-breakdown"}:
        return "breakdown"
    if normalized in {"outro", "ambient-outro"}:
        return "outro"
    if normalized in {
        "drop",
        "cooldown",
        "bridge",
        "verse",
        "chorus",
        "instrumental",
        "main",
    }:
        return "main"
    return "unknown"


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) and parsed >= 0 else None


def _first_number(source: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in source and (value := _number(source[key])) is not None:
            return value
    return None


def _source_track(source: dict[str, Any]) -> dict[str, Any]:
    track = source.get("track")
    return track if isinstance(track, dict) else source


def _safe_source_id(value: Any) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._:-]+", "-", str(value or "").strip()).strip("-")
    if not normalized or not re.match(r"^[A-Za-z0-9]", normalized):
        raise ValueError("Raveform track id is required")
    return normalized


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def convert_raveform_track(
    source: dict[str, Any],
    dataset_version: str,
    *,
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    """Convert one Raveform track to untrusted Section candidate records.

    Source files in circulation use several names for the same timing fields,
    so the import boundary accepts the known variants and emits one strict
    HarBeat contract. It never upgrades public labels to human truth.
    """
    if not isinstance(source, dict):
        raise ValueError("Raveform track must be a JSON object")
    track = _source_track(source)
    source_track_id = track.get("id", track.get("track_id", source.get("track_id")))
    track_id = f"raveform:{_safe_source_id(source_track_id)}"
    duration = _first_number(track, "duration_sec", "duration")
    if duration is None:
        duration = _first_number(source, "duration_sec", "duration")

    raw_sections = source.get("sections", track.get("sections"))
    if not isinstance(raw_sections, list) or not raw_sections:
        raise ValueError("Raveform sections are required")

    sections: list[dict[str, Any]] = []
    for position, raw in enumerate(raw_sections):
        if not isinstance(raw, dict):
            raise ValueError(f"Raveform section {position} must be an object")
        start = _first_number(raw, "start_sec", "start", "time")
        if start is None:
            raise ValueError(f"Raveform section {position} is missing its start time")
        label = raw.get("label", raw.get("function", raw.get("name", raw.get("type", ""))))
        sections.append(
            {
                "source_position": position,
                "start_sec": start,
                "end_sec": _first_number(raw, "end_sec", "end"),
                "label": str(label or ""),
            }
        )
    sections.sort(key=lambda item: (item["start_sec"], item["source_position"]))

    source_version = str(source.get("source_version", track.get("source_version", "unknown")))
    timestamp = created_at or _utc_now()
    records: list[dict[str, Any]] = []
    for index, section in enumerate(sections):
        end = section["end_sec"]
        if end is None and index + 1 < len(sections):
            end = sections[index + 1]["start_sec"]
        if end is None:
            end = duration
        if end is None or end <= section["start_sec"]:
            raise ValueError(f"Raveform section {index} has no valid end boundary")
        original_label = section["label"]
        record = AnnotationRecord(
            annotation_id=f"raveform-{_safe_source_id(source_track_id)}-{index:04d}",
            dataset_version=dataset_version,
            track_id=track_id,
            task_id="structure.section_label",
            granularity="section",
            start_sec=round(section["start_sec"], 6),
            end_sec=round(end, 6),
            start_bar_index=None,
            end_bar_index=None,
            value=map_raveform_section_label(original_label),
            annotator_id="dataset-raveform",
            annotation_status="candidate",
            annotator_confidence=None,
            candidate_source=(
                f"dataset:raveform:{source_version}:label={original_label or '<empty>'}"
            ),
            created_at=timestamp,
        )
        records.append(record.model_dump(mode="json"))
    return records
