"""Calibrate two drum-overlap thresholds from human-labelled JSONL pairs.

Each line must contain ``score`` plus ``human_band`` and should also contain
``song_a_id`` and ``song_b_id`` for auditability. Thresholds are selected only
on --train. Supplying --test produces the held-out evidence required before the
runtime policy may be marked validated.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


LABELS = ("fx_transition", "standard_mix", "harmonic_check")
DEFAULT_CATEGORY_WEIGHT = 0.40


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        has_components = (
            value.get("category_overlap_score") is not None
            and value.get("rhythm_landing_similarity_score") is not None
        )
        if value.get("score") is None and not has_components:
            raise ValueError(
                f"{path}:{line_number}: provide score or both component scores"
            )
        label = str(value["human_band"])
        if label not in LABELS:
            raise ValueError(f"{path}:{line_number}: unsupported human_band {label!r}")
        score = float(value.get("score", 0.0))
        if has_components:
            category = float(value["category_overlap_score"])
            rhythm = float(value["rhythm_landing_similarity_score"])
            if not 0.0 <= category <= 1.0 or not 0.0 <= rhythm <= 1.0:
                raise ValueError(
                    f"{path}:{line_number}: component scores must be within 0..1"
                )
            if value.get("score") is None:
                score = DEFAULT_CATEGORY_WEIGHT * category + (
                    1.0 - DEFAULT_CATEGORY_WEIGHT
                ) * rhythm
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"{path}:{line_number}: score must be within 0..1")
        normalized = {**value, "score": score, "human_band": label}
        if has_components:
            normalized["category_overlap_score"] = category
            normalized["rhythm_landing_similarity_score"] = rhythm
        rows.append(normalized)
    if not rows:
        raise ValueError(f"no labelled rows in {path}")
    return rows


def _predict(score: float, low: float, high: float) -> str:
    if score < low:
        return LABELS[0]
    if score <= high:
        return LABELS[1]
    return LABELS[2]


def _effective_score(row: dict[str, Any], category_weight: float | None) -> float:
    if category_weight is None:
        return float(row["score"])
    return (
        category_weight * float(row["category_overlap_score"])
        + (1.0 - category_weight) * float(row["rhythm_landing_similarity_score"])
    )


def evaluate(
    rows: Iterable[dict[str, Any]],
    low: float,
    high: float,
    *,
    category_weight: float | None = None,
) -> dict[str, Any]:
    values = list(rows)
    confusion = {truth: {pred: 0 for pred in LABELS} for truth in LABELS}
    for row in values:
        truth = row["human_band"]
        prediction = _predict(_effective_score(row, category_weight), low, high)
        confusion[truth][prediction] += 1
    class_metrics = {}
    for label in LABELS:
        true_positive = confusion[label][label]
        false_positive = sum(confusion[truth][label] for truth in LABELS if truth != label)
        false_negative = sum(confusion[label][pred] for pred in LABELS if pred != label)
        precision = true_positive / max(1, true_positive + false_positive)
        recall = true_positive / max(1, true_positive + false_negative)
        f1 = 2 * precision * recall / max(1e-12, precision + recall)
        class_metrics[label] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": sum(confusion[label].values()),
        }
    accuracy = sum(confusion[label][label] for label in LABELS) / len(values)
    macro_f1 = sum(class_metrics[label]["f1"] for label in LABELS) / len(LABELS)
    return {
        "rows": len(values),
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "classes": class_metrics,
        "confusion": confusion,
    }


def calibrate(
    rows: list[dict[str, Any]],
) -> tuple[float, float, float | None, dict[str, Any]]:
    threshold_candidates = [round(value / 100, 2) for value in range(1, 100)]
    has_all_components = _all_have_components(rows)
    weight_candidates: list[float | None] = (
        [round(value / 20, 2) for value in range(1, 20)]
        if has_all_components
        else [None]
    )
    best: tuple[
        float, float, float, float, float, float | None, dict[str, Any]
    ] | None = None
    for category_weight in weight_candidates:
        for low in threshold_candidates:
            for high in threshold_candidates:
                if high - low < 0.05:
                    continue
                metrics = evaluate(
                    rows,
                    low,
                    high,
                    category_weight=category_weight,
                )
                weight_distance = (
                    abs(category_weight - DEFAULT_CATEGORY_WEIGHT)
                    if category_weight is not None
                    else 0.0
                )
                distance_from_proposal = (
                    abs(low - 0.70) + abs(high - 0.85) + weight_distance
                )
                rank = (
                    float(metrics["macro_f1"]),
                    float(metrics["accuracy"]),
                    -distance_from_proposal,
                )
                if best is None or rank > best[:3]:
                    best = (*rank, low, high, category_weight, metrics)
    if best is None:
        raise RuntimeError("unable to find threshold candidates")
    return float(best[3]), float(best[4]), best[5], best[6]


def _all_have_components(rows: Iterable[dict[str, Any]]) -> bool:
    return all(
        row.get("category_overlap_score") is not None
        and row.get("rhythm_landing_similarity_score") is not None
        for row in rows
    )


def _song_ids(rows: Iterable[dict[str, Any]]) -> set[str]:
    result: set[str] = set()
    for row in rows:
        for key in ("song_a_id", "song_b_id"):
            if row.get(key) is not None:
                result.add(str(row[key]))
    return result


def audit_split(
    train: Iterable[dict[str, Any]],
    test: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    train_rows = list(train)
    test_rows = list(test)
    train_song_ids = _song_ids(train_rows)
    test_song_ids = _song_ids(test_rows)
    overlap = sorted(train_song_ids & test_song_ids)
    missing_ids = not train_song_ids or not test_song_ids
    missing_train_labels = sorted(set(LABELS) - {row["human_band"] for row in train_rows})
    missing_test_labels = sorted(set(LABELS) - {row["human_band"] for row in test_rows})
    return {
        "train_song_count": len(train_song_ids),
        "test_song_count": len(test_song_ids),
        "overlapping_song_ids": overlap,
        "song_disjoint": not overlap and not missing_ids,
        "ids_complete": not missing_ids,
        "missing_train_labels": missing_train_labels,
        "missing_test_labels": missing_test_labels,
        "class_coverage_complete": not missing_train_labels and not missing_test_labels,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", required=True, type=Path)
    parser.add_argument("--test", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    train = _load_jsonl(args.train)
    low, high, category_weight, train_metrics = calibrate(train)
    effective_category_weight = (
        category_weight if category_weight is not None else DEFAULT_CATEGORY_WEIGHT
    )
    payload: dict[str, Any] = {
        "status": "train_only_not_validated",
        "weights": {
            "category": effective_category_weight,
            "rhythm_landing": 1.0 - effective_category_weight,
            "optimized": category_weight is not None,
        },
        "thresholds": {"low": low, "high": high},
        "train": train_metrics,
        "proposal_baseline": {
            "thresholds": {"low": 0.70, "high": 0.85},
            "train": evaluate(train, 0.70, 0.85),
        },
    }
    if args.test:
        test = _load_jsonl(args.test)
        if category_weight is not None and not _all_have_components(test):
            raise ValueError(
                "test rows must include both component scores when train optimized weights"
            )
        split_audit = audit_split(train, test)
        payload["split_audit"] = split_audit
        if not split_audit["ids_complete"]:
            payload["status"] = "heldout_invalid_missing_song_ids"
        elif not split_audit["song_disjoint"]:
            payload["status"] = "heldout_invalid_song_leakage"
        elif not split_audit["class_coverage_complete"]:
            payload["status"] = "heldout_invalid_class_coverage"
        else:
            payload["status"] = "heldout_validated"
        payload["test"] = evaluate(
            test,
            low,
            high,
            category_weight=category_weight,
        )
        payload["proposal_baseline"]["test"] = evaluate(test, 0.70, 0.85)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
