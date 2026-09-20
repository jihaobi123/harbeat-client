"""Run the production analysis stack against a local test music directory.

This runner deliberately avoids the application database.  It is intended for
review libraries supplied by musicians: every completed track is checkpointed
to JSON and a concise Markdown review report is regenerated after each track.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.analysis import analyze_audio_file
from app.modules.library.high_frequency_style_classifier import classify_high_frequency_styles
from app.modules.library.stem_analysis import analyze_stem_files

AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".ogg", ".aac", ".m4a", ".opus", ".wma"}
STEM_NAMES = ("vocals", "drums", "bass", "other")


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


def _write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_json_value(payload), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _stem_paths(stems_root: Path, audio_path: Path) -> dict[str, str]:
    directory = stems_root / "htdemucs" / audio_path.stem
    return {name: str(directory / f"{name}.wav") for name in STEM_NAMES}


def _stems_complete(paths: dict[str, str]) -> bool:
    return all(Path(paths[name]).is_file() for name in STEM_NAMES)


def _separate(audio_path: Path, stems_root: Path) -> dict[str, str]:
    paths = _stem_paths(stems_root, audio_path)
    if _stems_complete(paths):
        return paths
    subprocess.run(
        [
            sys.executable,
            "-m",
            "demucs",
            "-n",
            "htdemucs",
            "--segment",
            "7",
            "-o",
            str(stems_root),
            str(audio_path),
        ],
        check=True,
    )
    if not _stems_complete(paths):
        raise FileNotFoundError("Demucs completed but one or more stem files are missing")
    return paths


def _feature_rows(feature_analysis: dict) -> list[tuple[str, str, float, float]]:
    rows: list[tuple[str, str, float, float]] = []
    for group_name, group in (feature_analysis.get("feature_groups") or {}).items():
        if not isinstance(group, dict):
            continue
        for feature_name, value in group.items():
            if not isinstance(value, dict) or value.get("score") is None:
                continue
            if value.get("availability", "available") != "available":
                continue
            rows.append((
                str(group_name),
                str(feature_name),
                float(value.get("score", 0.0) or 0.0),
                float(value.get("reliability", value.get("confidence", 0.0)) or 0.0),
            ))
    return sorted(rows, key=lambda item: (item[0], -item[2], item[1]))


def _style_evidence(style: dict, key: str) -> str:
    items = style.get(key) or []
    if not items:
        return "无"
    return "、".join(
        f"{item.get('feature')}({float(item.get('score', 0.0)):.2f})"
        for item in items[:4]
    )


def _render_report(payload: dict) -> str:
    tracks = payload.get("tracks", [])
    completed = sum(track.get("status") == "completed" for track in tracks)
    failed = sum(track.get("status") == "error" for track in tracks)
    lines = [
        "# 测试曲库 1.0：预处理与21种风格分析结果",
        "",
        f"> 生成时间：{payload.get('updated_at', '')}",
        f"> 已处理：{len(tracks)} 首；成功：{completed} 首；失败：{failed} 首。",
        "",
        "说明：风格分数是绝对证据分，不强制合计为100%。`needs_review` 表示证据不足或候选过于接近。",
        "",
    ]
    for index, track in enumerate(tracks, start=1):
        lines.extend([f"## {index}. {track.get('title', track.get('file', '未知歌曲'))}", ""])
        if track.get("status") != "completed":
            lines.extend([f"- 状态：失败", f"- 错误：{track.get('error', 'unknown')}", ""])
            continue
        core = track.get("core", {})
        stem = track.get("stem_analysis", {})
        features = stem.get("feature_analysis", {})
        styles = track.get("style_analysis", {})
        lines.extend([
            f"- 基础：{float(core.get('bpm', 0.0)):.2f} BPM；{core.get('key') or '未知调性'}；Camelot {core.get('camelot_key') or '-'}；能量 {float(core.get('energy', 0.0)):.3f}",
            f"- 节拍：Beat {len(core.get('beat_points') or [])}；Downbeat {len(core.get('downbeats') or [])}；置信度 {float(core.get('beat_confidence', 0.0) or 0.0):.3f}",
            f"- 分轨：完整={stem.get('has_complete_stems')}；质量={float(stem.get('stem_quality_score', 0.0) or 0.0):.3f}",
            f"- 特征：版本={features.get('version', 'unknown')}；状态={features.get('status', 'unknown')}；总体测量置信度={float((features.get('confidence') or {}).get('overall', 0.0) or 0.0):.3f}",
            f"- 风格：版本={styles.get('version', 'unknown')}；状态={styles.get('status', 'unknown')}；可靠度={float(styles.get('reliability', 0.0) or 0.0):.3f}；置信度={float(styles.get('confidence', 0.0) or 0.0):.3f}；需复核={styles.get('needs_review', True)}",
            f"- Drum Loop：{stem.get('has_drum_loop')}；重复分数={float((stem.get('drum_loop_analysis') or {}).get('score', 0.0) or 0.0):.3f}",
            f"- 复核原因：{'、'.join(styles.get('review_reasons') or []) or '无'}",
            "- 多标签：" + (
                "、".join(
                    f"{item.get('name')} {float(item.get('score', 0.0)):.3f}"
                    for item in (styles.get("detected_styles") or [])
                ) or "无达到完整检测条件的标签"
            ),
            "",
            "| 排名 | 风格 | 分数 | 可靠度 | 置信度 | 覆盖率 | 支持证据 | 反对证据 |",
            "|---:|---|---:|---:|---:|---:|---|---|",
        ])
        for style in styles.get("top_styles", [])[:3]:
            lines.append(
                f"| {style.get('rank')} | {style.get('name')} (`{style.get('style_id')}`) "
                f"| {float(style.get('score', 0.0)):.3f} | {float(style.get('reliability', 0.0)):.3f} "
                f"| {float(style.get('confidence', 0.0)):.3f} "
                f"| {float(style.get('feature_coverage', 0.0)):.3f} "
                f"| {_style_evidence(style, 'positive_evidence')} "
                f"| {_style_evidence(style, 'negative_evidence')} |"
            )
        lines.extend(["", "主要可用特征：", ""])
        feature_rows = _feature_rows(features)
        if feature_rows:
            for group, name, score, reliability in feature_rows:
                if score >= 0.35:
                    lines.append(f"- `{group}.{name}`：分数 {score:.3f}，可靠度 {reliability:.3f}")
        else:
            lines.append("- 无可用特征")
        flags = features.get("quality_flags") or []
        lines.extend(["", f"质量提示：{'、'.join(flags) if flags else '无'}", ""])
    return "\n".join(lines).rstrip() + "\n"


def _checkpoint(output_dir: Path, payload: dict) -> None:
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(output_dir / "results.json", payload)
    (output_dir / "report.md").write_text(_render_report(payload), encoding="utf-8")


def _analyze_track(audio_path: Path, stems_root: Path) -> dict:
    started = time.monotonic()
    core = analyze_audio_file(str(audio_path))
    stem_paths = _separate(audio_path, stems_root)
    stem_analysis = analyze_stem_files(
        stem_paths,
        original_path=str(audio_path),
        bpm=float(core.get("bpm", 0.0) or 0.0),
        beat_points=list(core.get("beat_points") or []),
        downbeats=list(core.get("downbeats") or []),
        key_profile=dict(core.get("key_profile") or {}),
    )
    style_analysis = classify_high_frequency_styles(stem_analysis.get("feature_analysis"))
    return {
        "file": str(audio_path),
        "title": audio_path.stem,
        "status": "completed",
        "elapsed_sec": round(time.monotonic() - started, 3),
        "core": core,
        "stems": stem_paths,
        "stem_analysis": stem_analysis,
        "style_analysis": style_analysis,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stems_root = output_dir / "stems"
    stems_root.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "results.json"
    if args.resume and result_path.is_file():
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    else:
        payload = {
            "version": "style_test_library_v2",
            "input_dir": str(input_dir),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "tracks": [],
        }
    completed_files = {
        track.get("file") for track in payload.get("tracks", [])
        if track.get("status") == "completed"
    }
    audio_files = sorted(
        path for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    )
    if args.limit > 0:
        audio_files = audio_files[: args.limit]

    for index, audio_path in enumerate(audio_files, start=1):
        if str(audio_path) in completed_files:
            print(f"[{index}/{len(audio_files)}] skip completed: {audio_path.name}", flush=True)
            continue
        print(f"[{index}/{len(audio_files)}] analyzing: {audio_path.name}", flush=True)
        try:
            track = _analyze_track(audio_path, stems_root)
            top = (track.get("style_analysis") or {}).get("top_styles") or []
            top_text = ", ".join(f"{item['style_id']}={item['score']:.3f}" for item in top[:3])
            print(f"[{index}/{len(audio_files)}] completed in {track['elapsed_sec']:.1f}s: {top_text}", flush=True)
        except Exception as exc:
            track = {
                "file": str(audio_path),
                "title": audio_path.stem,
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"[{index}/{len(audio_files)}] failed: {track['error']}", flush=True)
        payload["tracks"] = [
            item for item in payload.get("tracks", []) if item.get("file") != str(audio_path)
        ] + [track]
        _checkpoint(output_dir, payload)

    print(f"results: {result_path}", flush=True)
    print(f"report: {output_dir / 'report.md'}", flush=True)
    return 0 if all(track.get("status") == "completed" for track in payload["tracks"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
