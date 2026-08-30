"""Metrics used to calibrate music features and multi-label style decisions.

The benchmark layer deliberately stays separate from production inference.  It
compares saved analysis results with public-dataset or human annotations, so a
passing unit test is never confused with acoustic accuracy.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

import numpy as np


BENCHMARK_EVALUATION_VERSION = "music_benchmark_evaluation_v2"


def _divide(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def binary_metrics(expected: Iterable[bool], predicted: Iterable[bool]) -> dict[str, Any]:
    # Normalize NumPy scalar booleans so metric payloads remain ordinary JSON
    # primitives when evaluators operate on vectorized annotations.
    pairs = [
        (bool(reference), bool(decision))
        for reference, decision in zip(expected, predicted, strict=True)
    ]
    tp = sum(reference and decision for reference, decision in pairs)
    fp = sum(not reference and decision for reference, decision in pairs)
    fn = sum(reference and not decision for reference, decision in pairs)
    tn = sum(not reference and not decision for reference, decision in pairs)
    precision = _divide(tp, tp + fp)
    recall = _divide(tp, tp + fn)
    return {
        "sample_count": len(pairs),
        "positive_count": tp + fn,
        "negative_count": tn + fp,
        "true_positive": tp,
        "false_positive": fp,
        "false_negative": fn,
        "true_negative": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(_divide(2.0 * precision * recall, precision + recall), 4),
        "accuracy": round(_divide(tp + tn, len(pairs)), 4),
    }


def select_threshold(
    examples: Iterable[tuple[float, bool]],
    *,
    candidates: Iterable[float] | None = None,
) -> dict[str, Any]:
    """Choose an F1-optimal threshold without treating the result as universal."""
    rows = [(float(score), bool(expected)) for score, expected in examples]
    values = list(candidates or [value / 100.0 for value in range(20, 86, 2)])
    trials = []
    for threshold in values:
        metrics = binary_metrics(
            (expected for _, expected in rows),
            (score >= threshold for score, _ in rows),
        )
        trials.append({"threshold": round(float(threshold), 4), **metrics})
    # Prefer recall after F1, then the threshold closest to the current neutral
    # boundary.  This gives deterministic output without implying false
    # precision from tiny benchmark sets.
    best = max(
        trials,
        key=lambda item: (item["f1"], item["recall"], -abs(item["threshold"] - 0.55)),
        default={"threshold": 0.55, **binary_metrics([], [])},
    )
    return {
        "version": BENCHMARK_EVALUATION_VERSION,
        "selected": best,
        "trials": trials,
        "warning": None if len(rows) >= 30 else "insufficient_samples_for_release_calibration",
    }


def multilabel_metrics(
    expected: Iterable[Iterable[str]],
    predicted: Iterable[Iterable[str]],
) -> dict[str, Any]:
    pairs = [
        ({str(value) for value in reference}, {str(value) for value in decision})
        for reference, decision in zip(expected, predicted, strict=True)
    ]
    labels = sorted(set().union(*(reference | decision for reference, decision in pairs))) if pairs else []
    per_label = {}
    micro_tp = micro_fp = micro_fn = 0
    for label in labels:
        metrics = binary_metrics(
            (label in reference for reference, _ in pairs),
            (label in decision for _, decision in pairs),
        )
        per_label[label] = metrics
        micro_tp += metrics["true_positive"]
        micro_fp += metrics["false_positive"]
        micro_fn += metrics["false_negative"]
    micro_precision = _divide(micro_tp, micro_tp + micro_fp)
    micro_recall = _divide(micro_tp, micro_tp + micro_fn)
    macro_f1 = _divide(sum(item["f1"] for item in per_label.values()), len(per_label))
    return {
        "version": BENCHMARK_EVALUATION_VERSION,
        "sample_count": len(pairs),
        "label_count": len(labels),
        "exact_match_ratio": round(
            _divide(sum(reference == decision for reference, decision in pairs), len(pairs)), 4,
        ),
        "micro_precision": round(micro_precision, 4),
        "micro_recall": round(micro_recall, 4),
        "micro_f1": round(
            _divide(2.0 * micro_precision * micro_recall, micro_precision + micro_recall), 4,
        ),
        "macro_f1": round(macro_f1, 4),
        "per_label": per_label,
    }


def _event_time(value: float | dict[str, Any]) -> float:
    if isinstance(value, dict):
        return float(value["time"])
    return float(value)


def onset_event_metrics(
    expected: dict[str, Iterable[float | dict[str, Any]]],
    predicted: dict[str, Iterable[float | dict[str, Any]]],
    *,
    tolerance_seconds: float = 0.05,
) -> dict[str, Any]:
    """Score drum/note onsets with one-to-one, class-aware matching.

    A prediction may match at most one reference event and vice versa.  This
    prevents several nearby detector peaks from receiving credit for one hit.
    Accuracy is intentionally omitted because continuous time has no meaningful
    count of true-negative event positions.
    """
    if tolerance_seconds <= 0:
        raise ValueError("tolerance_seconds must be positive")
    labels = sorted(set(expected) | set(predicted))
    per_class: dict[str, dict[str, Any]] = {}
    total_reference = total_prediction = total_matches = 0
    all_errors: list[float] = []
    for label in labels:
        references = sorted(_event_time(value) for value in expected.get(label, []))
        decisions = sorted(_event_time(value) for value in predicted.get(label, []))
        candidates = sorted(
            (
                abs(reference - decision),
                reference_index,
                decision_index,
            )
            for reference_index, reference in enumerate(references)
            for decision_index, decision in enumerate(decisions)
            if abs(reference - decision) <= tolerance_seconds
        )
        used_references: set[int] = set()
        used_decisions: set[int] = set()
        errors: list[float] = []
        for error, reference_index, decision_index in candidates:
            if reference_index in used_references or decision_index in used_decisions:
                continue
            used_references.add(reference_index)
            used_decisions.add(decision_index)
            errors.append(error)
        matches = len(errors)
        precision = _divide(matches, len(decisions))
        recall = _divide(matches, len(references))
        per_class[label] = {
            "reference_count": len(references),
            "prediction_count": len(decisions),
            "matches": matches,
            "false_positive": len(decisions) - matches,
            "false_negative": len(references) - matches,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(_divide(2.0 * precision * recall, precision + recall), 4),
            "mean_absolute_error_ms": (
                round(1000.0 * sum(errors) / len(errors), 3) if errors else None
            ),
        }
        total_reference += len(references)
        total_prediction += len(decisions)
        total_matches += matches
        all_errors.extend(errors)
    precision = _divide(total_matches, total_prediction)
    recall = _divide(total_matches, total_reference)
    return {
        "version": BENCHMARK_EVALUATION_VERSION,
        "tolerance_seconds": round(float(tolerance_seconds), 4),
        "reference_count": total_reference,
        "prediction_count": total_prediction,
        "matches": total_matches,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(_divide(2.0 * precision * recall, precision + recall), 4),
        "mean_absolute_error_ms": (
            round(1000.0 * sum(all_errors) / len(all_errors), 3) if all_errors else None
        ),
        "per_class": per_class,
    }


def event_release_gate(
    metrics: dict[str, Any],
    *,
    minimum_reference_events: int = 100,
    minimum_precision: float = 0.80,
    minimum_recall: float = 0.80,
    minimum_f1: float = 0.80,
) -> dict[str, Any]:
    """Decide whether event evidence may leave evaluation-only status."""
    reasons = []
    if int(metrics.get("reference_count", 0)) < minimum_reference_events:
        reasons.append("insufficient_reference_events")
    if float(metrics.get("precision", 0.0)) < minimum_precision:
        reasons.append("precision_below_gate")
    if float(metrics.get("recall", 0.0)) < minimum_recall:
        reasons.append("recall_below_gate")
    if float(metrics.get("f1", 0.0)) < minimum_f1:
        reasons.append("f1_below_gate")
    return {
        "passed": not reasons,
        "reasons": reasons,
        "thresholds": {
            "minimum_reference_events": minimum_reference_events,
            "minimum_precision": minimum_precision,
            "minimum_recall": minimum_recall,
            "minimum_f1": minimum_f1,
        },
    }


def tempo_metrics(
    expected: Iterable[float],
    predicted: Iterable[float],
    *,
    tolerance_fraction: float = 0.04,
) -> dict[str, Any]:
    """MIREX-style tempo Acc1 and metrical-level-tolerant Acc2 metrics."""
    pairs = [(float(reference), float(decision)) for reference, decision in zip(
        expected, predicted, strict=True,
    )]
    relative_errors = []
    acc1 = []
    acc2 = []
    metrical_ratios = (0.5, 1.0, 2.0, 1.0 / 3.0, 3.0)
    for reference, decision in pairs:
        if reference <= 0 or decision <= 0:
            relative_errors.append(float("inf"))
            acc1.append(False)
            acc2.append(False)
            continue
        error = abs(decision - reference) / reference
        relative_errors.append(error)
        acc1.append(error <= tolerance_fraction)
        acc2.append(any(
            abs(decision - reference * ratio) / (reference * ratio) <= tolerance_fraction
            for ratio in metrical_ratios
        ))
    finite = [value for value in relative_errors if np.isfinite(value)]
    return {
        "version": BENCHMARK_EVALUATION_VERSION,
        "sample_count": len(pairs),
        "tolerance_fraction": tolerance_fraction,
        "accuracy_1": round(_divide(sum(acc1), len(acc1)), 4),
        "accuracy_2": round(_divide(sum(acc2), len(acc2)), 4),
        "mean_absolute_relative_error": (
            round(float(np.mean(finite)), 4) if finite else None
        ),
        "median_absolute_relative_error": (
            round(float(np.median(finite)), 4) if finite else None
        ),
        "correct_1": sum(acc1),
        "correct_2": sum(acc2),
    }


def dataset_breakdown(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Expose sample provenance so one large dataset cannot hide domain bias."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"items": 0, "annotated": 0})
    for row in rows:
        name = str(row.get("dataset") or "unknown")
        counts[name]["items"] += 1
        if row.get("expected_features") or row.get("expected_styles"):
            counts[name]["annotated"] += 1
    return dict(sorted(counts.items()))
