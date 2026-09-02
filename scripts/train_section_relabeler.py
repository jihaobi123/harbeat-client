#!/usr/bin/env python3
"""Train, cross-validate, evaluate, and export the section relabeler."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.section_relabel_dataset import (
    DatasetValidationError,
    annotation_is_reviewed,
    annotation_is_trainable,
    track_is_excluded,
    validate_dataset,
)
from app.modules.library.section_relabeler import (
    RELABELER_SCHEMA_VERSION,
    STRUCTURE_LABELS,
    build_track_feature_matrix,
    canonical_target_structure_label,
    feature_names,
    load_relabeler_model,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--model-output", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--minimum-override-precision", type=float, default=0.90)
    parser.add_argument("--minimum-override-count", type=int, default=10)
    parser.add_argument("--include-low-confidence", action="store_true")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def review_progress(payload: dict[str, Any], split: str) -> dict[str, int]:
    total = reviewed = trainable = 0
    for track in payload.get("tracks") or []:
        if track.get("split") != split or track_is_excluded(track):
            continue
        for segment in track.get("segments") or []:
            total += 1
            annotation = dict(segment.get("annotation") or {})
            reviewed += int(annotation_is_reviewed(annotation))
            trainable += int(annotation_is_trainable(annotation))
    return {"total": total, "reviewed": reviewed, "trainable": trainable}


def review_is_complete(progress: dict[str, int]) -> bool:
    """Return whether a split is eligible for its one-time locked evaluation."""
    return progress["reviewed"] == progress["total"]


def collect_rows(
    payload: dict[str, Any], split: str, *, include_low_confidence: bool
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[dict[str, Any]]]:
    features: list[np.ndarray] = []
    targets: list[str] = []
    originals: list[str] = []
    groups: list[str] = []
    records: list[dict[str, Any]] = []
    for track in payload.get("tracks") or []:
        if track.get("split") != split or track_is_excluded(track):
            continue
        segments = list(track.get("segments") or [])
        track_matrix = build_track_feature_matrix(segments, duration=track.get("duration"))
        for index, segment in enumerate(segments):
            annotation = dict(segment.get("annotation") or {})
            human_label = canonical_target_structure_label(annotation.get("human_label"))
            if human_label not in STRUCTURE_LABELS:
                continue
            if annotation.get("uncertain") or annotation.get("boundary_ok") is False:
                continue
            if not include_low_confidence and annotation.get("human_confidence") == "low":
                continue
            original = canonical_target_structure_label(
                segment.get("structure_label_candidate")
                or segment.get("songformer_label")
                or segment.get("label")
            )
            features.append(track_matrix[index])
            targets.append(human_label)
            originals.append(original)
            groups.append(str(track["track_id"]))
            records.append(
                {
                    "track_id": track["track_id"],
                    "segment_index": index,
                    "start": segment.get("start"),
                    "end": segment.get("end"),
                    "original": original,
                    "target": human_label,
                }
            )
    if not features:
        return (
            np.zeros((0, len(feature_names()))),
            np.asarray([], dtype=str),
            np.asarray([], dtype=str),
            np.asarray([], dtype=str),
            [],
        )
    return (
        np.vstack(features),
        np.asarray(targets),
        np.asarray(originals),
        np.asarray(groups),
        records,
    )


def fit_classifier(x: np.ndarray, y: np.ndarray, c_value: float):
    scaler = StandardScaler().fit(x)
    classifier = LogisticRegression(
        C=c_value,
        class_weight="balanced",
        max_iter=3000,
        solver="lbfgs",
        random_state=20260831,
    ).fit(scaler.transform(x), y)
    return scaler, classifier


def aligned_probabilities(classifier, values: np.ndarray, labels: list[str]) -> np.ndarray:
    raw = classifier.predict_proba(values)
    aligned = np.zeros((len(values), len(labels)), dtype=np.float64)
    lookup = {label: index for index, label in enumerate(labels)}
    for source_index, label in enumerate(classifier.classes_):
        if label in lookup:
            aligned[:, lookup[label]] = raw[:, source_index]
    return aligned


def gated_predictions(
    probabilities: np.ndarray,
    labels: list[str],
    originals: np.ndarray,
    threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    indices = np.argmax(probabilities, axis=1)
    proposed = np.asarray([labels[index] for index in indices])
    confidence = probabilities[np.arange(len(indices)), indices]
    final = np.where((proposed != originals) & (confidence >= threshold), proposed, originals)
    return final, proposed


def metrics(y: np.ndarray, prediction: np.ndarray, original: np.ndarray) -> dict[str, Any]:
    labels = list(STRUCTURE_LABELS)
    baseline_correct = original == y
    final_correct = prediction == y
    changed = prediction != original
    fixed = (~baseline_correct) & final_correct
    introduced = baseline_correct & (~final_correct)
    return {
        "segment_count": int(len(y)),
        "accuracy": float(accuracy_score(y, prediction)),
        "macro_f1": float(f1_score(y, prediction, labels=labels, average="macro", zero_division=0)),
        "baseline_accuracy": float(accuracy_score(y, original)),
        "baseline_macro_f1": float(f1_score(y, original, labels=labels, average="macro", zero_division=0)),
        "changed_count": int(np.sum(changed)),
        "fixed_errors": int(np.sum(fixed)),
        "introduced_errors": int(np.sum(introduced)),
        "net_gain": int(np.sum(fixed) - np.sum(introduced)),
        "override_precision": float(np.mean(final_correct[changed])) if np.any(changed) else 1.0,
        "confusion_matrix": confusion_matrix(y, prediction, labels=labels).tolist(),
        "labels": labels,
    }


def choose_threshold(
    probabilities: np.ndarray,
    labels: list[str],
    originals: np.ndarray,
    targets: np.ndarray,
    minimum_precision: float,
    minimum_override_count: int,
) -> tuple[float, dict[str, Any]]:
    candidates = [round(value, 2) for value in np.arange(0.50, 0.951, 0.025)] + [1.0]
    scored: list[tuple[tuple[float, ...], float, dict[str, Any]]] = []
    for threshold in candidates:
        prediction, _ = gated_predictions(probabilities, labels, originals, threshold)
        result = metrics(targets, prediction, originals)
        acceptable = result["changed_count"] == 0 or (
            result["changed_count"] >= minimum_override_count
            and result["override_precision"] >= minimum_precision
        )
        score = (
            1.0 if acceptable else 0.0,
            float(result["net_gain"]),
            float(result["macro_f1"]),
            float(result["override_precision"]),
            threshold,
        )
        scored.append((score, threshold, result))
    _, threshold, result = max(scored, key=lambda item: item[0])
    return threshold, result


def cross_validate(
    x: np.ndarray,
    y: np.ndarray,
    originals: np.ndarray,
    groups: np.ndarray,
    *,
    folds: int,
    minimum_precision: float,
    minimum_override_count: int = 10,
) -> tuple[float, float, np.ndarray, dict[str, Any]]:
    labels = sorted(set(y.tolist()))
    unique_groups = len(set(groups.tolist()))
    split_count = min(folds, unique_groups)
    if split_count < 2:
        raise ValueError("at least two independently labelled songs are required")
    splitter = StratifiedGroupKFold(
        n_splits=split_count, shuffle=True, random_state=20260831
    )
    best: tuple[
        tuple[float, float, float, float],
        float,
        float,
        np.ndarray,
        dict[str, Any],
    ] | None = None
    for c_value in (0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0):
        oof = np.zeros((len(y), len(labels)), dtype=np.float64)
        for train_index, validation_index in splitter.split(x, y, groups):
            scaler, classifier = fit_classifier(x[train_index], y[train_index], c_value)
            oof[validation_index] = aligned_probabilities(
                classifier, scaler.transform(x[validation_index]), labels
            )
        threshold, gated_metrics = choose_threshold(
            oof,
            labels,
            originals,
            y,
            minimum_precision,
            minimum_override_count,
        )
        score = (
            float(gated_metrics["net_gain"]),
            float(gated_metrics["macro_f1"]),
            float(gated_metrics["override_precision"]),
            -c_value,
        )
        if best is None or score > best[0]:
            best = (score, c_value, threshold, oof, gated_metrics)
    assert best is not None
    _, c_value, threshold, oof, gated_metrics = best
    return c_value, threshold, oof, {
        "folds": split_count,
        "labels_seen": labels,
        "selected_c": c_value,
        "selected_override_threshold": threshold,
        "minimum_override_precision": minimum_precision,
        "minimum_override_count": minimum_override_count,
        "gated_metrics": gated_metrics,
    }


def export_parameters(classifier) -> tuple[np.ndarray, np.ndarray]:
    coefficients = np.asarray(classifier.coef_, dtype=np.float64)
    intercept = np.asarray(classifier.intercept_, dtype=np.float64)
    if len(classifier.classes_) == 2 and coefficients.shape[0] == 1:
        coefficients = np.vstack([np.zeros_like(coefficients[0]), coefficients[0]])
        intercept = np.asarray([0.0, intercept[0]], dtype=np.float64)
    return coefficients, intercept


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as destination:
        json.dump(payload, destination, ensure_ascii=False, indent=2)
        destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    if not 0.0 <= args.minimum_override_precision <= 1.0:
        raise SystemExit("--minimum-override-precision must be between 0 and 1")
    if args.minimum_override_count < 0:
        raise SystemExit("--minimum-override-count must be non-negative")
    if args.folds < 2:
        raise SystemExit("--folds must be at least 2")
    dataset_path = args.dataset.expanduser().resolve()
    raw_bytes = dataset_path.read_bytes()
    payload = json.loads(raw_bytes)
    try:
        dataset_validation = validate_dataset(
            payload,
            require_complete_splits=(
                () if args.allow_incomplete else ("development",)
            ),
            include_low_confidence=args.include_low_confidence,
        )
    except DatasetValidationError as exc:
        raise SystemExit(f"dataset contract validation failed: {exc}") from exc
    development_progress = review_progress(payload, "development")
    development_complete = review_is_complete(development_progress)
    if not args.allow_incomplete and not development_complete:
        missing = development_progress["total"] - development_progress["reviewed"]
        raise SystemExit(
            f"development annotation is incomplete: {missing} segments still need review; "
            "use --allow-incomplete only for a provisional experiment"
        )
    x, y, originals, groups, records = collect_rows(
        payload, "development", include_low_confidence=args.include_low_confidence
    )
    if len(y) < 20 or len(set(y.tolist())) < 2:
        raise SystemExit("not enough reviewed development segments to train")
    c_value, threshold, oof, cv_report = cross_validate(
        x,
        y,
        originals,
        groups,
        folds=args.folds,
        minimum_precision=args.minimum_override_precision,
        minimum_override_count=args.minimum_override_count,
    )
    scaler, classifier = fit_classifier(x, y, c_value)
    coefficients, intercept = export_parameters(classifier)
    dataset_hash = hashlib.sha256(raw_bytes).hexdigest()
    parameter_hash = hashlib.sha256(coefficients.tobytes() + intercept.tobytes()).hexdigest()
    model_version = f"harbeat_section_relabeler_v1_{parameter_hash[:10]}"
    model_payload = {
        "schema_version": RELABELER_SCHEMA_VERSION,
        "model_version": model_version,
        "training_dataset_sha256": dataset_hash,
        "feature_names": feature_names(),
        "labels": [
            canonical_target_structure_label(value) for value in classifier.classes_
        ],
        "feature_mean": scaler.mean_.tolist(),
        "feature_scale": scaler.scale_.tolist(),
        "coefficients": coefficients.tolist(),
        "intercept": intercept.tolist(),
        "override_threshold": threshold,
        "target_thresholds": {},
        "training_summary": {
            "development_segments": int(len(y)),
            "development_tracks": int(len(set(groups.tolist()))),
            "class_counts": dict(Counter(y.tolist())),
            "selected_c": c_value,
            "cross_validation": cv_report,
        },
    }

    report: dict[str, Any] = {
        "model_version": model_version,
        "dataset": str(dataset_path),
        "dataset_schema_version": dataset_validation["schema_version"],
        "dataset_validation": dataset_validation,
        "development": cv_report,
        "review_progress": {
            "development": development_progress,
            "test": review_progress(payload, "test"),
        },
        "test": {"status": "not_fully_reviewed"},
    }
    test_progress = review_progress(payload, "test")
    if not development_complete:
        report["test"] = {
            "status": "skipped_incomplete_development",
            "reviewed_segments": test_progress["reviewed"],
            "pending_development_segments": (
                development_progress["total"] - development_progress["reviewed"]
            ),
        }
    else:
        test_x, test_y, test_originals, _, test_records = collect_rows(
            payload, "test", include_low_confidence=args.include_low_confidence
        )
    if development_complete and review_is_complete(test_progress) and len(test_y) > 0:
        probabilities = aligned_probabilities(
            classifier, scaler.transform(test_x), list(classifier.classes_)
        )
        prediction, proposed = gated_predictions(
            probabilities, list(classifier.classes_), test_originals, threshold
        )
        test_metrics = metrics(test_y, prediction, test_originals)
        test_metrics["status"] = "evaluated_once"
        test_metrics["reviewed_segments"] = test_progress["reviewed"]
        test_metrics["evaluated_segments"] = int(len(test_y))
        test_metrics["excluded_segments"] = test_progress["total"] - int(len(test_y))
        test_metrics["evaluation_coverage"] = float(len(test_y) / test_progress["total"])
        test_metrics["predictions"] = [
            {
                **record,
                "proposed": str(proposed[index]),
                "final": str(prediction[index]),
                "correct": bool(prediction[index] == test_y[index]),
            }
            for index, record in enumerate(test_records)
        ]
        report["test"] = test_metrics
    elif development_complete and review_is_complete(test_progress):
        report["test"] = {
            "status": "no_evaluable_segments",
            "reviewed_segments": test_progress["reviewed"],
            "evaluated_segments": 0,
            "excluded_segments": test_progress["total"],
            "evaluation_coverage": 0.0,
        }
    elif development_complete:
        report["test"] = {
            "status": "not_fully_reviewed",
            "reviewed_segments": test_progress["reviewed"],
            "pending_segments": test_progress["total"] - test_progress["reviewed"],
        }

    atomic_write_json(args.model_output, model_payload)
    load_relabeler_model(args.model_output)
    atomic_write_json(args.report_output, report)
    print(json.dumps({
        "model": str(args.model_output),
        "report": str(args.report_output),
        "model_version": model_version,
        "development": cv_report["gated_metrics"],
        "test_status": report["test"]["status"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
