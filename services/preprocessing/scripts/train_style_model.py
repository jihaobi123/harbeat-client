#!/usr/bin/env python3
"""Train and cross-validate 13-class reference style prototypes.

All evaluation folds are inherited from the whole-track, artist-grouped split.
Segments are weak observations of a track, never independent split units.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.metrics.pairwise import cosine_distances
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, normalize
from sklearn.svm import LinearSVC


SEED = 20260829
GATES = {
    "macro_f1": 0.45,
    "balanced_accuracy": 0.50,
    "top3_recall": 0.75,
    "fold_macro_f1_std_max": 0.12,
    "class_recall_floor": 0.30,
    "fusion_gain_macro_f1": 0.03,
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def _softmax(scores: np.ndarray) -> np.ndarray:
    scores = np.asarray(scores, dtype=float)
    scores = scores - np.max(scores, axis=1, keepdims=True)
    exponential = np.exp(np.clip(scores, -50.0, 50.0))
    return exponential / np.sum(exponential, axis=1, keepdims=True)


def _sample_weights(rows: list[dict[str, Any]]) -> np.ndarray:
    track_counts = Counter(row["track_id"] for row in rows)
    class_tracks: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        class_tracks[row["primary_style"]].add(row["track_id"])
    weights = np.asarray([
        1.0 / track_counts[row["track_id"]] / len(class_tracks[row["primary_style"]])
        for row in rows
    ], dtype=float)
    return weights / np.mean(weights)


def _aggregate_track_probabilities(
    probabilities: np.ndarray, rows: list[dict[str, Any]], classes: list[str],
) -> tuple[list[str], np.ndarray, dict[str, list[int]]]:
    indices: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        indices[row["track_id"]].append(index)
    track_ids = sorted(indices)
    aggregated = []
    for track_id in track_ids:
        ordered = sorted(indices[track_id], key=lambda index: rows[index]["start_seconds"])
        valid = [index for index in ordered if not rows[index].get("structural_neutral")]
        if len(valid) < 2:
            valid = ordered
        matrix = probabilities[valid]
        top_count = max(1, int(math.ceil(len(matrix) / 2.0)))
        core_proxy = np.mean(np.sort(matrix, axis=0)[-top_count:], axis=0)
        median = np.median(matrix, axis=0)
        if len(matrix) >= 2:
            consecutive = np.max((matrix[:-1] + matrix[1:]) / 2.0, axis=0)
        else:
            consecutive = matrix[0]
        score = 0.60 * core_proxy + 0.25 * median + 0.15 * consecutive
        aggregated.append(score / max(float(np.sum(score)), 1e-12))
    return track_ids, np.stack(aggregated), indices


def _metrics(y_true: list[str], probabilities: np.ndarray, classes: list[str]) -> dict[str, Any]:
    predicted = [classes[index] for index in np.argmax(probabilities, axis=1)]
    precision, recall, f1, support = precision_recall_fscore_support(
        y_true, predicted, labels=classes, zero_division=0,
    )
    top3 = np.argsort(probabilities, axis=1)[:, -3:]
    class_to_index = {label: index for index, label in enumerate(classes)}
    top3_recall = float(np.mean([
        class_to_index[label] in row for label, row in zip(y_true, top3)
    ]))
    return {
        "top1_accuracy": float(accuracy_score(y_true, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predicted)),
        "macro_precision": float(np.mean(precision)),
        "macro_recall": float(np.mean(recall)),
        "macro_f1": float(np.mean(f1)),
        "top3_recall": top3_recall,
        "per_class": {
            label: {
                "precision": float(precision[index]),
                "recall": float(recall[index]),
                "f1": float(f1[index]),
                "support": int(support[index]),
            }
            for index, label in enumerate(classes)
        },
        "confusion_matrix": confusion_matrix(y_true, predicted, labels=classes).tolist(),
    }


def _pipeline(kind: str, n_samples: int, n_features: int) -> Pipeline:
    target_pca = 32 if n_features < 128 else 64
    components = max(1, min(target_pca, n_samples - 1, n_features))
    if kind == "logreg":
        classifier: Any = LogisticRegression(
            C=1.0, max_iter=4000, solver="lbfgs", random_state=SEED,
        )
    elif kind == "svm":
        classifier = LinearSVC(C=0.25, class_weight="balanced", random_state=SEED)
    else:
        raise ValueError(kind)
    return Pipeline([
        ("scaler", StandardScaler()),
        ("pca", PCA(n_components=components, random_state=SEED)),
        ("clf", classifier),
    ])


def _predict(estimator: Pipeline, matrix: np.ndarray, classes: list[str]) -> np.ndarray:
    classifier_classes = list(estimator.named_steps["clf"].classes_)
    if hasattr(estimator, "predict_proba"):
        raw = estimator.predict_proba(matrix)
    else:
        raw = _softmax(estimator.decision_function(matrix))
    output = np.zeros((len(matrix), len(classes)), dtype=float)
    class_to_index = {label: index for index, label in enumerate(classes)}
    for column, label in enumerate(classifier_classes):
        output[:, class_to_index[str(label)]] = raw[:, column]
    return output


def _nearest_probabilities(
    train_matrix: np.ndarray, train_rows: list[dict[str, Any]],
    test_matrix: np.ndarray, classes: list[str],
) -> np.ndarray:
    train_track_ids, train_by_track, _ = _track_vectors(train_matrix, train_rows)
    labels_by_track = {
        row["track_id"]: row["primary_style"] for row in train_rows
    }
    train_labels = [labels_by_track[track_id] for track_id in train_track_ids]
    distances = cosine_distances(normalize(test_matrix), normalize(train_by_track))
    class_distances = np.full((len(test_matrix), len(classes)), 2.0, dtype=float)
    for class_index, label in enumerate(classes):
        columns = [index for index, item in enumerate(train_labels) if item == label]
        class_distances[:, class_index] = np.min(distances[:, columns], axis=1)
    return _softmax(-class_distances / 0.12)


def _track_vectors(matrix: np.ndarray, rows: list[dict[str, Any]]) -> tuple[list[str], np.ndarray, dict[str, list[int]]]:
    indices: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        indices[row["track_id"]].append(index)
    track_ids = sorted(indices)
    vectors = np.stack([np.mean(matrix[indices[track_id]], axis=0) for track_id in track_ids])
    return track_ids, vectors, indices


def _route_matrix(route: str, embeddings: np.ndarray, technical: np.ndarray) -> np.ndarray:
    normalized_embeddings = normalize(embeddings)
    if route == "embedding":
        return normalized_embeddings
    if route == "technical":
        return technical
    if route == "fusion":
        return np.concatenate([normalized_embeddings, technical], axis=1)
    raise ValueError(route)


def _cross_validate(
    name: str,
    matrix: np.ndarray,
    rows: list[dict[str, Any]],
    classes: list[str],
    kind: str,
) -> tuple[dict[str, Any], np.ndarray, list[dict[str, Any]]]:
    folds = sorted({int(row["fold"]) for row in rows})
    oof = np.zeros((len(rows), len(classes)), dtype=float)
    fold_metrics = []
    prediction_rows = []
    label_by_track = {row["track_id"]: row["primary_style"] for row in rows}
    for fold in folds:
        train_indices = [index for index, row in enumerate(rows) if int(row["fold"]) != fold]
        test_indices = [index for index, row in enumerate(rows) if int(row["fold"]) == fold]
        train_rows = [rows[index] for index in train_indices]
        test_rows = [rows[index] for index in test_indices]
        if kind == "nearest":
            segment_probabilities = _nearest_probabilities(
                matrix[train_indices], train_rows, matrix[test_indices], classes,
            )
        else:
            estimator = _pipeline(kind, len(train_indices), matrix.shape[1])
            estimator.fit(
                matrix[train_indices],
                [row["primary_style"] for row in train_rows],
                clf__sample_weight=_sample_weights(train_rows),
            )
            segment_probabilities = _predict(estimator, matrix[test_indices], classes)
        oof[test_indices] = segment_probabilities
        track_ids, track_probabilities, _ = _aggregate_track_probabilities(
            segment_probabilities, test_rows, classes,
        )
        y_true = [label_by_track[track_id] for track_id in track_ids]
        metrics = _metrics(y_true, track_probabilities, classes)
        fold_metrics.append({"fold": fold, "track_count": len(track_ids), **metrics})
        for track_id, expected, probabilities in zip(track_ids, y_true, track_probabilities):
            ranked = np.argsort(probabilities)[::-1]
            prediction_rows.append({
                "model": name,
                "fold": fold,
                "track_id": track_id,
                "expected": expected,
                "predicted": classes[int(ranked[0])],
                "top1_probability": float(probabilities[ranked[0]]),
                "top3": [classes[int(index)] for index in ranked[:3]],
                "probabilities": {label: float(probabilities[index]) for index, label in enumerate(classes)},
            })
    all_track_ids, all_track_probabilities, _ = _aggregate_track_probabilities(oof, rows, classes)
    y_true = [label_by_track[track_id] for track_id in all_track_ids]
    overall = _metrics(y_true, all_track_probabilities, classes)
    fold_macro = [item["macro_f1"] for item in fold_metrics]
    summary = {
        "name": name,
        "kind": kind,
        "folds": fold_metrics,
        "fold_macro_f1_mean": float(np.mean(fold_macro)),
        "fold_macro_f1_std": float(np.std(fold_macro)),
        "overall": overall,
    }
    return summary, oof, prediction_rows


def _write_prediction_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "model", "fold", "track_id", "expected", "predicted",
            "top1_probability", "top3", "probabilities",
        ])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                **row,
                "top3": json.dumps(row["top3"], ensure_ascii=False),
                "probabilities": json.dumps(row["probabilities"], ensure_ascii=False),
            })


def _evaluate_univariate_features(
    technical: np.ndarray,
    feature_names: list[str],
    rows: list[dict[str, Any]],
    classes: list[str],
) -> list[dict[str, Any]]:
    if technical.shape[1] != len(feature_names):
        raise RuntimeError("technical feature schema does not match matrix")
    results = []
    for index, feature_name in enumerate(feature_names):
        summary, _, _ = _cross_validate(
            f"univariate_{feature_name}", technical[:, index : index + 1],
            rows, classes, "logreg",
        )
        metrics = summary["overall"]
        results.append({
            "feature": feature_name,
            "top1_accuracy": metrics["top1_accuracy"],
            "balanced_accuracy": metrics["balanced_accuracy"],
            "macro_f1": metrics["macro_f1"],
            "top3_recall": metrics["top3_recall"],
            "fold_macro_f1_std": summary["fold_macro_f1_std"],
        })
    return sorted(results, key=lambda item: item["macro_f1"], reverse=True)


def _audit_purity(
    rows: list[dict[str, Any]], probabilities: np.ndarray, classes: list[str],
    manifest: list[dict[str, Any]], dataset_dir: Path,
) -> dict[str, Any]:
    class_to_index = {label: index for index, label in enumerate(classes)}
    track_indices: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        track_indices[row["track_id"]].append(index)
    audit: dict[str, dict[str, Any]] = {}
    for track_id, indices in track_indices.items():
        indices.sort(key=lambda index: rows[index]["start_seconds"])
        expected = rows[indices[0]]["primary_style"]
        expected_index = class_to_index[expected]
        switches = []
        previous_prediction = None
        status_weight = Counter()
        total_weight = 0.0
        for index in indices:
            row = rows[index]
            vector = probabilities[index]
            ranking = np.argsort(vector)[::-1]
            predicted_index = int(ranking[0])
            predicted = classes[predicted_index]
            expected_probability = float(vector[expected_index])
            best_probability = float(vector[predicted_index])
            margin = best_probability - expected_probability
            if row.get("structural_neutral") and best_probability < 0.35:
                status = "neutral"
            elif predicted == expected and (expected_probability >= 0.18 or expected_probability - float(vector[ranking[1]]) >= 0.04):
                status = "core"
            elif expected_index in ranking[:3]:
                status = "supporting"
            elif predicted != expected and margin >= 0.12 and best_probability >= 0.20:
                status = "conflicting"
            else:
                status = "supporting"
            duration = float(row["duration_seconds"])
            status_weight[status] += duration
            total_weight += duration
            row.update({
                "purity_status": status,
                "purity_source": "artist_grouped_oof_embedding_consistency_v1",
                "expected_style_probability": round(expected_probability, 6),
                "predicted_style": predicted,
                "predicted_style_probability": round(best_probability, 6),
                "top3_styles": [classes[int(item)] for item in ranking[:3]],
            })
            if (
                previous_prediction is not None
                and predicted != previous_prediction
                and best_probability >= 0.35
            ):
                switches.append({
                    "at_seconds": row["start_seconds"],
                    "from": previous_prediction,
                    "to": predicted,
                    "confidence": round(best_probability, 6),
                })
            previous_prediction = predicted
        coverage = {key: float(status_weight[key] / max(total_weight, 1e-12)) for key in (
            "core", "supporting", "neutral", "conflicting",
        )}
        if coverage["core"] >= 0.70 and coverage["conflicting"] < 0.10:
            grade = "A"
        elif coverage["core"] >= 0.40 and coverage["conflicting"] < 0.30:
            grade = "B"
        else:
            grade = "C"
        audit[track_id] = {
            "purity_grade": grade,
            "core_coverage": coverage["core"],
            "supporting_coverage": coverage["supporting"],
            "neutral_coverage": coverage["neutral"],
            "conflicting_coverage": coverage["conflicting"],
            "style_switch_points": switches,
            "label_purity_source": "model_assisted_not_human_ground_truth",
        }
    for track in manifest:
        if track["track_id"] not in audit:
            continue
        track.update(audit[track["track_id"]])
        track["label_status"] = "model_audited"
    _atomic_jsonl(dataset_dir / "segment_manifest.jsonl", rows)
    _atomic_jsonl(dataset_dir / "manifest.jsonl", manifest)
    with (dataset_dir / "label_audit.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        fields = [
            "track_id", "primary_style", "secondary_styles", "artist", "primary_artist",
            "title", "original_filename", "duration_seconds", "sample_rate", "channels",
            "bitrate", "fold", "label_status", "label_confidence", "purity_grade",
            "core_coverage", "supporting_coverage", "neutral_coverage",
            "conflicting_coverage", "style_switch_points", "risk_flags",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for track in manifest:
            writer.writerow({
                key: json.dumps(track.get(key), ensure_ascii=False)
                if isinstance(track.get(key), (list, dict)) else track.get(key)
                for key in fields
            })
    class_acceptance = {}
    for label in classes:
        selected = [item for item in manifest if item["primary_style"] == label]
        acceptable = sum(item.get("purity_grade") in {"A", "B"} for item in selected)
        class_acceptance[label] = {"a_or_b_tracks": acceptable, "accepted": acceptable >= 3}
    return {
        "tracks": audit,
        "grade_counts": dict(Counter(item["purity_grade"] for item in audit.values())),
        "class_acceptance": class_acceptance,
        "all_classes_have_three_a_or_b": all(item["accepted"] for item in class_acceptance.values()),
        "warning": "OOF consistency is a triage signal, not independent human ground truth.",
    }


def _fit_final(
    name: str, route: str, kind: str, matrix: np.ndarray,
    rows: list[dict[str, Any]], classes: list[str], output: Path,
) -> None:
    estimator = _pipeline(kind, len(rows), matrix.shape[1])
    estimator.fit(
        matrix, [row["primary_style"] for row in rows],
        clf__sample_weight=_sample_weights(rows),
    )
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "version": "style_reference_classifier_v1",
        "name": name,
        "route": route,
        "kind": kind,
        "classes": classes,
        "aggregation": "0.60*top_half_mean+0.25*median+0.15*best_consecutive_pair",
        "estimator": estimator,
    }, output / "model.joblib")


def _write_reports(
    dataset_dir: Path, results: dict[str, dict[str, Any]],
    predictions: list[dict[str, Any]], selected_name: str, classes: list[str],
    gates: dict[str, Any], purity: dict[str, Any],
    univariate: list[dict[str, Any]],
) -> None:
    reports = dataset_dir / "reports"
    reports.mkdir(exist_ok=True)
    metadata = json.loads((dataset_dir / "dataset_metadata.json").read_text(encoding="utf-8"))
    schema = json.loads((dataset_dir / "feature_schema.json").read_text(encoding="utf-8"))
    _write_prediction_csv(reports / "prediction_details.csv", predictions)
    with (reports / "technical_feature_accuracy.csv").open(
        "w", encoding="utf-8-sig", newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "feature", "top1_accuracy", "balanced_accuracy", "macro_f1",
            "top3_recall", "fold_macro_f1_std",
        ])
        writer.writeheader()
        writer.writerows(univariate)
    selected = results[selected_name]["overall"]
    with (reports / "per_class_metrics.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["class", "precision", "recall", "f1", "support"])
        writer.writeheader()
        for label in classes:
            writer.writerow({"class": label, **selected["per_class"][label]})
    try:
        import matplotlib.pyplot as plt

        matrix = np.asarray(selected["confusion_matrix"])
        figure, axis = plt.subplots(figsize=(11, 9))
        image = axis.imshow(matrix, cmap="Blues")
        axis.set_xticks(range(len(classes)), labels=classes, rotation=60, ha="right", fontsize=8)
        axis.set_yticks(range(len(classes)), labels=classes, fontsize=8)
        axis.set_xlabel("Predicted")
        axis.set_ylabel("Reference folder label")
        axis.set_title(f"Artist-grouped OOF confusion matrix: {selected_name}")
        for row in range(len(classes)):
            for column in range(len(classes)):
                axis.text(column, row, str(matrix[row, column]), ha="center", va="center", fontsize=7)
        figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
        figure.tight_layout()
        figure.savefig(reports / "confusion_matrix.png", dpi=180)
        plt.close(figure)
    except ImportError:
        pass
    lines = [
        "# 13 类风格原型：艺人隔离四折验证",
        "",
        f"> 生成时间：{datetime.now(timezone.utc).isoformat()}",
        "> 评价单位为完整歌曲；片段从未跨 Fold。文件名、艺人名和目录路径未进入模型。",
        "",
        "## 路线结果",
        "",
        "| 模型 | Top-1 | Balanced Acc | Macro-F1 | Top-3 | Fold F1 标准差 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, result in sorted(results.items(), key=lambda item: item[1]["overall"]["macro_f1"], reverse=True):
        metrics = result["overall"]
        lines.append(
            f"| `{name}` | {metrics['top1_accuracy']:.3f} | {metrics['balanced_accuracy']:.3f} "
            f"| {metrics['macro_f1']:.3f} | {metrics['top3_recall']:.3f} "
            f"| {result['fold_macro_f1_std']:.3f} |"
        )
    lines.extend([
        "",
        "## 单项技术特征识别力",
        "",
        "> 每行都只输入一个技术特征，仍采用相同的完整歌曲/艺人隔离四折。完整 65 项见 `technical_feature_accuracy.csv`。",
        "",
        "| 特征 | Top-1 | Balanced Acc | Macro-F1 | Top-3 |",
        "|---|---:|---:|---:|---:|",
    ])
    for item in univariate[:15]:
        lines.append(
            f"| `{item['feature']}` | {item['top1_accuracy']:.3f} "
            f"| {item['balanced_accuracy']:.3f} | {item['macro_f1']:.3f} "
            f"| {item['top3_recall']:.3f} |"
        )
    lines.extend([
        "",
        "## 原型门槛",
        "",
        f"- 最佳嵌入模型：`{gates['best_embedding_model']}`；最佳融合模型：`{gates['best_fusion_model']}`。",
        f"- 融合 Macro-F1 增益：{gates['fusion_gain_macro_f1']:.3f}。",
        f"- 总结：**{'通过，可进入扩充数据阶段' if gates['prototype_passed'] else '未通过，不接入运行时'}**。",
        "",
        "| 条件 | 实际 | 是否通过 |",
        "|---|---:|---|",
    ])
    for check in gates["checks"]:
        lines.append(f"| {check['name']} | {check['actual']:.3f} | {'是' if check['passed'] else '否'} |")
    lines.extend([
        "",
        "## 片段纯度审计",
        "",
        f"- A/B/C 数量：{json.dumps(purity['grade_counts'], ensure_ascii=False)}。",
        f"- 每类至少三首 A/B：{'是' if purity['all_classes_have_three_a_or_b'] else '否'}。",
        "- 重要限制：这些状态来自艺人隔离的折外一致性，只适合筛查；仍需人工试听确认冲突片段。",
        "",
    ])
    (reports / "cross_validation.md").write_text("\n".join(lines), encoding="utf-8")
    methodology = [
        "# style_reference_v0 方法与复现路径",
        "",
        "## 数据和隔离",
        "",
        f"- 源 ZIP SHA-256：`{metadata['source_zip_sha256']}`；原文件未修改。",
        f"- {metadata['track_count']} 首、{metadata['class_count']} 类；缺失目标类：{', '.join(metadata['missing_target_styles'])}。",
        "- 使用 StratifiedGroupKFold 四折；group=primary_artist，歌曲及其全部片段继承同一 Fold。",
        "- 文件名、艺人、目录和旧风格规则分数不进入模型矩阵。",
        "",
        "## 切片和输入",
        "",
        "- 首选 Downbeat 对齐的 16 小节窗、8 小节步长；Downbeat 需复核或不稳定时改用 30 秒窗、15 秒步长。",
        f"- 嵌入：Discogs-EffNet，输出 `{schema['embedding']['output']}`，{schema['embedding']['dimension']} 维，模型 SHA-256 `{schema['embedding'].get('model_sha256', 'not_recorded')}`。",
        f"- 技术路线：{schema['technical']['dimension']} 个纯音频连续特征；完整字段见 `feature_schema.json`。",
        "- 片段只是弱观察；最终指标全部按歌曲聚合后计算。",
        "",
        "## 模型和判定",
        "",
        "- 比较嵌入最近邻、嵌入 LogReg/SVM、技术 LogReg/SVM、融合 LogReg/SVM。",
        "- 每折只用训练 Fold 拟合 StandardScaler、PCA 与分类头。",
        "- 单项技术特征也逐一重复同样的艺人隔离四折，结果见 `technical_feature_accuracy.csv`。",
        "- 片段 core/supporting/neutral/conflicting 来自折外一致性筛查，不等同人工真值。",
        "",
        "## 复现命令",
        "",
        "```bash",
        "python scripts/build_style_reference_dataset.py --zip <source.zip> --output-dir <style_reference_v0>",
        "python scripts/extract_style_embeddings.py --dataset-dir <style_reference_v0> --model <discogs-effnet-bs64-1.pb> --resume",
        "python scripts/train_style_model.py --dataset-dir <style_reference_v0>",
        "python scripts/evaluate_style_model.py --dataset-dir <style_reference_v0> --effnet-model <discogs-effnet-bs64-1.pb>",
        "```",
        "",
    ]
    (reports / "methodology.md").write_text("\n".join(methodology), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    args = parser.parse_args()
    dataset_dir = args.dataset_dir.resolve()
    segment_rows = _read_jsonl(dataset_dir / "segment_manifest.jsonl")
    manifest = _read_jsonl(dataset_dir / "manifest.jsonl")
    payload = np.load(dataset_dir / "embeddings" / "segment_features.npz", allow_pickle=False)
    segment_ids = payload["segment_ids"].astype(str).tolist()
    if segment_ids != [row["segment_id"] for row in segment_rows]:
        raise RuntimeError("segment feature order does not match segment manifest")
    if len({row["track_id"] for row in segment_rows}) != len(manifest):
        raise RuntimeError("features are incomplete; every manifest track must be extracted")
    embeddings = np.asarray(payload["embeddings"], dtype=np.float32)
    technical = np.asarray(payload["technical"], dtype=np.float32)
    feature_schema = json.loads((dataset_dir / "feature_schema.json").read_text(encoding="utf-8"))
    technical_names = list(feature_schema["technical"]["names"])
    classes = sorted({row["primary_style"] for row in segment_rows})
    specifications = [
        ("embedding_nearest", "embedding", "nearest"),
        ("embedding_logreg", "embedding", "logreg"),
        ("embedding_svm", "embedding", "svm"),
        ("technical_logreg", "technical", "logreg"),
        ("technical_svm", "technical", "svm"),
        ("fusion_logreg", "fusion", "logreg"),
        ("fusion_svm", "fusion", "svm"),
    ]
    results = {}
    oof = {}
    prediction_rows = []
    for name, route, kind in specifications:
        print(f"training {name}", flush=True)
        matrix = _route_matrix(route, embeddings, technical)
        summary, probabilities, predictions = _cross_validate(
            name, matrix, segment_rows, classes, kind,
        )
        results[name] = summary
        oof[name] = probabilities
        prediction_rows.extend(predictions)
        print(
            f"{name}: macro_f1={summary['overall']['macro_f1']:.3f}, "
            f"top3={summary['overall']['top3_recall']:.3f}", flush=True,
        )
    best_embedding = max(
        (name for name in results if name.startswith("embedding_") and name != "embedding_nearest"),
        key=lambda name: results[name]["overall"]["macro_f1"],
    )
    best_fusion = max(
        (name for name in results if name.startswith("fusion_")),
        key=lambda name: results[name]["overall"]["macro_f1"],
    )
    selected_name = max(results, key=lambda name: results[name]["overall"]["macro_f1"])
    print("evaluating each technical feature independently", flush=True)
    univariate = _evaluate_univariate_features(
        technical, technical_names, segment_rows, classes,
    )
    print(
        f"best individual feature: {univariate[0]['feature']} "
        f"macro_f1={univariate[0]['macro_f1']:.3f}", flush=True,
    )
    purity = _audit_purity(segment_rows, oof[best_embedding], classes, manifest, dataset_dir)
    embedding_metrics = results[best_embedding]["overall"]
    fusion_metrics = results[best_fusion]["overall"]
    fusion_gain = fusion_metrics["macro_f1"] - embedding_metrics["macro_f1"]
    recalled_classes = sum(
        item["recall"] >= GATES["class_recall_floor"]
        for item in fusion_metrics["per_class"].values()
    )
    checks = [
        {"name": "macro_f1", "actual": fusion_metrics["macro_f1"], "passed": fusion_metrics["macro_f1"] >= GATES["macro_f1"]},
        {"name": "balanced_accuracy", "actual": fusion_metrics["balanced_accuracy"], "passed": fusion_metrics["balanced_accuracy"] >= GATES["balanced_accuracy"]},
        {"name": "top3_recall", "actual": fusion_metrics["top3_recall"], "passed": fusion_metrics["top3_recall"] >= GATES["top3_recall"]},
        {"name": "fold_macro_f1_std_max", "actual": results[best_fusion]["fold_macro_f1_std"], "passed": results[best_fusion]["fold_macro_f1_std"] <= GATES["fold_macro_f1_std_max"]},
        {"name": "fraction_classes_recall_ge_0.30", "actual": recalled_classes / len(classes), "passed": recalled_classes >= math.ceil(len(classes) / 2)},
        {"name": "fusion_gain_macro_f1", "actual": fusion_gain, "passed": fusion_gain >= GATES["fusion_gain_macro_f1"]},
    ]
    model_gates_passed = all(check["passed"] for check in checks)
    dataset_metadata = json.loads(
        (dataset_dir / "dataset_metadata.json").read_text(encoding="utf-8")
    )
    gates = {
        "thresholds": GATES,
        "best_embedding_model": best_embedding,
        "best_fusion_model": best_fusion,
        "best_overall_model": selected_name,
        "fusion_gain_macro_f1": fusion_gain,
        "checks": checks,
        "model_gates_passed": model_gates_passed,
        "dataset_screen_passed": purity["all_classes_have_three_a_or_b"],
        "human_label_review_complete": bool(dataset_metadata.get("labels_are_reviewed")),
        "prototype_passed": bool(
            model_gates_passed and purity["all_classes_have_three_a_or_b"]
        ),
        "runtime_integration_allowed": bool(
            model_gates_passed
            and purity["all_classes_have_three_a_or_b"]
            and dataset_metadata.get("labels_are_reviewed")
        ),
    }
    models_dir = dataset_dir / "models"
    best_embedding_kind = results[best_embedding]["kind"]
    best_fusion_kind = results[best_fusion]["kind"]
    _fit_final(
        best_embedding, "embedding", best_embedding_kind,
        _route_matrix("embedding", embeddings, technical), segment_rows, classes,
        models_dir / "embedding_classifier",
    )
    best_technical = max(
        (name for name in results if name.startswith("technical_")),
        key=lambda name: results[name]["overall"]["macro_f1"],
    )
    _fit_final(
        best_technical, "technical", results[best_technical]["kind"],
        _route_matrix("technical", embeddings, technical), segment_rows, classes,
        models_dir / "technical_classifier",
    )
    _fit_final(
        best_fusion, "fusion", best_fusion_kind,
        _route_matrix("fusion", embeddings, technical), segment_rows, classes,
        models_dir / "fusion_classifier",
    )
    _atomic_json(models_dir / "model_card.json", {
        "version": "style_reference_model_card_v1",
        "status": "experimental_not_approved" if not gates["runtime_integration_allowed"] else "approved_prototype",
        "runtime_integration_allowed": gates["runtime_integration_allowed"],
        "tracks": len(manifest),
        "segments": len(segment_rows),
        "classes": classes,
        "missing_target_styles": dataset_metadata.get("missing_target_styles") or [],
        "best_embedding_model": best_embedding,
        "best_fusion_model": best_fusion,
        "gates": gates,
        "known_limitations": [
            "Only five reference tracks per present class.",
            "Eight of the 21 target styles are absent.",
            "Purity grades are model-assisted OOF triage, not human ground truth.",
            "Best route is selected on the same four folds used for reporting; an independent holdout is still required.",
        ],
    })
    np.savez_compressed(
        models_dir / "oof_segment_predictions.npz",
        segment_ids=np.asarray(segment_ids),
        classes=np.asarray(classes),
        **{name: probabilities.astype(np.float32) for name, probabilities in oof.items()},
    )
    _atomic_json(dataset_dir / "reports" / "cross_validation.json", {
        "version": "style_reference_cv_v1",
        "classes": classes,
        "results": results,
        "gates": gates,
        "purity_audit": purity,
        "univariate_technical_features": univariate,
    })
    _write_reports(
        dataset_dir, results, prediction_rows, selected_name, classes, gates,
        purity, univariate,
    )
    print(json.dumps({
        "status": "passed" if gates["prototype_passed"] else "not_passed",
        "best_model": selected_name,
        "best_embedding": best_embedding,
        "best_fusion": best_fusion,
        "gates": gates,
        "purity_grades": purity["grade_counts"],
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
