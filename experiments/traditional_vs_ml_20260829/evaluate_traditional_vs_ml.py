#!/usr/bin/env python3
"""Paired evaluation of the 69-feature rule route against existing ML predictions.

This is an experiment-only evaluator.  It does not alter the production 80% gate.
The main traditional condition keeps features whose recorded held-out accuracy is
strictly greater than 0.50 (continuous features use within-tolerance fraction),
while retaining the current analysis-method compatibility guard.  The sensitivity
condition additionally requires F1 > 0.50 for binary features.
"""
from __future__ import annotations

import copy
import csv
import json
import math
import os
import sys
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import binomtest
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    precision_score,
    recall_score,
)


CLIENT = Path(__file__).resolve().parents[2]
WORKSPACE = Path(os.environ.get("HARBEAT_EXPERIMENT_ROOT", CLIENT.parent)).expanduser().resolve()
DATASET = Path(os.environ.get("HARBEAT_STYLE_DATASET", WORKSPACE / "style_reference_v0"))
EXPERIMENT = Path(os.environ.get("HARBEAT_STYLE_COMPARISON", WORKSPACE / "style_comparison_20260829"))
RAW_ROOT = EXPERIMENT / "traditional_69_by_class"
VALIDATED_ROOT = EXPERIMENT / "traditional_69_by_class_validated_routes"
REPORT_ROOT = EXPERIMENT / "reports"
CALIBRATION_PATH = CLIENT / "config/feature_calibration/v1.json"
MANIFEST_PATH = DATASET / "manifest.jsonl"
ML_PREDICTIONS_PATH = DATASET / "reports/prediction_details.csv"
ML_CV_PATH = DATASET / "reports/cross_validation.json"

CLASSES = [
    "afro_afrobeats", "amapiano", "baile_funk", "boombap", "breakbeat",
    "dancehall", "disco", "funk", "grime_uk_hiphop", "house",
    "jazz_hiphop", "jersey_club", "trap",
]
INITIAL_RAW_CLASSES = {"afro_afrobeats", "amapiano", "baile_funk", "boombap"}
ML_MODELS = ["embedding_logreg", "fusion_svm", "technical_logreg"]
RNG_SEED = 20260829

sys.path.insert(0, str(CLIENT))
from app.modules.library.high_frequency_style_classifier import (  # noqa: E402
    classify_high_frequency_styles,
)
from app.modules.library.high_frequency_style_taxonomy import (  # noqa: E402
    STYLE_DEFINITIONS,
)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def metric_value(entry: dict) -> float | None:
    metrics = entry.get("held_out_metrics") or {}
    if entry.get("validation_mode") == "continuous":
        value = metrics.get("within_tolerance_fraction")
    else:
        value = metrics.get("accuracy")
    return None if value is None else float(value)


def feature_sets() -> tuple[list[str], list[str], list[dict]]:
    calibration = load_json(CALIBRATION_PATH)
    main: list[str] = []
    robust: list[str] = []
    rows: list[dict] = []
    for path, entry in (calibration.get("features") or {}).items():
        metrics = entry.get("held_out_metrics") or {}
        value = metric_value(entry)
        eligible_main = value is not None and value > 0.50
        is_continuous = entry.get("validation_mode") == "continuous"
        f1 = metrics.get("f1")
        eligible_robust = eligible_main and (is_continuous or (f1 is not None and float(f1) > 0.50))
        if eligible_main:
            main.append(path)
        if eligible_robust:
            robust.append(path)
        rows.append({
            "feature": path,
            "validation_mode": "continuous" if is_continuous else "binary",
            "selection_metric": "within_tolerance_fraction" if is_continuous else "accuracy",
            "selection_value": value,
            "f1": None if f1 is None else float(f1),
            "sample_count": metrics.get("sample_count"),
            "calibration_status": entry.get("status"),
            "main_accuracy_gt_0_50": eligible_main,
            "sensitivity_accuracy_and_f1_gt_0_50": eligible_robust,
        })
    return sorted(main), sorted(robust), rows


def load_manifest() -> dict[str, dict]:
    records = {}
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            records[item["track_id"]] = item
    return records


def load_tracks() -> tuple[dict[str, dict], list[dict]]:
    tracks: dict[str, dict] = {}
    audit: list[dict] = []
    for expected in CLASSES:
        parent = RAW_ROOT if expected in INITIAL_RAW_CLASSES else VALIDATED_ROOT
        result_path = parent / expected / "results.json"
        if not result_path.is_file():
            raise RuntimeError(f"missing result file: {result_path}")
        payload = load_json(result_path)
        completed = [item for item in payload.get("tracks", []) if item.get("status") == "completed"]
        if len(completed) != 5:
            raise RuntimeError(f"{expected}: expected 5 completed tracks, got {len(completed)}")
        for item in completed:
            track_id = Path(item["file"]).stem
            feature_analysis = (((item.get("stem_analysis") or {}).get("feature_analysis")) or {})
            routes = (((feature_analysis.get("model_evidence") or {}).get("routes")) or {})
            route_status = {
                key: ((routes.get(key) or {}).get("status"))
                for key in ("drum_transcription", "bass_transcription", "chord_transcription", "style_tags")
            }
            valid = (
                route_status["drum_transcription"] == "ready"
                and route_status["bass_transcription"] == "ready"
                and route_status["chord_transcription"] == "ready"
                and route_status["style_tags"] == "disabled"
            )
            audit.append({"track_id": track_id, "expected": expected, **route_status, "valid": valid})
            if not valid:
                raise RuntimeError(f"invalid route audit for {track_id}: {route_status}")
            if track_id in tracks:
                raise RuntimeError(f"duplicate track id: {track_id}")
            tracks[track_id] = item
    if len(tracks) != 65:
        raise RuntimeError(f"expected 65 unique tracks, got {len(tracks)}")
    return tracks, audit


def complete_feature_inventory(tracks: dict[str, dict], calibrated_rows: list[dict]) -> list[dict]:
    calibrated = {row["feature"]: row for row in calibrated_rows}
    observed_sets: list[set[str]] = []
    for item in tracks.values():
        groups = ((((item.get("stem_analysis") or {}).get("feature_analysis") or {}).get("feature_groups")) or {})
        observed_sets.append({
            f"{group}.{name}"
            for group, features in groups.items() if isinstance(features, dict)
            for name in features
        })
    universe = set().union(*observed_sets)
    if len(universe) != 69 or any(paths != universe for paths in observed_sets):
        raise RuntimeError(
            f"high-level feature inventory is not a consistent 69 paths: union={len(universe)}"
        )
    rows = []
    for path in sorted(universe):
        if path in calibrated:
            rows.append(calibrated[path])
        else:
            rows.append({
                "feature": path,
                "validation_mode": None,
                "selection_metric": None,
                "selection_value": None,
                "f1": None,
                "sample_count": None,
                "calibration_status": "no_heldout_accuracy_record",
                "main_accuracy_gt_0_50": False,
                "sensitivity_accuracy_and_f1_gt_0_50": False,
            })
    return rows


def unavailable_copy(feature: dict) -> dict:
    value = copy.deepcopy(feature)
    value.update({
        "availability": "unavailable",
        "detected": None,
        "score": None,
        "probability": None,
        "decision": "unknown",
        "style_required_allowed": False,
    })
    return value


def filter_features(source: dict, allowed: set[str] | None, *, guard_method: bool) -> tuple[dict, dict]:
    """Return filtered feature analysis and per-track selection audit.

    ``allowed=None`` is the raw all-69 diagnostic.  For thresholded conditions,
    a whitelisted feature still becomes unavailable if the emitted method does
    not match the method used by its accuracy record.
    """
    # Keep only fields consumed by the rule classifier; raw transcription events
    # make the source JSON very large and are irrelevant to this comparison.
    result = {
        "status": source.get("status"),
        "music_context": {"bpm": ((source.get("music_context") or {}).get("bpm"))},
        "feature_groups": {},
        "model_evidence": {
            "routes": {
                "style_tags": {"status": "disabled", "engine": "disabled_for_pure_traditional_test"},
                "instrument_tags": {"status": "disabled", "engine": "disabled_for_pure_traditional_test"},
            }
        },
    }
    for group, features in (source.get("feature_groups") or {}).items():
        if not isinstance(features, dict):
            continue
        result["feature_groups"][group] = {
            name: {
                key: copy.deepcopy(feature.get(key))
                for key in (
                    "availability", "detected", "score", "confidence", "reliability",
                    "quality", "evidence_level", "time_ranges", "calibration_method_supported",
                )
                if key in feature
            }
            if isinstance(feature, dict) else feature
            for name, feature in features.items()
        }
    groups = result.get("feature_groups") or {}
    retained: list[str] = []
    method_mismatch: list[str] = []
    for group, features in groups.items():
        if not isinstance(features, dict):
            continue
        for name, feature in list(features.items()):
            if not isinstance(feature, dict):
                continue
            path = f"{group}.{name}"
            method_ok = feature.get("calibration_method_supported") is not False
            keep = allowed is None or path in allowed
            if guard_method and keep and not method_ok:
                keep = False
                method_mismatch.append(path)
            if keep:
                retained.append(path)
            else:
                features[name] = unavailable_copy(feature)
    return result, {
        "retained": sorted(retained),
        "method_mismatch": sorted(set(method_mismatch)),
    }


def prediction_from_analysis(analysis: dict, closed_classes: set[str]) -> dict:
    styles = analysis.get("styles") or []
    ranked_all = [item["style_id"] for item in styles]
    ranked_closed = [style for style in ranked_all if style in closed_classes]
    primary = analysis.get("primary_style") or {}
    return {
        "open21_top1": ranked_all[0] if ranked_all else None,
        "open21_top3": ranked_all[:3],
        "closed13_top1": ranked_closed[0] if ranked_closed else None,
        "closed13_top3": ranked_closed[:3],
        "strict_primary": primary.get("style_id"),
        "abstained": not bool(primary.get("style_id")),
        "top_score": ((analysis.get("primary_style_candidate") or {}).get("score")),
        "status": analysis.get("status"),
        "review_reasons": analysis.get("review_reasons") or [],
    }


def classification_metrics(expected: list[str], predicted: list[str | None]) -> dict:
    sentinel = "__abstain__"
    pred = [value if value is not None else sentinel for value in predicted]
    correct_count = sum(truth == guess for truth, guess in zip(expected, pred))
    return {
        "correct_count": correct_count,
        "top1_accuracy": float(accuracy_score(expected, pred)),
        "balanced_accuracy": float(balanced_accuracy_score(expected, pred)),
        "macro_precision": float(precision_score(expected, pred, labels=CLASSES, average="macro", zero_division=0)),
        "macro_recall": float(recall_score(expected, pred, labels=CLASSES, average="macro", zero_division=0)),
        "macro_f1": float(f1_score(expected, pred, labels=CLASSES, average="macro", zero_division=0)),
        "abstention_rate": float(sum(value is None for value in predicted) / len(predicted)),
        "exact_one_sided_pvalue_vs_uniform_1_of_13": float(
            binomtest(correct_count, len(expected), 1.0 / len(CLASSES), alternative="greater").pvalue
        ),
    }


def per_class_metrics(expected: list[str], predicted: list[str | None]) -> list[dict]:
    pred = [value if value is not None else "__abstain__" for value in predicted]
    precision, recall, f1, support = precision_recall_fscore_support(
        expected, pred, labels=CLASSES, zero_division=0,
    )
    return [
        {
            "class": label,
            "precision": float(precision[i]),
            "recall": float(recall[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
        for i, label in enumerate(CLASSES)
    ]


def bootstrap_difference(
    rows: list[dict], traditional_key: str, ml_key: str, *, iterations: int = 10000,
) -> dict:
    rng = np.random.default_rng(RNG_SEED)
    by_class = {label: [i for i, row in enumerate(rows) if row["expected"] == label] for label in CLASSES}
    expected = np.asarray([row["expected"] for row in rows], dtype=object)
    traditional = np.asarray([row[traditional_key] for row in rows], dtype=object)
    ml = np.asarray([row[ml_key] for row in rows], dtype=object)

    def values(indices: np.ndarray) -> tuple[float, float]:
        y = expected[indices].tolist()
        a = traditional[indices].tolist()
        b = ml[indices].tolist()
        return (
            float(accuracy_score(y, b) - accuracy_score(y, a)),
            float(
                f1_score(y, b, labels=CLASSES, average="macro", zero_division=0)
                - f1_score(y, a, labels=CLASSES, average="macro", zero_division=0)
            ),
        )

    diffs = np.empty((iterations, 2), dtype=float)
    for iteration in range(iterations):
        sampled = np.concatenate([
            rng.choice(indices, size=len(indices), replace=True)
            for indices in by_class.values()
        ])
        diffs[iteration] = values(sampled)
    point = values(np.arange(len(rows)))
    return {
        "direction": "ml_minus_traditional",
        "iterations": iterations,
        "seed": RNG_SEED,
        "accuracy_difference": point[0],
        "accuracy_95ci": np.quantile(diffs[:, 0], [0.025, 0.975]).tolist(),
        "macro_f1_difference": point[1],
        "macro_f1_95ci": np.quantile(diffs[:, 1], [0.025, 0.975]).tolist(),
    }


def mcnemar(rows: list[dict], traditional_key: str, ml_key: str) -> dict:
    traditional_only = 0
    ml_only = 0
    both_correct = 0
    both_wrong = 0
    for row in rows:
        truth = row["expected"]
        trad_ok = row[traditional_key] == truth
        ml_ok = row[ml_key] == truth
        if trad_ok and ml_ok:
            both_correct += 1
        elif trad_ok:
            traditional_only += 1
        elif ml_ok:
            ml_only += 1
        else:
            both_wrong += 1
    discordant = traditional_only + ml_only
    pvalue = 1.0 if discordant == 0 else float(binomtest(min(traditional_only, ml_only), discordant, 0.5).pvalue)
    return {
        "both_correct": both_correct,
        "traditional_only_correct": traditional_only,
        "ml_only_correct": ml_only,
        "both_wrong": both_wrong,
        "discordant_pairs": discordant,
        "exact_two_sided_pvalue": pvalue,
    }


def load_ml_predictions() -> dict[str, dict[str, dict]]:
    result: dict[str, dict[str, dict]] = {name: {} for name in ML_MODELS}
    with ML_PREDICTIONS_PATH.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            model = row["model"]
            if model not in result:
                continue
            result[model][row["track_id"]] = {
                "predicted": row["predicted"],
                "top3": json.loads(row["top3"]),
                "top1_probability": float(row["top1_probability"]),
                "fold": int(row["fold"]),
            }
    for model, values in result.items():
        if len(values) != 65:
            raise RuntimeError(f"{model}: expected 65 predictions, got {len(values)}")
    return result


def style_rule_coverage(allowed: set[str]) -> list[dict]:
    rows = []
    for style, rule in STYLE_DEFINITIONS.items():
        positive = rule.get("positive") or {}
        total_weight = float(sum(positive.values()))
        retained_weight = float(sum(weight for path, weight in positive.items() if path in allowed))
        required = rule.get("required_any") or []
        satisfiable = sum(any(path in allowed for path in alternatives) for alternatives in required)
        rows.append({
            "style": style,
            "in_test_13": style in CLASSES,
            "positive_rule_feature_count": len(positive),
            "retained_positive_feature_count": sum(path in allowed for path in positive),
            "retained_positive_weight_fraction": retained_weight / total_weight if total_weight else 0.0,
            "required_groups": len(required),
            "satisfiable_required_groups": satisfiable,
            "all_required_groups_satisfiable": satisfiable == len(required),
        })
    return rows


def taxonomy_feature_paths() -> set[str]:
    paths: set[str] = set()
    for rule in STYLE_DEFINITIONS.values():
        paths.update((rule.get("positive") or {}).keys())
        paths.update((rule.get("negative") or {}).keys())
        for alternatives in rule.get("required_any") or []:
            paths.update(alternatives)
    return paths


def save_confusion(expected: list[str], predicted: list[str | None], path: Path, title: str) -> None:
    pred = [value if value is not None else "__abstain__" for value in predicted]
    matrix = confusion_matrix(expected, pred, labels=CLASSES)
    fig, ax = plt.subplots(figsize=(11, 9))
    image = ax.imshow(matrix, cmap="Blues", vmin=0, vmax=5)
    ax.set_xticks(range(len(CLASSES)), CLASSES, rotation=55, ha="right", fontsize=8)
    ax.set_yticks(range(len(CLASSES)), CLASSES, fontsize=8)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Expected")
    ax.set_title(title)
    for i in range(len(CLASSES)):
        for j in range(len(CLASSES)):
            value = int(matrix[i, j])
            if value:
                ax.text(j, i, str(value), ha="center", va="center", fontsize=8,
                        color="white" if value >= 3 else "black")
    fig.colorbar(image, ax=ax, shrink=0.75)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def save_comparison_chart(summary: dict[str, dict], path: Path) -> None:
    names = list(summary)
    accuracy = [summary[name]["top1_accuracy"] for name in names]
    macro_f1 = [summary[name]["macro_f1"] for name in names]
    x = np.arange(len(names))
    width = 0.36
    fig, ax = plt.subplots(figsize=(11, 5.8))
    bars1 = ax.bar(x - width / 2, accuracy, width, label="Top-1 accuracy")
    bars2 = ax.bar(x + width / 2, macro_f1, width, label="Macro-F1")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Score")
    ax.set_xticks(x, names, rotation=25, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    for bars in (bars1, bars2):
        ax.bar_label(bars, labels=[f"{bar.get_height():.3f}" for bar in bars], padding=3, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> None:
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()
    if len(manifest) != 65:
        raise RuntimeError(f"manifest must contain 65 tracks, got {len(manifest)}")
    tracks, route_audit = load_tracks()
    main_features, robust_features, calibrated_feature_rows = feature_sets()
    feature_rows = complete_feature_inventory(tracks, calibrated_feature_rows)
    if len(main_features) != 19 or len(robust_features) != 15:
        raise RuntimeError(
            f"unexpected feature-set sizes: main={len(main_features)}, robust={len(robust_features)}"
        )
    ml = load_ml_predictions()
    conditions = {
        "traditional_literal_acc_gt_0_50": (set(main_features), False),
        "traditional_acc_gt_0_50": (set(main_features), True),
        "traditional_acc_and_f1_gt_0_50": (set(robust_features), True),
        "traditional_all69_raw_diagnostic": (None, False),
    }
    rows = []
    feature_use_audit = []
    for track_id in sorted(tracks):
        item = tracks[track_id]
        truth = manifest[track_id]["primary_style"]
        source = ((item.get("stem_analysis") or {}).get("feature_analysis")) or {}
        row = {
            "track_id": track_id,
            "expected": truth,
            "artist": manifest[track_id].get("artist"),
            "title": manifest[track_id].get("title"),
            "purity_grade": manifest[track_id].get("purity_grade"),
            "elapsed_sec": item.get("elapsed_sec"),
        }
        for condition, (allowed, method_guard) in conditions.items():
            filtered, audit = filter_features(source, allowed, guard_method=method_guard)
            analysis = classify_high_frequency_styles(filtered)
            prediction = prediction_from_analysis(analysis, set(CLASSES))
            for key, value in prediction.items():
                row[f"{condition}__{key}"] = value
            feature_use_audit.append({
                "track_id": track_id,
                "condition": condition,
                "retained_count": len(audit["retained"]),
                "retained": audit["retained"],
                "method_mismatch": audit["method_mismatch"],
            })
        for model in ML_MODELS:
            pred = ml[model][track_id]
            row[f"{model}__top1"] = pred["predicted"]
            row[f"{model}__top3"] = pred["top3"]
            row[f"{model}__probability"] = pred["top1_probability"]
            row[f"{model}__fold"] = pred["fold"]
        rows.append(row)

    expected = [row["expected"] for row in rows]
    summary: dict[str, dict] = {}
    for condition in conditions:
        closed_key = f"{condition}__closed13_top1"
        open_key = f"{condition}__open21_top1"
        strict_key = f"{condition}__strict_primary"
        values = [row[closed_key] for row in rows]
        result = classification_metrics(expected, values)
        result["closed13_top3_recall"] = float(np.mean([
            row["expected"] in row[f"{condition}__closed13_top3"] for row in rows
        ]))
        result["open21_top1_accuracy"] = float(np.mean([row[open_key] == row["expected"] for row in rows]))
        result["open21_top3_recall"] = float(np.mean([
            row["expected"] in row[f"{condition}__open21_top3"] for row in rows
        ]))
        result["strict_primary_accuracy"] = float(np.mean([row[strict_key] == row["expected"] for row in rows]))
        result["strict_primary_abstention_rate"] = float(np.mean([row[strict_key] is None for row in rows]))
        result["per_class"] = per_class_metrics(expected, values)
        summary[condition] = result
    cv = load_json(ML_CV_PATH)
    for model in ML_MODELS:
        values = [row[f"{model}__top1"] for row in rows]
        result = classification_metrics(expected, values)
        result["closed13_top3_recall"] = float(np.mean([
            row["expected"] in row[f"{model}__top3"] for row in rows
        ]))
        result["per_class"] = per_class_metrics(expected, values)
        result["reported_cv_overall"] = cv["results"][model]["overall"]
        summary[model] = result

    main_key = "traditional_acc_gt_0_50__closed13_top1"
    paired = {}
    for model in ("embedding_logreg", "fusion_svm"):
        ml_key = f"{model}__top1"
        paired[model] = {
            "mcnemar": mcnemar(rows, main_key, ml_key),
            "stratified_bootstrap": bootstrap_difference(rows, main_key, ml_key),
        }

    confusion_labels = CLASSES
    for name, prediction_key in {
        "traditional_acc_gt_0_50": main_key,
        "embedding_logreg": "embedding_logreg__top1",
        "fusion_svm": "fusion_svm__top1",
    }.items():
        save_confusion(
            expected,
            [row[prediction_key] for row in rows],
            REPORT_ROOT / f"confusion_{name}.png",
            f"{name} — 13-class paired evaluation",
        )
    save_comparison_chart(
        {
            "Traditional literal >50%": summary["traditional_literal_acc_gt_0_50"],
            "Traditional >50% + method guard": summary["traditional_acc_gt_0_50"],
            "Traditional acc+F1 >50%": summary["traditional_acc_and_f1_gt_0_50"],
            "Raw all-69 diagnostic": summary["traditional_all69_raw_diagnostic"],
            "Technical-65 ML": summary["technical_logreg"],
            "Embedding ML": summary["embedding_logreg"],
            "Fusion ML": summary["fusion_svm"],
        },
        REPORT_ROOT / "method_comparison.png",
    )

    elapsed = [float(row["elapsed_sec"]) for row in rows if row.get("elapsed_sec") is not None]
    taxonomy_paths = taxonomy_feature_paths()
    mismatch_counts = Counter(
        path
        for audit in feature_use_audit
        if audit["condition"] == "traditional_acc_gt_0_50"
        for path in audit["method_mismatch"]
    )
    output = {
        "version": "traditional_69_vs_ml_paired_v1",
        "dataset": {
            "track_count": len(rows),
            "class_count_present": len(CLASSES),
            "songs_per_class": dict(Counter(expected)),
            "taxonomy_target_count": len(STYLE_DEFINITIONS),
            "missing_taxonomy_classes": sorted(set(STYLE_DEFINITIONS) - set(CLASSES)),
            "label_source": "folder_label_user_reference_library",
        },
        "traditional_feature_policy": {
            "registered_high_level_feature_count": 69,
            "main_eligible_count": len(main_features),
            "main_eligible": main_features,
            "main_features_referenced_by_taxonomy_count": len(set(main_features) & taxonomy_paths),
            "main_features_not_referenced_by_taxonomy": sorted(set(main_features) - taxonomy_paths),
            "sensitivity_eligible_count": len(robust_features),
            "sensitivity_eligible": robust_features,
            "bpm_context_outside_69": True,
            "style_tag_ml_disabled": True,
            "analysis_method_compatibility_guard": True,
            "method_mismatch_track_counts": dict(mismatch_counts),
            "production_80_percent_gate_changed": False,
        },
        "route_audit": {
            "all_65_valid": all(item["valid"] for item in route_audit),
            "records": route_audit,
        },
        "runtime": {
            "traditional_elapsed_sec_sum": float(sum(elapsed)),
            "traditional_elapsed_sec_mean": float(np.mean(elapsed)),
            "traditional_elapsed_sec_median": float(np.median(elapsed)),
            "ml_runtime_not_comparable": True,
        },
        "metrics": summary,
        "paired_tests": paired,
        "rule_coverage_main": style_rule_coverage(set(main_features)),
        "rule_coverage_sensitivity": style_rule_coverage(set(robust_features)),
    }
    write_json(REPORT_ROOT / "comparison_metrics.json", output)
    write_json(REPORT_ROOT / "per_track_predictions.json", rows)
    write_json(REPORT_ROOT / "feature_use_audit.json", feature_use_audit)
    write_json(REPORT_ROOT / "feature_selection.json", feature_rows)

    # Flat CSVs for direct review.
    flat_fields = [
        "track_id", "expected", "artist", "title", "purity_grade", "elapsed_sec",
        "traditional_acc_gt_0_50__open21_top1",
        "traditional_acc_gt_0_50__closed13_top1",
        "traditional_acc_gt_0_50__strict_primary",
        "traditional_acc_gt_0_50__abstained",
        "traditional_acc_and_f1_gt_0_50__closed13_top1",
        "traditional_literal_acc_gt_0_50__closed13_top1",
        "traditional_all69_raw_diagnostic__closed13_top1",
        "technical_logreg__top1", "embedding_logreg__top1", "fusion_svm__top1",
    ]
    with (REPORT_ROOT / "per_track_predictions.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=flat_fields)
        writer.writeheader()
        writer.writerows([{key: row.get(key) for key in flat_fields} for row in rows])
    with (REPORT_ROOT / "feature_selection.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(feature_rows[0]))
        writer.writeheader()
        writer.writerows(feature_rows)
    with (REPORT_ROOT / "per_class_metrics.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = ["method", "class", "precision", "recall", "f1", "support"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for method, metrics in summary.items():
            for class_row in metrics["per_class"]:
                writer.writerow({"method": method, **class_row})
    print(json.dumps({
        "report_root": str(REPORT_ROOT),
        "main_feature_count": len(main_features),
        "robust_feature_count": len(robust_features),
        "metrics": {
            name: {
                "top1_accuracy": value["top1_accuracy"],
                "macro_f1": value["macro_f1"],
                "top3": value.get("closed13_top3_recall"),
            }
            for name, value in summary.items()
        },
        "paired_tests": paired,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
