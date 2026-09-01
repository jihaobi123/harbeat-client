"""Small, versioned residual classifier for SongFormer section labels.

SongFormer remains the boundary provider.  This module only proposes or applies
label changes from a JSON-exported linear classifier.  Missing models, missing
probabilities, and schema mismatches fail closed to the SongFormer candidate.
"""

from __future__ import annotations

import json
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from app.modules.library.section_contract import (
    canonical_structure_label,
    normalize_structure_probabilities,
)


RELABELER_SCHEMA_VERSION = "harbeat_section_relabeler_v1"
# SongFormer evidence keeps its original eight-class vocabulary.  In particular,
# ``silence`` remains a source feature so old and newly prepared datasets share
# the exact same feature schema.
SOURCE_STRUCTURE_LABELS = (
    "intro",
    "verse",
    "chorus",
    "bridge",
    "instrumental",
    "outro",
    "silence",
    "pre-chorus",
)

# Human annotations and classifier outputs use the same vocabulary as the
# normalized SongFormer evidence.
STRUCTURE_LABELS = SOURCE_STRUCTURE_LABELS


def canonical_target_structure_label(raw: object) -> str:
    """Normalize a label into the human/classifier target vocabulary."""
    return canonical_structure_label(raw)


def _probabilities(item: Mapping[str, Any]) -> dict[str, float]:
    raw = item.get("structure_label_probabilities")
    if raw is None:
        raw = item.get("label_probabilities")
    values = normalize_structure_probabilities(raw)
    if values:
        return {
            label: float(values.get(label, 0.0))
            for label in SOURCE_STRUCTURE_LABELS
        }

    candidate = canonical_structure_label(
        item.get("structure_label_candidate")
        or item.get("songformer_label")
        or item.get("label")
    )
    return {
        label: 1.0 if label == candidate else 0.0
        for label in SOURCE_STRUCTURE_LABELS
    }


def feature_names() -> list[str]:
    names: list[str] = []
    for prefix in ("prob", "log_prob", "previous_prob", "next_prob", "candidate"):
        names.extend(f"{prefix}_{label}" for label in SOURCE_STRUCTURE_LABELS)
    names.extend(
        [
            "duration_seconds",
            "log_duration_seconds",
            "relative_duration",
            "start_relative",
            "end_relative",
            "midpoint_relative",
            "segment_index_relative",
            "confidence",
            "margin",
            "entropy_normalized",
            "is_first_segment",
            "is_last_segment",
        ]
    )
    return names


def build_track_feature_matrix(
    segments: Sequence[Mapping[str, Any]],
    *,
    duration: float | None = None,
) -> np.ndarray:
    """Build deterministic per-segment features without moving boundaries."""
    items = [dict(item) for item in segments]
    if not items:
        return np.zeros((0, len(feature_names())), dtype=np.float64)

    inferred_duration = max(float(item.get("end", 0.0) or 0.0) for item in items)
    track_duration = max(float(duration or inferred_duration), 1e-6)
    probabilities = [_probabilities(item) for item in items]
    vectors: list[list[float]] = []
    count = len(items)
    zero_probabilities = {label: 0.0 for label in SOURCE_STRUCTURE_LABELS}

    for index, item in enumerate(items):
        current = probabilities[index]
        previous = probabilities[index - 1] if index > 0 else zero_probabilities
        following = probabilities[index + 1] if index + 1 < count else zero_probabilities
        candidate = canonical_structure_label(
            item.get("structure_label_candidate")
            or item.get("songformer_label")
            or item.get("label")
        )
        start = max(0.0, float(item.get("start", 0.0) or 0.0))
        end = max(start, float(item.get("end", start) or start))
        segment_duration = max(0.0, end - start)
        ranked = sorted(current.values(), reverse=True)
        confidence = ranked[0] if ranked else 0.0
        margin = confidence - (ranked[1] if len(ranked) > 1 else 0.0)
        entropy = -sum(
            value * math.log(max(value, 1e-12)) for value in current.values()
        ) / math.log(len(SOURCE_STRUCTURE_LABELS))

        vector: list[float] = []
        vector.extend(current[label] for label in SOURCE_STRUCTURE_LABELS)
        vector.extend(
            math.log(max(current[label], 1e-6))
            for label in SOURCE_STRUCTURE_LABELS
        )
        vector.extend(previous[label] for label in SOURCE_STRUCTURE_LABELS)
        vector.extend(following[label] for label in SOURCE_STRUCTURE_LABELS)
        vector.extend(
            1.0 if candidate == label else 0.0
            for label in SOURCE_STRUCTURE_LABELS
        )
        vector.extend(
            [
                segment_duration,
                math.log1p(segment_duration),
                segment_duration / track_duration,
                start / track_duration,
                end / track_duration,
                ((start + end) / 2.0) / track_duration,
                index / max(count - 1, 1),
                confidence,
                margin,
                entropy,
                1.0 if index == 0 else 0.0,
                1.0 if index == count - 1 else 0.0,
            ]
        )
        vectors.append(vector)

    matrix = np.asarray(vectors, dtype=np.float64)
    if matrix.shape[1] != len(feature_names()):
        raise RuntimeError("section relabeler feature schema is inconsistent")
    return matrix


def _validate_model(payload: Mapping[str, Any]) -> dict[str, Any]:
    model = dict(payload)
    if model.get("schema_version") != RELABELER_SCHEMA_VERSION:
        raise ValueError("unsupported section relabeler schema version")
    if list(model.get("feature_names") or []) != feature_names():
        raise ValueError("section relabeler feature names do not match runtime")
    labels = [
        canonical_target_structure_label(value) for value in model.get("labels") or []
    ]
    if not labels or len(labels) != len(set(labels)):
        raise ValueError("section relabeler labels are missing or duplicated")
    if any(label not in STRUCTURE_LABELS for label in labels):
        raise ValueError("section relabeler contains an unsupported target label")
    mean = np.asarray(model.get("feature_mean"), dtype=np.float64)
    scale = np.asarray(model.get("feature_scale"), dtype=np.float64)
    coefficients = np.asarray(model.get("coefficients"), dtype=np.float64)
    intercept = np.asarray(model.get("intercept"), dtype=np.float64)
    feature_count = len(feature_names())
    if mean.shape != (feature_count,) or scale.shape != (feature_count,):
        raise ValueError("section relabeler scaler shape is invalid")
    if coefficients.shape != (len(labels), feature_count):
        raise ValueError("section relabeler coefficient shape is invalid")
    if intercept.shape != (len(labels),):
        raise ValueError("section relabeler intercept shape is invalid")
    if not all(np.all(np.isfinite(array)) for array in (mean, scale, coefficients, intercept)):
        raise ValueError("section relabeler contains non-finite parameters")
    if np.any(scale <= 0):
        raise ValueError("section relabeler feature scale must be positive")
    model["labels"] = labels
    model["_mean"] = mean
    model["_scale"] = scale
    model["_coefficients"] = coefficients
    model["_intercept"] = intercept
    return model


def load_relabeler_model(path: str | os.PathLike[str]) -> dict[str, Any]:
    model_path = Path(path).expanduser().resolve()
    payload = json.loads(model_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("section relabeler model must be a JSON object")
    model = _validate_model(payload)
    model["model_path"] = str(model_path)
    return model


@lru_cache(maxsize=4)
def _load_relabeler_model_cached(path: str, mtime_ns: int) -> dict[str, Any]:
    del mtime_ns
    return load_relabeler_model(path)


def default_relabeler_model_path() -> Path:
    configured = os.getenv("SECTION_RELABELER_MODEL", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (
        Path(__file__).resolve().parents[3]
        / "config"
        / "model_validation"
        / "songformer_section_relabeler_v1.json"
    )


def load_default_relabeler_model() -> dict[str, Any] | None:
    path = default_relabeler_model_path()
    if not path.is_file():
        return None
    return _load_relabeler_model_cached(str(path), path.stat().st_mtime_ns)


def predict_relabeler_probabilities(
    segments: Sequence[Mapping[str, Any]],
    model: Mapping[str, Any],
) -> np.ndarray:
    validated = model if "_coefficients" in model else _validate_model(model)
    matrix = build_track_feature_matrix(segments)
    standardized = (matrix - validated["_mean"]) / validated["_scale"]
    logits = standardized @ validated["_coefficients"].T + validated["_intercept"]
    logits -= np.max(logits, axis=1, keepdims=True)
    exponentials = np.exp(logits)
    return exponentials / np.sum(exponentials, axis=1, keepdims=True)


def apply_section_relabeler(
    segments: Sequence[Mapping[str, Any]],
    *,
    model: Mapping[str, Any] | None = None,
    enabled: bool = True,
    shadow_mode: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Propose/apply labels while preserving every input start/end boundary."""
    result = [dict(item) for item in segments]
    if not result:
        return result, {"status": "empty", "changed_count": 0}
    if not enabled:
        return result, {"status": "disabled", "changed_count": 0}
    selected_model = dict(model) if model is not None else load_default_relabeler_model()
    if selected_model is None:
        return result, {"status": "model_missing", "changed_count": 0}
    validated = selected_model if "_coefficients" in selected_model else _validate_model(selected_model)
    probabilities = predict_relabeler_probabilities(result, validated)
    labels = list(validated["labels"])
    global_threshold = float(validated.get("override_threshold", 1.0))
    target_thresholds = {
        canonical_target_structure_label(key): float(value)
        for key, value in dict(validated.get("target_thresholds") or {}).items()
    }
    changed_count = 0
    proposed_count = 0

    for index, item in enumerate(result):
        source_original = canonical_structure_label(
            item.get("structure_label_candidate")
            or item.get("songformer_label")
            or item.get("label")
        )
        original = canonical_target_structure_label(source_original)
        distribution = {
            label: float(value) for label, value in zip(labels, probabilities[index])
        }
        ranked = sorted(distribution.items(), key=lambda pair: pair[1], reverse=True)
        proposed = ranked[0][0]
        confidence = ranked[0][1]
        margin = confidence - (ranked[1][1] if len(ranked) > 1 else 0.0)
        threshold = target_thresholds.get(proposed, global_threshold)
        should_override = proposed != original and confidence >= threshold
        final_label = (
            proposed if should_override and not shadow_mode else source_original
        )
        if proposed != original:
            proposed_count += 1
        if final_label != source_original:
            changed_count += 1
        item.update(
            {
                "structure_label": final_label,
                "structure_label_source": (
                    "harbeat_section_relabeler_v1"
                    if final_label != source_original
                    else "songformer_candidate"
                ),
                "relabeler_label_candidate": proposed,
                "relabeler_probabilities": distribution,
                "relabeler_confidence": confidence,
                "relabeler_margin": margin,
                "relabeler_override_threshold": threshold,
                "label_change_proposed": proposed != original,
                "label_changed": final_label != source_original,
                "relabeler_status": "shadow" if shadow_mode else "active",
                "relabeler_model_version": validated.get("model_version"),
                "label": final_label,
            }
        )

    return result, {
        "status": "shadow" if shadow_mode else "active",
        "model_version": validated.get("model_version"),
        "changed_count": changed_count,
        "proposed_change_count": proposed_count,
        "segment_count": len(result),
        "override_threshold": global_threshold,
    }
