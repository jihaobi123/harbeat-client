#!/usr/bin/env python3
"""Run leakage, shuffle and audio-perturbation checks for style_reference_v0."""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import joblib
import numpy as np
from sklearn.preprocessing import normalize

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.extract_style_embeddings import SAMPLE_RATE, _embedding_frames, _load_audio
from scripts.train_style_model import _cross_validate, _predict, _read_jsonl


SEED = 20260829


def _atomic_json(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _leakage_checks(
    manifest: list[dict[str, Any]], segments: list[dict[str, Any]],
    feature_schema: dict[str, Any],
) -> dict[str, Any]:
    track_by_id = {track["track_id"]: track for track in manifest}
    segment_fold_mismatches = [
        row["segment_id"] for row in segments
        if int(row["fold"]) != int(track_by_id[row["track_id"]]["fold"])
    ]
    artist_fold_map: dict[str, set[int]] = {}
    for track in manifest:
        artist_fold_map.setdefault(track["artist_group"], set()).add(int(track["fold"]))
    leaked_artists = {
        artist: sorted(folds) for artist, folds in artist_fold_map.items() if len(folds) > 1
    }
    technical_names = set(feature_schema["technical"]["names"])
    forbidden = {"artist", "title", "filename", "folder", "path", "style_score", "old_style"}
    forbidden_features = sorted(
        name for name in technical_names if any(token in name.casefold() for token in forbidden)
    )
    return {
        "segment_fold_mismatch_count": len(segment_fold_mismatches),
        "artist_groups_crossing_folds": leaked_artists,
        "forbidden_model_features": forbidden_features,
        "passed": not segment_fold_mismatches and not leaked_artists and not forbidden_features,
    }


def _external_audit_summary(dataset_dir: Path) -> dict[str, Any]:
    cache_dir = dataset_dir / "external" / "musicbrainz"
    rows = []
    if cache_dir.is_dir():
        for path in sorted(cache_dir.glob("*.json")):
            rows.append(json.loads(path.read_text(encoding="utf-8")))
    return {
        "tracks": len(rows),
        "statuses": dict(Counter(row.get("status", "unknown") for row in rows)),
        "tagged_tracks": sum(bool(row.get("external_labels")) for row in rows),
        "interpretation": "Identity/tag triage only; miss or absent tags are not treated as label conflicts.",
    }


def _subgroup_summary(
    dataset_dir: Path,
    manifest: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    model_name: str,
) -> dict[str, Any]:
    track_by_id = {track["track_id"]: track for track in manifest}
    method_by_track = {}
    for row in segments:
        method_by_track[row["track_id"]] = row["window_method"]
    with (dataset_dir / "reports" / "prediction_details.csv").open(
        "r", encoding="utf-8-sig", newline="",
    ) as handle:
        predictions = [
            row for row in csv.DictReader(handle) if row["model"] == model_name
        ]
    dimensions = {
        "window_method": lambda track_id: method_by_track[track_id],
        "purity_grade": lambda track_id: track_by_id[track_id].get("purity_grade") or "unreviewed",
        "fold": lambda track_id: f"fold_{track_by_id[track_id]['fold']}",
    }
    groups = {}
    for dimension, resolve in dimensions.items():
        selected: dict[str, list[dict[str, str]]] = {}
        for row in predictions:
            selected.setdefault(str(resolve(row["track_id"])), []).append(row)
        groups[dimension] = {
            name: {
                "tracks": len(items),
                "top1_accuracy": float(np.mean([
                    item["expected"] == item["predicted"] for item in items
                ])),
            }
            for name, items in selected.items()
        }
    confusion_pairs = Counter(
        f"{row['expected']} -> {row['predicted']}"
        for row in predictions if row["expected"] != row["predicted"]
    )
    return {
        "model": model_name,
        "groups": groups,
        "confusion_pairs": dict(confusion_pairs.most_common()),
    }


def _write_review_queue(
    dataset_dir: Path,
    manifest: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> None:
    method_by_track = {}
    for row in segments:
        method_by_track[row["track_id"]] = row["window_method"]
    external_by_track = {}
    cache_dir = dataset_dir / "external" / "musicbrainz"
    if cache_dir.is_dir():
        for path in cache_dir.glob("*.json"):
            item = json.loads(path.read_text(encoding="utf-8"))
            external_by_track[item["track_id"]] = item
    rows = []
    for track in manifest:
        reasons = []
        if track.get("purity_grade") == "C":
            reasons.append("model_assisted_grade_C")
        if track.get("purity_grade") == "B":
            reasons.append("model_assisted_grade_B")
        if track.get("style_switch_points"):
            reasons.append("possible_style_switch")
        if "version_or_remix_name" in (track.get("risk_flags") or []):
            reasons.append("version_or_remix_name")
        external = external_by_track.get(track["track_id"], {})
        if external.get("status") in {"miss", "error", "identity_needs_review"}:
            reasons.append(f"musicbrainz_{external.get('status')}")
        if not reasons:
            continue
        rows.append({
            "priority": 1 if track.get("purity_grade") == "C" else 2,
            "track_id": track["track_id"],
            "primary_style": track["primary_style"],
            "artist": track["artist"],
            "title": track["title"],
            "purity_grade": track.get("purity_grade"),
            "core_coverage": track.get("core_coverage"),
            "conflicting_coverage": track.get("conflicting_coverage"),
            "window_method": method_by_track.get(track["track_id"]),
            "possible_switch_points": track.get("style_switch_points") or [],
            "external_status": external.get("status"),
            "review_reasons": reasons,
        })
    rows.sort(key=lambda row: (row["priority"], row["primary_style"], row["artist"], row["title"]))
    with (dataset_dir / "reports" / "manual_review_queue.csv").open(
        "w", encoding="utf-8-sig", newline="",
    ) as handle:
        fields = list(rows[0]) if rows else ["track_id"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, (list, dict)) else value
                for key, value in row.items()
            })


def _shuffle_test(
    embeddings: np.ndarray, rows: list[dict[str, Any]], classes: list[str], repetitions: int,
) -> dict[str, Any]:
    rng = np.random.default_rng(SEED)
    track_ids = sorted({row["track_id"] for row in rows})
    labels_by_track = {
        track_id: next(row["primary_style"] for row in rows if row["track_id"] == track_id)
        for track_id in track_ids
    }
    original_labels = np.asarray([labels_by_track[track_id] for track_id in track_ids])
    matrix = normalize(embeddings)
    scores = []
    errors = []
    for repetition in range(repetitions):
        shuffled = original_labels.copy()
        rng.shuffle(shuffled)
        label_map = dict(zip(track_ids, shuffled.tolist()))
        cooked_rows = deepcopy(rows)
        for row in cooked_rows:
            row["primary_style"] = label_map[row["track_id"]]
        try:
            summary, _, _ = _cross_validate(
                f"label_shuffle_{repetition}", matrix, cooked_rows, classes, "logreg",
            )
            scores.append(summary["overall"]["macro_f1"])
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    return {
        "repetitions": repetitions,
        "completed": len(scores),
        "macro_f1_values": scores,
        "macro_f1_mean": float(np.mean(scores)) if scores else None,
        "macro_f1_std": float(np.std(scores)) if scores else None,
        "chance_top1": 1.0 / len(classes),
        "errors": errors,
    }


def _mean_embedding(predictor: Any, audio: np.ndarray) -> np.ndarray:
    return np.mean(_embedding_frames(predictor, audio), axis=0).astype(np.float32)


def _prediction(estimator_payload: dict[str, Any], embedding: np.ndarray) -> np.ndarray:
    matrix = normalize(embedding.reshape(1, -1))
    return _predict(
        estimator_payload["estimator"], matrix, list(estimator_payload["classes"]),
    )[0]


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    return float(np.dot(left, right) / denominator) if denominator else 0.0


def _write_wav(path: Path, audio: np.ndarray) -> None:
    import soundfile as sf

    sf.write(path, audio, SAMPLE_RATE, subtype="PCM_16")


def _audio_robustness(
    manifest: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    model_path: Path,
    effnet_model: Path,
) -> dict[str, Any]:
    import essentia.standard as es

    payload = joblib.load(model_path)
    classes = list(payload["classes"])
    predictor = es.TensorflowPredictEffnetDiscogs(
        graphFilename=str(effnet_model), output="PartitionedCall:1",
    )
    first_by_class = {}
    track_by_id = {track["track_id"]: track for track in manifest}
    for row in segments:
        first_by_class.setdefault(row["primary_style"], row)
    records = []
    ffmpeg = shutil.which("ffmpeg")
    for label, row in sorted(first_by_class.items()):
        track = track_by_id[row["track_id"]]
        full_audio = _load_audio(Path(track["audio_path"]))
        start = int(round(float(row["start_seconds"]) * SAMPLE_RATE))
        end = int(round(float(row["end_seconds"]) * SAMPLE_RATE))
        baseline_audio = full_audio[start:min(end, full_audio.size)]
        baseline_embedding = _mean_embedding(predictor, baseline_audio)
        baseline_probability = _prediction(payload, baseline_embedding)
        variants: dict[str, np.ndarray] = {
            "loudness_minus_6db": np.clip(baseline_audio * 0.501187, -1.0, 1.0),
        }
        shift = int(round(2.0 * SAMPLE_RATE))
        shifted_end = min(full_audio.size, end + shift)
        shifted_start = max(0, shifted_end - len(baseline_audio))
        variants["crop_offset_plus_2s"] = full_audio[shifted_start:shifted_end]
        with tempfile.TemporaryDirectory(prefix="harbeat_style_robustness_") as temporary_name:
            temporary = Path(temporary_name)
            wav_path = temporary / "window.wav"
            _write_wav(wav_path, baseline_audio)
            variants["wav_pcm16_roundtrip"] = _load_audio(wav_path)
            if ffmpeg:
                mp3_path = temporary / "window.mp3"
                completed = subprocess.run(
                    [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav_path), "-b:a", "128k", str(mp3_path)],
                    capture_output=True,
                    text=True,
                )
                if completed.returncode == 0 and mp3_path.is_file():
                    variants["mp3_128k_roundtrip"] = _load_audio(mp3_path)
            else:
                try:
                    import soundfile as sf

                    mp3_path = temporary / "window.mp3"
                    sf.write(mp3_path, baseline_audio, SAMPLE_RATE, format="MP3")
                    variants["mp3_roundtrip"] = _load_audio(mp3_path)
                except (OSError, RuntimeError, TypeError, ValueError):
                    pass
            baseline_top = classes[int(np.argmax(baseline_probability))]
            for variant_name, variant_audio in variants.items():
                variant_embedding = _mean_embedding(predictor, variant_audio)
                variant_probability = _prediction(payload, variant_embedding)
                records.append({
                    "track_id": row["track_id"],
                    "reference_style": label,
                    "variant": variant_name,
                    "baseline_prediction": baseline_top,
                    "variant_prediction": classes[int(np.argmax(variant_probability))],
                    "top1_agreement": baseline_top == classes[int(np.argmax(variant_probability))],
                    "embedding_cosine": _cosine(baseline_embedding, variant_embedding),
                    "probability_l1": float(np.sum(np.abs(baseline_probability - variant_probability))),
                })
    summary = {}
    for variant in sorted({row["variant"] for row in records}):
        selected = [row for row in records if row["variant"] == variant]
        summary[variant] = {
            "tracks": len(selected),
            "top1_agreement": float(np.mean([row["top1_agreement"] for row in selected])),
            "embedding_cosine_mean": float(np.mean([row["embedding_cosine"] for row in selected])),
            "probability_l1_mean": float(np.mean([row["probability_l1"] for row in selected])),
        }
    return {
        "scope": "one deterministic first segment per class",
        "model": str(model_path),
        "ffmpeg_available": bool(ffmpeg),
        "summary": summary,
        "details": records,
    }


def _render_report(payload: dict[str, Any], cv: dict[str, Any]) -> str:
    leakage = payload["leakage"]
    shuffle = payload["label_shuffle"]
    audio = payload["audio_robustness"]
    lines = [
        "# 13 类风格原型：稳健性与反泄漏验证",
        "",
        f"> 生成时间：{payload['created_at']}",
        "",
        "## 结论",
        "",
        f"- 艺人/歌曲/Fold 隔离：{'通过' if leakage['passed'] else '失败'}。",
        f"- 标签打乱 Macro-F1：{shuffle['macro_f1_mean']:.3f} ± {shuffle['macro_f1_std']:.3f}（{shuffle['completed']} 次）。",
        f"- 正式原型门槛：{'通过' if cv['gates']['prototype_passed'] else '未通过'}；运行时接入：{'允许' if cv['gates']['runtime_integration_allowed'] else '禁止'}。",
        "",
        "## 音频扰动稳定性",
        "",
        "| 扰动 | 样本 | Top-1 一致率 | 嵌入余弦相似度 | 概率 L1 变化 |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, result in audio["summary"].items():
        lines.append(
            f"| `{name}` | {result['tracks']} | {result['top1_agreement']:.3f} "
            f"| {result['embedding_cosine_mean']:.3f} | {result['probability_l1_mean']:.3f} |"
        )
    lines.extend([
        "",
        "## 数据子组",
        "",
        "> 下表是相关性检查；固定窗通常对应更难的 Downbeat 样本，不能把差异直接解释为切片方法的因果效果。",
        "> A/B/C 来自嵌入折外预测，因此它与分类正确率天然相关，只用于排序人工复核，不能当作独立纯度验证。",
        "",
        "| 子组 | 歌曲数 | Top-1 |",
        "|---|---:|---:|",
    ])
    for dimension, groups in payload["subgroups"]["groups"].items():
        for name, result in groups.items():
            lines.append(
                f"| `{dimension}:{name}` | {result['tracks']} | {result['top1_accuracy']:.3f} |"
            )
    lines.extend([
        "",
        "## 边界说明",
        "",
        "- 扰动测试每类固定取一个片段，验证的是同一音频变换前后的预测一致性，不是额外测试集准确率。",
        "- 标签打乱按整曲重排，歌曲的所有片段仍保持同一随机标签，避免制造片段级泄漏。",
        "- 技术特征与嵌入消融结果见 `cross_validation.md`；元数据字段未出现在 feature schema 中。",
        "",
    ])
    return "\n".join(lines)


def _render_final_assessment(
    payload: dict[str, Any], cv: dict[str, Any], dataset_metadata: dict[str, Any],
) -> str:
    gates = cv["gates"]
    results = cv["results"]
    embedding = results[gates["best_embedding_model"]]["overall"]
    fusion = results[gates["best_fusion_model"]]["overall"]
    technical_names = [
        name for name in results if name.startswith("technical_")
    ]
    best_technical_name = max(
        technical_names, key=lambda name: results[name]["overall"]["macro_f1"],
    )
    technical = results[best_technical_name]["overall"]
    univariate = cv.get("univariate_technical_features") or []
    purity = cv["purity_audit"]
    external = payload.get("external_label_audit") or {}
    subgroups = payload.get("subgroups", {}).get("groups", {})
    window_groups = subgroups.get("window_method", {})
    switch_tracks = sum(
        bool(track.get("style_switch_points")) for track in purity["tracks"].values()
    )
    missing = dataset_metadata.get("missing_target_styles") or []
    lines = [
        "# 音乐风格模型首轮落地验证：最终判断",
        "",
        f"> 生成时间：{payload['created_at']}",
        "",
        "## 直接结论",
        "",
        f"- 当前实验能验证 **13 类**，不能验证 21 类；数据中缺少 {len(missing)} 类：{', '.join(missing)}。",
        f"- 13 类模型指标门槛：{'通过' if gates['model_gates_passed'] else '未通过'}；数据纯度筛查：{'通过' if gates['dataset_screen_passed'] else '未通过'}。",
        f"- 只看当前 13 类识别信号：最佳融合 Top-1 {fusion['top1_accuracy']:.3f}、Macro-F1 {fusion['macro_f1']:.3f}；完整模型门槛未过的模型项是融合增益仅 {gates['fusion_gain_macro_f1']:.3f}。",
        f"- 运行时接入：**{'允许' if gates['runtime_integration_allowed'] else '暂不允许'}**。未人工复核的模型辅助纯度标签不能当作最终真值。",
        "",
        "## 三条路线的证据",
        "",
        f"- 嵌入 `{gates['best_embedding_model']}`：Macro-F1 {embedding['macro_f1']:.3f}，Balanced Accuracy {embedding['balanced_accuracy']:.3f}，Top-3 {embedding['top3_recall']:.3f}。",
        f"- 技术特征 `{best_technical_name}`：Macro-F1 {technical['macro_f1']:.3f}，Balanced Accuracy {technical['balanced_accuracy']:.3f}，Top-3 {technical['top3_recall']:.3f}。",
        f"- 融合 `{gates['best_fusion_model']}`：Macro-F1 {fusion['macro_f1']:.3f}，Balanced Accuracy {fusion['balanced_accuracy']:.3f}，Top-3 {fusion['top3_recall']:.3f}；相对嵌入增益 {gates['fusion_gain_macro_f1']:.3f}。",
    ]
    if univariate:
        best = univariate[0]
        lines.append(
        f"- 最强单项技术特征 `{best['feature']}`：Top-1 {best['top1_accuracy']:.3f}，Macro-F1 {best['macro_f1']:.3f}；完整 65 项见 `technical_feature_accuracy.csv`。"
        )
    lines.extend([
        "",
        "## 数据不干净风险",
        "",
        f"- 模型辅助纯度等级：{json.dumps(purity['grade_counts'], ensure_ascii=False)}。",
        f"- 检出可能切换风格的歌曲：{switch_tracks}/{len(purity['tracks'])}。这些点位是人工试听队列，不是已确认的第二标签。",
        f"- 每类至少三首 A/B：{'是' if purity['all_classes_have_three_a_or_b'] else '否'}。",
        f"- MusicBrainz 身份审计：{external.get('tracks', 0)} 首；状态 {json.dumps(external.get('statuses', {}), ensure_ascii=False)}；有公开 tag {external.get('tagged_tracks', 0)} 首。Miss/无 tag 不自动视为标签冲突。",
        f"- 窗口子组：节拍对齐 {window_groups.get('beat_aligned_16_bars_hop_8', {}).get('top1_accuracy', 0.0):.3f}，固定回退 {window_groups.get('fixed_30s_hop_15s', {}).get('top1_accuracy', 0.0):.3f}；这是难度相关性，不是因果结论。",
        "",
        "## 下一步决策",
        "",
    ])
    if not gates["model_gates_passed"]:
        lines.append("1. 暂停接入；优先清洗 C 级与冲突片段，再扩充每类歌曲，不应在这 65 首上增加模型复杂度。")
    elif not gates["dataset_screen_passed"]:
        lines.append("1. 模型路线有信号，但数据筛查未过；先人工复核冲突时间点并补足每类至少三首 A/B。")
    else:
        lines.append("1. 13 类原型可进入人工复核与外部留出集阶段；在独立新歌复测前仍不视为生产模型。")
    lines.extend([
        "2. 为缺失 8 类各收集至少 15～30 首、跨艺人且版本明确的歌曲，再重新进行同样的艺人隔离验证。",
        "3. 只有 21 类都存在独立样本并通过逐类 Recall/混淆检查，才能回答 21 类正式模型是否成立。",
        "4. 当前最佳路线是在同一组四折结果中选出的，存在探索性选优偏差；扩充后必须保留完全未参与选择的外部测试集。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--effnet-model", type=Path, required=True)
    parser.add_argument("--shuffle-repetitions", type=int, default=10)
    args = parser.parse_args()
    dataset_dir = args.dataset_dir.resolve()
    manifest = _read_jsonl(dataset_dir / "manifest.jsonl")
    segments = _read_jsonl(dataset_dir / "segment_manifest.jsonl")
    features = np.load(dataset_dir / "embeddings" / "segment_features.npz", allow_pickle=False)
    embeddings = np.asarray(features["embeddings"], dtype=np.float32)
    technical = np.asarray(features["technical"], dtype=np.float32)
    schema = json.loads((dataset_dir / "feature_schema.json").read_text(encoding="utf-8"))
    dataset_metadata = json.loads(
        (dataset_dir / "dataset_metadata.json").read_text(encoding="utf-8")
    )
    cv = json.loads((dataset_dir / "reports" / "cross_validation.json").read_text(encoding="utf-8"))
    classes = list(cv["classes"])
    leakage = _leakage_checks(manifest, segments, schema)
    print(f"leakage checks: {'passed' if leakage['passed'] else 'failed'}", flush=True)
    shuffle = _shuffle_test(embeddings, segments, classes, args.shuffle_repetitions)
    print(f"label shuffle mean macro-F1: {shuffle['macro_f1_mean']:.3f}", flush=True)
    embedding_model = dataset_dir / "models" / "embedding_classifier" / "model.joblib"
    audio = _audio_robustness(
        manifest, segments, embedding_model, args.effnet_model.resolve(),
    )
    subgroups = _subgroup_summary(
        dataset_dir, manifest, segments, cv["gates"]["best_overall_model"],
    )
    _write_review_queue(dataset_dir, manifest, segments)
    payload = {
        "version": "style_reference_robustness_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "leakage": leakage,
        "label_shuffle": shuffle,
        "audio_robustness": audio,
        "subgroups": subgroups,
        "ablation": {
            name: result["overall"] for name, result in cv["results"].items()
        },
        "metadata_removal": {
            "passed": not leakage["forbidden_model_features"],
            "reason": "model matrices are assembled only from segment_features.npz; manifest metadata is never concatenated",
        },
        "external_label_audit": _external_audit_summary(dataset_dir),
    }
    reports = dataset_dir / "reports"
    _atomic_json(reports / "robustness.json", payload)
    (reports / "robustness.md").write_text(_render_report(payload, cv), encoding="utf-8")
    (reports / "final_assessment.md").write_text(
        _render_final_assessment(payload, cv, dataset_metadata), encoding="utf-8",
    )
    print(json.dumps({
        "status": "ready",
        "leakage_passed": leakage["passed"],
        "shuffle_macro_f1_mean": shuffle["macro_f1_mean"],
        "audio_summary": audio["summary"],
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
