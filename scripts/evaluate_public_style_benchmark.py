#!/usr/bin/env python3
"""Evaluate saved production analysis against public weak style labels."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.benchmark_evaluation import multilabel_metrics  # noqa: E402


BOUNDARY_STYLES = {"funk", "disco", "house"}
NEW_FEATURES = (
    "low_frequency.bass_syncopation",
    "low_frequency.bass_staccato_ratio",
    "low_frequency.bass_riff_repetition",
    "low_frequency.bass_octave_pattern",
    "low_frequency.bass_kick_interlock",
    "rhythm_grammar.offbeat_open_hat",
    "rhythm_grammar.four_floor_stability",
    "rhythm_grammar.timing_quantization",
    "rhythm_grammar.drum_loop_repetition",
    "rhythm_grammar.drum_machine_consistency",
)


def _feature(track: dict, path: str) -> dict | None:
    group, name = path.split(".", 1)
    return (((track.get("stem_analysis") or {}).get("feature_analysis") or {}).get("feature_groups") or {}).get(group, {}).get(name)


def evaluate(manifest: list[dict], result: dict) -> dict:
    expected_by_id = {row["clip_id"]: set(row.get("expected_styles") or []) for row in manifest}
    rows = [track for track in result.get("tracks", []) if track.get("status") == "completed"]
    expected_sets = []
    detected_sets = []
    top_hits = boundary_hits = primary_hits = detected_hits = no_primary = 0
    top_distribution = Counter()
    boundary_distribution = Counter()
    for track in rows:
        clip_id = Path(track.get("file", "")).stem
        expected = expected_by_id.get(clip_id, set())
        styles = (track.get("style_analysis") or {}).get("styles") or []
        top = ((track.get("style_analysis") or {}).get("primary_style_candidate") or {})
        primary = ((track.get("style_analysis") or {}).get("primary_style") or {})
        detected = {
            item.get("style_id") for item in ((track.get("style_analysis") or {}).get("detected_styles") or [])
            if item.get("style_id")
        }
        boundary = max(
            (item for item in styles if item.get("style_id") in BOUNDARY_STYLES),
            key=lambda item: float(item.get("score", 0.0) or 0.0),
            default={},
        )
        top_id = top.get("style_id")
        primary_id = primary.get("style_id")
        boundary_id = boundary.get("style_id")
        top_distribution[str(top_id or "none")] += 1
        boundary_distribution[str(boundary_id or "none")] += 1
        top_hits += bool(top_id in expected)
        boundary_hits += bool(boundary_id in expected)
        primary_hits += bool(primary_id in expected)
        detected_hits += bool(expected & detected)
        no_primary += not bool(primary_id)
        expected_sets.append(expected)
        detected_sets.append(detected)

    feature_stats = {}
    for path in NEW_FEATURES:
        values = []
        reliabilities = []
        unavailable = 0
        for track in rows:
            value = _feature(track, path)
            if not isinstance(value, dict) or value.get("score") is None:
                unavailable += 1
                continue
            values.append(float(value["score"]))
            reliabilities.append(float(value.get("reliability", 0.0) or 0.0))
        feature_stats[path] = {
            "available": len(values),
            "unavailable": unavailable,
            "minimum": round(min(values), 4) if values else None,
            "maximum": round(max(values), 4) if values else None,
            "mean": round(statistics.fmean(values), 4) if values else None,
            "mean_reliability": round(statistics.fmean(reliabilities), 4) if reliabilities else None,
            "near_zero_count": sum(value <= 0.02 for value in values),
            "near_saturation_count": sum(value >= 0.98 for value in values),
        }
    count = len(rows)
    return {
        "benchmark_type": "public_weak_label_validation",
        "completed": count,
        "manifest_items": len(manifest),
        "top_candidate_hit_ratio": round(top_hits / count, 4) if count else 0.0,
        "boundary_only_candidate_hit_ratio": round(boundary_hits / count, 4) if count else 0.0,
        "primary_style_hit_ratio": round(primary_hits / count, 4) if count else 0.0,
        "detected_any_expected_ratio": round(detected_hits / count, 4) if count else 0.0,
        "no_primary_style_count": no_primary,
        "detected_multilabel": multilabel_metrics(expected_sets, detected_sets),
        "top_candidate_distribution": dict(top_distribution.most_common()),
        "boundary_candidate_distribution": dict(boundary_distribution.most_common()),
        "feature_statistics": feature_stats,
        "warning": "uploader tags and random 30-second clips are weak labels; do not calibrate production thresholds without human clip review",
    }


def render_markdown(summary: dict) -> str:
    lines = [
        "# MTG-Jamendo Funk / Disco / House 弱标签验证",
        "",
        f"- 完成：{summary['completed']}/{summary['manifest_items']}",
        f"- 21 类第一候选命中公开标签：{summary['top_candidate_hit_ratio']:.1%}",
        f"- 仅在 Funk/Disco/House 内比较的候选命中：{summary['boundary_only_candidate_hit_ratio']:.1%}",
        f"- 完整主标签命中：{summary['primary_style_hit_ratio']:.1%}",
        f"- 多标签至少命中一个公开标签：{summary['detected_any_expected_ratio']:.1%}",
        f"- 无完整主标签：{summary['no_primary_style_count']}",
        "",
        "> 注意：上传者标签和随机 30 秒片段属于弱标签，只能用于发现问题，不能直接修改生产阈值。",
        "",
        "## 新增特征分布",
        "",
        "| 特征 | 可用 | 最小 | 最大 | 均值 | 平均可靠度 | 近零 | 近饱和 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for path, item in summary["feature_statistics"].items():
        lines.append(
            f"| `{path}` | {item['available']} | {item['minimum']} | {item['maximum']} "
            f"| {item['mean']} | {item['mean_reliability']} | {item['near_zero_count']} "
            f"| {item['near_saturation_count']} |"
        )
    lines.extend([
        "",
        "## 第一候选分布",
        "",
        ", ".join(f"{name}: {count}" for name, count in summary["top_candidate_distribution"].items()),
        "",
        "## 三类内部候选分布",
        "",
        ", ".join(f"{name}: {count}" for name, count in summary["boundary_candidate_distribution"].items()),
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()
    summary = evaluate(
        json.loads(args.manifest.read_text(encoding="utf-8")),
        json.loads(args.results.read_text(encoding="utf-8")),
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    args.output_md.write_text(render_markdown(summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
