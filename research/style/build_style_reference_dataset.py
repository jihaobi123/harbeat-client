#!/usr/bin/env python3
"""Build a leakage-safe manifest from a folder-labelled reference ZIP.

The source archive is never modified. Audio members are copied to a separate
experiment directory under deterministic content-derived ids. Splits are made
at whole-track and primary-artist level before any later segment extraction.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Any
from zipfile import ZipFile, ZipInfo

from mutagen import File as MutagenFile
import numpy as np
from sklearn.model_selection import StratifiedGroupKFold


AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus"}
STYLE_LABELS = {
    "afro": "afro_afrobeats",
    "amapiano": "amapiano",
    "baile funk": "baile_funk",
    "boombap": "boombap",
    "breakbeat": "breakbeat",
    "dancehall": "dancehall",
    "disco": "disco",
    "funk": "funk",
    "grime": "grime_uk_hiphop",
    "house": "house",
    "jazz hiphop": "jazz_hiphop",
    "jersey club": "jersey_club",
    "trap": "trap",
}
TARGET_STYLE_IDS = (
    "boombap", "trap", "funk", "breakbeat", "soul_neo_soul", "jazz_hiphop",
    "afro_afrobeats", "house", "grime_uk_hiphop", "rnb", "disco",
    "jersey_club", "drill", "amapiano", "moombahton", "dancehall",
    "baile_funk", "memphis_trap", "rage", "uk_garage", "trap_soul",
)
VERSION_TERMS = re.compile(
    r"\b(remix|mix|edit|vip|instrumental|mashup|bootleg|version|rework)\b",
    flags=re.IGNORECASE,
)
TIMESTAMP_SUFFIX = re.compile(r"\.\d{10,}$")


def _json_dump(path: Path, payload: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    temporary.replace(path)


def _jsonl_dump(path: Path, rows: list[dict[str, Any]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def _audio_members(archive: ZipFile) -> list[ZipInfo]:
    members = []
    for member in archive.infolist():
        name = member.filename
        if member.is_dir() or name.startswith("__MACOSX/") or "/._" in name:
            continue
        if PurePosixPath(name).suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        members.append(member)
    return members


def _label_for(member: ZipInfo) -> tuple[str, str]:
    original = PurePosixPath(member.filename).parts[-2].strip()
    normalized = " ".join(original.casefold().replace("_", " ").split())
    if normalized not in STYLE_LABELS:
        raise ValueError(f"unsupported style directory: {original!r}")
    return original, STYLE_LABELS[normalized]


def _artist_title(filename: str) -> tuple[str, str, str]:
    stem = TIMESTAMP_SUFFIX.sub("", Path(filename).stem).strip()
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
    else:
        artist, title = "unknown_artist", stem
    artist = " ".join(artist.split())
    title = " ".join(title.split())
    primary = re.split(r"\s*(?:,|&|/|\bfeat\.?\b|\bft\.?\b)\s*", artist, maxsplit=1, flags=re.I)[0]
    primary = primary.strip() or artist
    return artist, primary, title


def _copy_and_hash(archive: ZipFile, member: ZipInfo, target: Path) -> str:
    digest = hashlib.sha256()
    temporary = target.with_suffix(target.suffix + ".tmp")
    with archive.open(member) as source, temporary.open("wb") as destination:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            destination.write(chunk)
    temporary.replace(target)
    return digest.hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _audio_metadata(path: Path) -> tuple[dict[str, Any], list[str]]:
    flags: list[str] = []
    result = {
        "duration_seconds": None,
        "sample_rate": None,
        "channels": None,
        "bitrate": None,
        "codec": path.suffix.lower().lstrip("."),
    }
    try:
        audio = MutagenFile(path)
        info = getattr(audio, "info", None)
        if info is None:
            raise ValueError("audio metadata unavailable")
        result.update({
            "duration_seconds": round(float(getattr(info, "length", 0.0) or 0.0), 3),
            "sample_rate": int(getattr(info, "sample_rate", 0) or 0) or None,
            "channels": int(getattr(info, "channels", 0) or 0) or None,
            "bitrate": int(getattr(info, "bitrate", 0) or 0) or None,
        })
        if not result["duration_seconds"]:
            flags.append("duration_unavailable")
    except Exception as exc:  # corrupt or unsupported source must remain auditable
        flags.append(f"metadata_error:{type(exc).__name__}")
    return result, flags


def _assign_folds(rows: list[dict[str, Any]], fold_count: int, seed: int) -> dict[str, int]:
    y = np.asarray([row["primary_style"] for row in rows])
    groups = np.asarray([row["artist_group"] for row in rows])
    splitter = StratifiedGroupKFold(n_splits=fold_count, shuffle=True, random_state=seed)
    assignments: dict[str, int] = {}
    dummy = np.zeros((len(rows), 1), dtype=float)
    for fold, (_, test_indices) in enumerate(splitter.split(dummy, y, groups)):
        for index in test_indices:
            assignments[rows[int(index)]["track_id"]] = int(fold)
    if len(assignments) != len(rows):
        raise RuntimeError("not every track received a fold assignment")
    return assignments


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            cooked = {}
            for field in fields:
                value = row.get(field)
                if isinstance(value, (list, dict)):
                    value = json.dumps(value, ensure_ascii=False)
                cooked[field] = value
            writer.writerow(cooked)


def _render_report(rows: list[dict[str, Any]], source_zip: Path, fold_count: int) -> str:
    labels = sorted({row["primary_style"] for row in rows})
    missing = [style for style in TARGET_STYLE_IDS if style not in labels]
    repeated = {}
    for row in rows:
        repeated.setdefault(row["artist_group"], []).append(row)
    repeated = {key: value for key, value in repeated.items() if len(value) > 1}
    versioned = [row for row in rows if "version_or_remix_name" in row["risk_flags"]]
    durations = [row["duration_seconds"] for row in rows if row["duration_seconds"]]
    lines = [
        "# 音乐风格参考曲库：数据集基础审计",
        "",
        f"> 源文件：`{source_zip}`",
        f"> 生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "## 结论",
        "",
        f"- 有效音频：{len(rows)} 首；当前类别：{len(labels)}；目标类别：{len(TARGET_STYLE_IDS)}。",
        f"- 每类歌曲数范围：{min(sum(r['primary_style'] == label for r in rows) for label in labels)}～{max(sum(r['primary_style'] == label for r in rows) for label in labels)}。",
        f"- 总时长：{sum(durations) / 3600:.2f} 小时。",
        f"- 缺失类别：{', '.join(missing)}。",
        f"- 文件名提示 Remix/Mix/Edit/Instrumental 等版本风险：{len(versioned)} 首。",
        f"- 重复主艺人组：{len(repeated)} 个；已通过艺人分组 Fold 隔离。",
        "- 当前所有文件夹标签均标为 `unreviewed`；不能在片段纯度审计前当成干净真值。",
        "",
        "## 类别分布",
        "",
        "| 类别 | 歌曲数 | 艺人组数 | Fold分布 |",
        "|---|---:|---:|---|",
    ]
    for label in labels:
        selected = [row for row in rows if row["primary_style"] == label]
        fold_counts = [sum(row["fold"] == fold for row in selected) for fold in range(fold_count)]
        lines.append(
            f"| `{label}` | {len(selected)} | {len({row['artist_group'] for row in selected})} "
            f"| {', '.join(f'F{fold}:{count}' for fold, count in enumerate(fold_counts))} |"
        )
    lines.extend(["", "## 重复艺人组", ""])
    if not repeated:
        lines.append("- 无")
    for artist_group, selected in sorted(repeated.items()):
        tracks = "；".join(f"{row['artist']} - {row['title']}" for row in selected)
        lines.append(f"- `{artist_group}`：{tracks}")
    lines.extend([
        "",
        "## 后续验证约束",
        "",
        "1. Fold 是完整歌曲和主艺人级别，后续所有片段必须继承歌曲 Fold。",
        "2. 文件名、艺人名、目录标签不得进入模型输入。",
        "3. `unreviewed` 歌曲在完成片段纯度和外部标签审计前只能用于弱监督实验。",
        "4. 只有 A/B 级歌曲可进入最终原型训练；C 级和争议样本只用于压力测试。",
        "5. 当前只允许训练 13 类原型，不得把缺失 8 类解释为负样本或类外识别能力。",
        "",
    ])
    return "\n".join(lines)


def build_dataset(source_zip: Path, output_dir: Path, *, fold_count: int, seed: int) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_root = output_dir / "audio"
    audio_root.mkdir(exist_ok=True)
    rows: list[dict[str, Any]] = []
    with ZipFile(source_zip) as archive:
        members = _audio_members(archive)
        for member in members:
            original_label, primary_style = _label_for(member)
            original_name = PurePosixPath(member.filename).name
            artist, primary_artist, title = _artist_title(original_name)
            risk_flags = ["label_unreviewed"]
            if VERSION_TERMS.search(title):
                risk_flags.append("version_or_remix_name")
            suffix = PurePosixPath(original_name).suffix.lower()
            provisional_id = hashlib.sha256(member.filename.encode("utf-8")).hexdigest()[:16]
            label_dir = audio_root / primary_style
            label_dir.mkdir(exist_ok=True)
            target = label_dir / f"{provisional_id}{suffix}"
            sha256 = _copy_and_hash(archive, member, target)
            track_id = sha256[:16]
            final_target = label_dir / f"{track_id}{suffix}"
            if final_target != target:
                if final_target.exists() and final_target.read_bytes() != target.read_bytes():
                    raise RuntimeError(f"track id collision: {track_id}")
                target.replace(final_target)
            metadata, metadata_flags = _audio_metadata(final_target)
            risk_flags.extend(metadata_flags)
            rows.append({
                "track_id": track_id,
                "primary_style": primary_style,
                "secondary_styles": [],
                "original_label": original_label,
                "artist": artist,
                "primary_artist": primary_artist,
                "artist_group": primary_artist.casefold(),
                "title": title,
                "original_filename": original_name,
                "source_member": member.filename,
                "audio_path": str(final_target.resolve()),
                "sha256": sha256,
                "file_size_bytes": member.file_size,
                **metadata,
                "label_source": "folder_label_user_reference_library",
                "label_status": "unreviewed",
                "label_confidence": None,
                "purity_grade": None,
                "core_coverage": None,
                "supporting_coverage": None,
                "conflicting_coverage": None,
                "risk_flags": sorted(set(risk_flags)),
            })
    rows.sort(key=lambda row: (row["primary_style"], row["artist_group"], row["title"]))
    if len({row["sha256"] for row in rows}) != len(rows):
        raise ValueError("archive contains exact duplicate audio files")
    folds = _assign_folds(rows, fold_count=fold_count, seed=seed)
    for row in rows:
        row["fold"] = folds[row["track_id"]]
    _jsonl_dump(output_dir / "manifest.jsonl", rows)
    _json_dump(output_dir / "track_splits.json", {
        "version": "style_reference_group_folds_v1",
        "seed": seed,
        "fold_count": fold_count,
        "group": "primary_artist",
        "assignments": folds,
    })
    _write_csv(output_dir / "label_audit.csv", rows, [
        "track_id", "primary_style", "secondary_styles", "artist", "primary_artist",
        "title", "original_filename", "duration_seconds", "sample_rate", "channels",
        "bitrate", "fold", "label_status", "label_confidence", "purity_grade",
        "core_coverage", "supporting_coverage", "conflicting_coverage", "risk_flags",
    ])
    (output_dir / "reports").mkdir(exist_ok=True)
    (output_dir / "reports" / "dataset_audit.md").write_text(
        _render_report(rows, source_zip, fold_count), encoding="utf-8",
    )
    _json_dump(output_dir / "dataset_metadata.json", {
        "version": "style_reference_dataset_v0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_zip": str(source_zip.resolve()),
        "source_zip_sha256": _file_hash(source_zip),
        "track_count": len(rows),
        "class_count": len({row["primary_style"] for row in rows}),
        "target_class_count": len(TARGET_STYLE_IDS),
        "missing_target_styles": sorted(set(TARGET_STYLE_IDS) - {row["primary_style"] for row in rows}),
        "fold_count": fold_count,
        "seed": seed,
        "audio_is_git_artifact": False,
        "labels_are_reviewed": False,
    })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260829)
    args = parser.parse_args()
    if not args.zip.is_file():
        parser.error(f"ZIP not found: {args.zip}")
    if args.folds < 2:
        parser.error("--folds must be at least 2")
    rows = build_dataset(args.zip, args.output_dir, fold_count=args.folds, seed=args.seed)
    print(json.dumps({
        "status": "ready",
        "tracks": len(rows),
        "classes": len({row['primary_style'] for row in rows}),
        "output_dir": str(args.output_dir.resolve()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
