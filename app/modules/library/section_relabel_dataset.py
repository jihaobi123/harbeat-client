"""Versioned contract shared by section-label annotation and training tools."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from app.modules.library.section_contract import canonical_structure_label
from app.modules.library.section_relabeler import (
    STRUCTURE_LABELS,
    build_track_feature_matrix,
    feature_names,
)


DATASET_SCHEMA_VERSION = "harbeat_section_label_dataset_v1"
DATASET_SPLITS = ("development", "test")
HUMAN_CONFIDENCE_LEVELS = ("", "high", "medium", "low")
ANNOTATION_FIELDS = {
    "human_label",
    "human_confidence",
    "boundary_ok",
    "uncertain",
    "notes",
}


class DatasetValidationError(ValueError):
    """Raised when annotation output cannot be consumed safely by training."""

    def __init__(self, issues: list[str]):
        self.issues = list(issues)
        preview = "; ".join(self.issues[:10])
        if len(self.issues) > 10:
            preview += f"; ... and {len(self.issues) - 10} more"
        super().__init__(preview)


def annotation_is_reviewed(annotation: Mapping[str, Any]) -> bool:
    label = canonical_structure_label(annotation.get("human_label"))
    return (
        label in STRUCTURE_LABELS
        or bool(annotation.get("uncertain"))
        or annotation.get("boundary_ok") is False
    )


def annotation_is_trainable(
    annotation: Mapping[str, Any], *, include_low_confidence: bool = False
) -> bool:
    label = canonical_structure_label(annotation.get("human_label"))
    return (
        label in STRUCTURE_LABELS
        and not bool(annotation.get("uncertain"))
        and annotation.get("boundary_ok") is not False
        and (
            include_low_confidence
            or annotation.get("human_confidence") != "low"
        )
    )


def validate_annotation(
    raw: object,
    *,
    location: str = "annotation",
    require_all_fields: bool = True,
) -> dict[str, Any]:
    """Validate one workbench annotation and return a normalized copy."""
    issues: list[str] = []
    if not isinstance(raw, Mapping):
        raise DatasetValidationError([f"{location} must be an object"])
    annotation = dict(raw)
    unknown = sorted(set(annotation) - ANNOTATION_FIELDS)
    if unknown:
        issues.append(f"{location} has unsupported fields: {', '.join(unknown)}")
    if require_all_fields:
        missing = sorted(ANNOTATION_FIELDS - set(annotation))
        if missing:
            issues.append(f"{location} is missing fields: {', '.join(missing)}")

    human_label = str(annotation.get("human_label") or "").strip().lower()
    if human_label and canonical_structure_label(human_label) not in STRUCTURE_LABELS:
        issues.append(f"{location}.human_label is unsupported: {human_label}")
    confidence = str(annotation.get("human_confidence") or "").strip().lower()
    if confidence not in HUMAN_CONFIDENCE_LEVELS:
        issues.append(f"{location}.human_confidence is invalid: {confidence}")
    for field in ("boundary_ok", "uncertain"):
        if field in annotation and not isinstance(annotation[field], bool):
            issues.append(f"{location}.{field} must be boolean")
    notes = annotation.get("notes", "")
    if not isinstance(notes, str):
        issues.append(f"{location}.notes must be a string")

    uncertain = bool(annotation.get("uncertain"))
    boundary_ok = annotation.get("boundary_ok", True)
    if human_label and uncertain:
        issues.append(f"{location} cannot have both human_label and uncertain=true")
    if human_label and boundary_ok is False:
        issues.append(f"{location} cannot have both human_label and boundary_ok=false")
    if uncertain and boundary_ok is False:
        issues.append(f"{location} cannot be both uncertain and a boundary error")
    if human_label and not confidence:
        issues.append(f"{location}.human_confidence is required for a human label")

    if issues:
        raise DatasetValidationError(issues)
    return {
        "human_label": canonical_structure_label(human_label) if human_label else "",
        "human_confidence": confidence,
        "boundary_ok": bool(boundary_ok),
        "uncertain": uncertain,
        "notes": notes,
    }


def validate_annotation_patch(raw: object) -> dict[str, Any]:
    """Validate fields received from the browser before merging them."""
    if not isinstance(raw, Mapping):
        raise DatasetValidationError(["annotation patch must be an object"])
    patch = dict(raw)
    unknown = sorted(set(patch) - ANNOTATION_FIELDS)
    if unknown:
        raise DatasetValidationError(
            [f"annotation patch has unsupported fields: {', '.join(unknown)}"]
        )
    probe = {
        "human_label": "",
        "human_confidence": "",
        "boundary_ok": True,
        "uncertain": False,
        "notes": "",
        **patch,
    }
    normalized = validate_annotation(probe)
    return {field: normalized[field] for field in patch}


def _finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def validate_dataset(
    payload: object,
    *,
    require_audio: bool = False,
    require_complete_splits: tuple[str, ...] = (),
    include_low_confidence: bool = False,
) -> dict[str, Any]:
    """Validate the full annotation/training contract and summarize progress."""
    if not isinstance(payload, Mapping):
        raise DatasetValidationError(["dataset root must be an object"])
    issues: list[str] = []
    if payload.get("schema_version") != DATASET_SCHEMA_VERSION:
        issues.append(
            "schema_version must be "
            f"{DATASET_SCHEMA_VERSION}, got {payload.get('schema_version')!r}"
        )
    tracks = payload.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        issues.append("tracks must be a non-empty list")
        tracks = []

    seen_track_ids: set[str] = set()
    track_counts: Counter[str] = Counter()
    segment_counts: Counter[str] = Counter()
    reviewed_counts: Counter[str] = Counter()
    trainable_counts: Counter[str] = Counter()
    uncertain_counts: Counter[str] = Counter()
    boundary_error_counts: Counter[str] = Counter()
    low_confidence_counts: Counter[str] = Counter()
    class_counts: dict[str, Counter[str]] = {
        split: Counter() for split in DATASET_SPLITS
    }

    for track_position, raw_track in enumerate(tracks):
        track_location = f"tracks[{track_position}]"
        if not isinstance(raw_track, Mapping):
            issues.append(f"{track_location} must be an object")
            continue
        track = dict(raw_track)
        track_id = str(track.get("track_id") or "").strip()
        if not track_id:
            issues.append(f"{track_location}.track_id is required")
        elif track_id in seen_track_ids:
            issues.append(f"duplicate track_id: {track_id}")
        else:
            seen_track_ids.add(track_id)
        split = str(track.get("split") or "").strip()
        if split not in DATASET_SPLITS:
            issues.append(f"{track_location}.split is invalid: {split!r}")
            continue
        track_counts[split] += 1
        if require_audio:
            audio_path = Path(str(track.get("audio_path") or "")).expanduser()
            if not audio_path.is_file():
                issues.append(f"{track_location}.audio_path does not exist: {audio_path}")
        duration = track.get("duration")
        if duration is not None and (
            _finite_number(duration) is None or float(duration) <= 0
        ):
            issues.append(f"{track_location}.duration must be a positive finite number")

        segments = track.get("segments")
        if not isinstance(segments, list) or not segments:
            issues.append(f"{track_location}.segments must be a non-empty list")
            continue
        previous_end = 0.0
        for index, raw_segment in enumerate(segments):
            location = f"{track_location}.segments[{index}]"
            segment_counts[split] += 1
            if not isinstance(raw_segment, Mapping):
                issues.append(f"{location} must be an object")
                continue
            segment = dict(raw_segment)
            if segment.get("segment_index") != index:
                issues.append(
                    f"{location}.segment_index must equal its list position {index}"
                )
            start = _finite_number(segment.get("start"))
            end = _finite_number(segment.get("end"))
            if start is None or end is None or start < 0 or end <= start:
                issues.append(f"{location} has invalid start/end")
            elif start + 1e-3 < previous_end:
                issues.append(f"{location} overlaps the previous segment")
            if end is not None:
                previous_end = end

            candidate = canonical_structure_label(
                segment.get("structure_label_candidate")
            )
            if candidate not in STRUCTURE_LABELS:
                issues.append(
                    f"{location}.structure_label_candidate is invalid: {candidate}"
                )
            raw_probabilities = segment.get("structure_label_probabilities")
            if not isinstance(raw_probabilities, Mapping):
                issues.append(
                    f"{location}.structure_label_probabilities must be an object"
                )
            else:
                probabilities = {
                    canonical_structure_label(label): _finite_number(value)
                    for label, value in raw_probabilities.items()
                }
                if set(probabilities) != set(STRUCTURE_LABELS):
                    missing = sorted(set(STRUCTURE_LABELS) - set(probabilities))
                    extra = sorted(set(probabilities) - set(STRUCTURE_LABELS))
                    issues.append(
                        f"{location} probability labels mismatch; "
                        f"missing={missing}, extra={extra}"
                    )
                elif any(value is None or value < 0 for value in probabilities.values()):
                    issues.append(f"{location} has invalid probability values")
                elif not math.isclose(
                    sum(float(value) for value in probabilities.values()),
                    1.0,
                    rel_tol=0.0,
                    abs_tol=1e-5,
                ):
                    issues.append(f"{location} probabilities do not sum to 1")

            try:
                annotation = validate_annotation(
                    segment.get("annotation"), location=f"{location}.annotation"
                )
            except DatasetValidationError as exc:
                issues.extend(exc.issues)
                continue
            if annotation_is_reviewed(annotation):
                reviewed_counts[split] += 1
            if annotation_is_trainable(
                annotation, include_low_confidence=include_low_confidence
            ):
                trainable_counts[split] += 1
                class_counts[split][annotation["human_label"]] += 1
            if annotation["uncertain"]:
                uncertain_counts[split] += 1
            if annotation["boundary_ok"] is False:
                boundary_error_counts[split] += 1
            if annotation["human_confidence"] == "low" and annotation["human_label"]:
                low_confidence_counts[split] += 1

        if all(isinstance(segment, Mapping) for segment in segments):
            try:
                matrix = build_track_feature_matrix(segments, duration=duration)
                expected_shape = (len(segments), len(feature_names()))
                if matrix.shape != expected_shape:
                    issues.append(
                        f"{track_location} feature matrix shape is {matrix.shape}, "
                        f"expected {expected_shape}"
                    )
                elif not np.all(np.isfinite(matrix)):
                    issues.append(f"{track_location} feature matrix contains non-finite values")
            except (KeyError, TypeError, ValueError) as exc:
                issues.append(f"{track_location} cannot build training features: {exc}")

    declared_counts = payload.get("track_counts")
    if isinstance(declared_counts, Mapping):
        for split in DATASET_SPLITS:
            declared = declared_counts.get(split)
            if declared is not None and declared != track_counts[split]:
                issues.append(
                    f"track_counts.{split}={declared} does not match {track_counts[split]}"
                )
        declared_total = declared_counts.get("total")
        if declared_total is not None and declared_total != len(tracks):
            issues.append(
                f"track_counts.total={declared_total} does not match {len(tracks)}"
            )

    for split in require_complete_splits:
        if split not in DATASET_SPLITS:
            issues.append(f"unknown required split: {split}")
        elif reviewed_counts[split] != segment_counts[split]:
            issues.append(
                f"{split} review is incomplete: "
                f"{reviewed_counts[split]}/{segment_counts[split]} segments reviewed"
            )

    if issues:
        raise DatasetValidationError(issues)
    return {
        "schema_version": DATASET_SCHEMA_VERSION,
        "tracks": {split: track_counts[split] for split in DATASET_SPLITS},
        "segments": {split: segment_counts[split] for split in DATASET_SPLITS},
        "reviewed": {split: reviewed_counts[split] for split in DATASET_SPLITS},
        "trainable": {split: trainable_counts[split] for split in DATASET_SPLITS},
        "excluded": {
            split: {
                "uncertain": uncertain_counts[split],
                "boundary_error": boundary_error_counts[split],
                "low_confidence": low_confidence_counts[split],
            }
            for split in DATASET_SPLITS
        },
        "class_counts": {
            split: dict(class_counts[split]) for split in DATASET_SPLITS
        },
        "feature_count": len(feature_names()),
    }
