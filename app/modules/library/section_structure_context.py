"""Whole-song recurrence features derived from cached SongFormer encoders."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


STRUCTURE_CONTEXT_VERSION = "songformer_structure_context_v2"
STRUCTURE_ENCODER_PROJECTION_VERSION = "songformer_encoder_projection_v1"
STRUCTURE_ENCODER_PROJECTION_DIMENSIONS_PER_VIEW = 128
STRUCTURE_ENCODER_PROJECTION_SEED = 43
STRUCTURE_ENCODER_VIEW_NAMES = (
    "musicfm_global_raw",
    "musicfm_global_centered",
    "musicfm_local_raw",
    "musicfm_local_centered",
    "muq_global_raw",
    "muq_global_centered",
    "muq_local_raw",
    "muq_local_centered",
)
STRUCTURE_ENCODER_PROJECTION_FEATURE_COUNT = (
    len(STRUCTURE_ENCODER_VIEW_NAMES) * STRUCTURE_ENCODER_PROJECTION_DIMENSIONS_PER_VIEW
)
STRUCTURE_CONTEXT_FEATURE_NAMES = (
    "candidate_track_fraction",
    "candidate_occurrence_relative",
    "same_candidate_previous_gap",
    "same_candidate_next_gap",
    "same_candidate_run_relative",
    "nearest_similarity",
    "nearest_nonadjacent_similarity",
    "top3_nonadjacent_similarity",
    "previous_best_similarity",
    "next_best_similarity",
    "nearest_distance_relative",
    "repeat_count_075_relative",
    "repeat_count_090_relative",
    "same_candidate_similarity",
    "cross_candidate_similarity",
    "repeats_before_and_after",
    "musicfm_global_similarity",
    "musicfm_local_similarity",
    "muq_global_similarity",
    "muq_local_similarity",
    "nearest_view_similarity_std",
    "previous_adjacent_similarity",
    "next_adjacent_similarity",
    "nonadjacent_similarity_margin",
)


def _array(value: object) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    array = np.asarray(value, dtype=np.float64)
    if array.ndim == 3 and array.shape[0] == 1:
        array = array[0]
    if array.ndim != 2 or not array.shape[0] or not array.shape[1]:
        raise ValueError(f"encoder embeddings must be [frames, dimensions], got {array.shape}")
    if not np.all(np.isfinite(array)):
        raise ValueError("encoder embeddings contain non-finite values")
    return array


def _pool_segments(
    values: object,
    segments: Sequence[Mapping[str, Any]],
    duration: float,
) -> tuple[np.ndarray, np.ndarray]:
    frames = _array(values)
    rate = frames.shape[0] / max(float(duration), 1e-6)
    pooled: list[np.ndarray] = []
    for segment in segments:
        start = max(0.0, float(segment.get("start", 0.0) or 0.0))
        end = max(start, float(segment.get("end", start) or start))
        first = min(frames.shape[0] - 1, max(0, int(np.floor(start * rate))))
        last = min(frames.shape[0], max(first + 1, int(np.ceil(end * rate))))
        pooled.append(np.mean(frames[first:last], axis=0))
    matrix = np.vstack(pooled)
    raw = matrix / np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-12)
    centered = matrix - np.mean(matrix, axis=0, keepdims=True) if len(matrix) > 1 else matrix
    centered = centered / np.maximum(np.linalg.norm(centered, axis=1, keepdims=True), 1e-12)
    return raw, centered


def _similarity(matrix: np.ndarray) -> np.ndarray:
    return np.clip(matrix @ matrix.T, -1.0, 1.0)


def _best(similarity: np.ndarray, indices: Sequence[int], default: float = 0.0) -> float:
    return float(np.max(similarity[list(indices)])) if indices else float(default)


def build_segment_structure_context(
    segments: Sequence[Mapping[str, Any]],
    *,
    encoder_views: Mapping[str, object],
    duration: float,
) -> list[dict[str, Any]]:
    """Build compact recurrence features without changing section boundaries."""
    items = [dict(segment) for segment in segments]
    if not items:
        return []
    required = ("musicfm_global", "musicfm_local", "muq_global", "muq_local")
    missing = [name for name in required if name not in encoder_views]
    if missing:
        raise ValueError(f"missing encoder views: {', '.join(missing)}")
    pooled = {
        name: _pool_segments(encoder_views[name], items, duration) for name in required
    }
    similarities = {name: _similarity(pooled[name][1]) for name in required}
    projection_rng = np.random.default_rng(STRUCTURE_ENCODER_PROJECTION_SEED)
    projected_views: list[np.ndarray] = []
    for name in required:
        for matrix in pooled[name]:
            projection = projection_rng.normal(
                0.0,
                1.0 / np.sqrt(STRUCTURE_ENCODER_PROJECTION_DIMENSIONS_PER_VIEW),
                size=(matrix.shape[1], STRUCTURE_ENCODER_PROJECTION_DIMENSIONS_PER_VIEW),
            )
            projected_views.append(matrix @ projection)
    encoder_projection = np.hstack(projected_views)
    combined = np.mean(np.stack(list(similarities.values())), axis=0)
    labels = [
        str(
            item.get("structure_label_candidate")
            or item.get("songformer_label")
            or item.get("label")
            or ""
        )
        for item in items
    ]
    count = len(items)
    result: list[dict[str, Any]] = []
    for index in range(count):
        other = [value for value in range(count) if value != index]
        nonadjacent = [value for value in other if abs(value - index) > 1]
        comparison = nonadjacent or other
        previous = [value for value in other if value < index]
        following = [value for value in other if value > index]
        same = [value for value in other if labels[value] == labels[index]]
        cross = [value for value in other if labels[value] != labels[index]]
        row = combined[index]
        nearest = max(comparison, key=lambda value: row[value]) if comparison else index
        ranked = sorted((float(row[value]) for value in comparison), reverse=True)
        candidate_positions = [value for value, label in enumerate(labels) if label == labels[index]]
        occurrence = candidate_positions.index(index)
        previous_same = [value for value in same if value < index]
        next_same = [value for value in same if value > index]
        run = 1
        cursor = index - 1
        while cursor >= 0 and labels[cursor] == labels[index]:
            run += 1
            cursor -= 1
        cursor = index + 1
        while cursor < count and labels[cursor] == labels[index]:
            run += 1
            cursor += 1
        repeat_before = any(row[value] >= 0.75 for value in previous)
        repeat_after = any(row[value] >= 0.75 for value in following)
        view_values = [similarities[name][index, nearest] for name in required]
        top = ranked[:3]
        features = {
            "candidate_track_fraction": len(candidate_positions) / count,
            "candidate_occurrence_relative": occurrence / max(len(candidate_positions) - 1, 1),
            "same_candidate_previous_gap": (
                (index - max(previous_same)) / max(count - 1, 1) if previous_same else 1.0
            ),
            "same_candidate_next_gap": (
                (min(next_same) - index) / max(count - 1, 1) if next_same else 1.0
            ),
            "same_candidate_run_relative": run / count,
            "nearest_similarity": _best(row, other),
            "nearest_nonadjacent_similarity": _best(row, comparison),
            "top3_nonadjacent_similarity": float(np.mean(top)) if top else 0.0,
            "previous_best_similarity": _best(row, previous),
            "next_best_similarity": _best(row, following),
            "nearest_distance_relative": abs(nearest - index) / max(count - 1, 1),
            "repeat_count_075_relative": sum(row[value] >= 0.75 for value in other) / max(count - 1, 1),
            "repeat_count_090_relative": sum(row[value] >= 0.90 for value in other) / max(count - 1, 1),
            "same_candidate_similarity": _best(row, same),
            "cross_candidate_similarity": _best(row, cross),
            "repeats_before_and_after": float(repeat_before and repeat_after),
            "musicfm_global_similarity": float(view_values[0]) if comparison else 0.0,
            "musicfm_local_similarity": float(view_values[1]) if comparison else 0.0,
            "muq_global_similarity": float(view_values[2]) if comparison else 0.0,
            "muq_local_similarity": float(view_values[3]) if comparison else 0.0,
            "nearest_view_similarity_std": float(np.std(view_values)) if comparison else 0.0,
            "previous_adjacent_similarity": float(row[index - 1]) if index else 0.0,
            "next_adjacent_similarity": float(row[index + 1]) if index + 1 < count else 0.0,
            "nonadjacent_similarity_margin": (top[0] - top[1]) if len(top) > 1 else (top[0] if top else 0.0),
        }
        result.append(
            {
                "schema_version": STRUCTURE_CONTEXT_VERSION,
                **{name: float(features[name]) for name in STRUCTURE_CONTEXT_FEATURE_NAMES},
                "encoder_projection": {
                    "schema_version": STRUCTURE_ENCODER_PROJECTION_VERSION,
                    "values": [float(value) for value in encoder_projection[index]],
                },
            }
        )
    return result


def structure_context_is_complete(segment: Mapping[str, Any]) -> bool:
    raw = segment.get("structure_context_features")
    if not isinstance(raw, Mapping) or raw.get("schema_version") != STRUCTURE_CONTEXT_VERSION:
        return False
    try:
        values = np.asarray([raw[name] for name in STRUCTURE_CONTEXT_FEATURE_NAMES], dtype=float)
    except (KeyError, TypeError, ValueError):
        return False
    projection = raw.get("encoder_projection")
    if not isinstance(projection, Mapping) or projection.get("schema_version") != STRUCTURE_ENCODER_PROJECTION_VERSION:
        return False
    try:
        projected = np.asarray(projection.get("values"), dtype=float)
    except (TypeError, ValueError):
        return False
    return bool(
        np.all(np.isfinite(values))
        and projected.shape == (STRUCTURE_ENCODER_PROJECTION_FEATURE_COUNT,)
        and np.all(np.isfinite(projected))
    )
