#!/usr/bin/env python3
"""Reanalyse saved test-library songs from existing Demucs stems.

This runner is intentionally feature-only.  It reuses saved BPM/beat/key
results and existing stems, invokes currently configured feature models, and
does not publish a style decision while the feature layer is under audit.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.stem_analysis import analyze_stem_files  # noqa: E402
from app.modules.library.feature_calibration import load_feature_calibration  # noqa: E402


STEM_NAMES = ("vocals", "drums", "bass", "other")
CALIBRATION_FEATURES = load_feature_calibration().get("features") or {}


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def stem_paths(stems_root: Path, title: str) -> dict[str, str]:
    directory = stems_root / "htdemucs" / title
    paths = {name: str(directory / f"{name}.wav") for name in STEM_NAMES}
    missing = [name for name, path in paths.items() if not Path(path).is_file()]
    if missing:
        raise FileNotFoundError(f"missing stems for {title}: {', '.join(missing)}")
    return paths


def _feature_inventory(feature_analysis: dict) -> list[dict[str, Any]]:
    rows = []
    for group, features in (feature_analysis.get("feature_groups") or {}).items():
        for name, feature in (features or {}).items():
            if not isinstance(feature, dict):
                continue
            rows.append({
                "path": f"{group}.{name}",
                "score": feature.get("score"),
                "probability": feature.get("probability"),
                "decision": feature.get("decision"),
                "validation_status": feature.get("validation_status"),
                "validation_scope": feature.get("validation_scope"),
                "style_required_allowed": bool(feature.get("style_required_allowed")),
                "reliability": feature.get("reliability"),
            })
    return rows


def render_report(payload: dict) -> str:
    lines = [
        "# 测试曲库：特征分析验证结果",
        "",
        f"> 更新时间：{payload.get('updated_at', '')}",
        "> 本报告只检查特征层；验证失败和未验证特征不会被写成可靠风格依据。",
        "",
        "| 歌曲 | 状态 | 已验证特征 | 验证失败 | 未验证/候选 | 模型 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for track in payload.get("tracks", []):
        if track.get("status") != "completed":
            lines.append(f"| {track.get('title')} | 失败：{track.get('error')} | - | - | - | - |")
            continue
        feature = (track.get("stem_analysis") or {}).get("feature_analysis") or {}
        counts = (feature.get("validation_summary") or {}).get("counts") or {}
        models = ", ".join(feature.get("selected_models") or []) or "无"
        provisional = int(counts.get("provisional", 0)) + int(counts.get("candidate_only", 0))
        lines.append(
            f"| {track.get('title')} | {feature.get('status')} "
            f"| {int(counts.get('validated', 0))} "
            f"| {int(counts.get('failed_validation', 0))} "
            f"| {provisional} | {models} |"
        )
    lines.extend(["", "## 每首歌已验证特征", ""])
    for track in payload.get("tracks", []):
        if track.get("status") != "completed":
            continue
        lines.extend([f"### {track.get('title')}", ""])
        validated = [
            row for row in track.get("feature_inventory", [])
            if row["validation_status"] == "validated"
        ]
        if not validated:
            lines.append("- 无")
        for row in validated:
            value = row["probability"] if row["probability"] is not None else row["score"]
            scope = str(
                row.get("validation_scope")
                or (CALIBRATION_FEATURES.get(row["path"]) or {}).get("validation_scope")
                or ""
            )
            if row["style_required_allowed"]:
                role = "可作风格必要条件"
            elif "rule_only" in scope:
                role = "仅规则一致性；不代表命名风格"
            elif row["decision"] == "measured":
                role = "连续测量证据"
            else:
                role = "辅助证据"
            lines.append(
                f"- `{row['path']}`：{row['decision']}，校准概率/分数 {value}（{role}）"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def checkpoint(output_dir: Path, payload: dict) -> None:
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "results.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(_json_value(payload), ensure_ascii=False, indent=2), encoding="utf-8",
    )
    temporary.replace(target)
    (output_dir / "report.md").write_text(render_report(payload), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-results", type=Path, required=True)
    parser.add_argument("--stems-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    source = json.loads(args.source_results.read_text(encoding="utf-8"))
    output_path = args.output_dir / "results.json"
    if args.resume and output_path.is_file():
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    else:
        payload = {
            "version": "feature_test_library_v1",
            "source_results": str(args.source_results.resolve()),
            "stems_root": str(args.stems_root.resolve()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tracks": [],
        }
    completed = {
        track.get("title") for track in payload.get("tracks", [])
        if track.get("status") == "completed"
    }
    tracks = source.get("tracks", [])
    if args.limit > 0:
        tracks = tracks[:args.limit]
    for index, source_track in enumerate(tracks, start=1):
        title = str(source_track.get("title") or Path(source_track["file"]).stem)
        if title in completed:
            print(f"[{index}/{len(tracks)}] skip completed: {title}", flush=True)
            continue
        print(f"[{index}/{len(tracks)}] feature analysis: {title}", flush=True)
        started = time.monotonic()
        try:
            core = source_track.get("core") or {}
            paths = stem_paths(args.stems_root, title)
            stem_analysis = analyze_stem_files(
                paths,
                original_path=source_track.get("file"),
                bpm=float(core.get("bpm", 0.0) or 0.0),
                beat_points=list(core.get("beat_points") or []),
                downbeats=list(core.get("downbeats") or []),
                key_profile=dict(core.get("key_profile") or {}),
            )
            track = {
                "title": title,
                "file": source_track.get("file"),
                "status": "completed",
                "elapsed_sec": round(time.monotonic() - started, 3),
                "core": core,
                "stems": paths,
                "stem_analysis": stem_analysis,
                "feature_inventory": _feature_inventory(stem_analysis.get("feature_analysis") or {}),
            }
            print(f"[{index}/{len(tracks)}] completed in {track['elapsed_sec']:.1f}s", flush=True)
        except Exception as exc:
            track = {
                "title": title,
                "file": source_track.get("file"),
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"[{index}/{len(tracks)}] failed: {track['error']}", flush=True)
        payload["tracks"] = [
            item for item in payload.get("tracks", []) if item.get("title") != title
        ] + [track]
        checkpoint(args.output_dir, payload)
    # Also refresh the human-readable report when --resume skips every track.
    checkpoint(args.output_dir, payload)
    return 0 if all(track.get("status") == "completed" for track in payload["tracks"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
