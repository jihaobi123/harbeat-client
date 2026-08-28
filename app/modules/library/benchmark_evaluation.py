"""Metrics used to calibrate music features and multi-label style decisions.

The benchmark layer deliberately stays separate from production inference.  It
compares saved analysis results with public-dataset or human annotations, so a
passing unit test is never confused with acoustic accuracy.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


BENCHMARK_EVALUATION_VERSION = "music_benchmark_evaluation_v1"


def _divide(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else 0.0


def binary_metrics(expected: Iterable[bool], predicted: Iterable[bool]) -> dict[str, Any]:
    pairs = list(zip(expected, predicted, strict=True))
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


def dataset_breakdown(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Expose sample provenance so one large dataset cannot hide domain bias."""
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"items": 0, "annotated": 0})
    for row in rows:
        name = str(row.get("dataset") or "unknown")
        counts[name]["items"] += 1
        if row.get("expected_features") or row.get("expected_styles"):
            counts[name]["annotated"] += 1
    return dict(sorted(counts.items()))
