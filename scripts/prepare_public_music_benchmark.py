#!/usr/bin/env python3
"""Select and optionally download a small, artist-diverse MTG-Jamendo benchmark."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen


TARGET_TAGS = {
    "funk": "funk",
    "disco": "disco",
    "house": "house",
}


def _stable_key(*values: str) -> str:
    return hashlib.sha256("|".join(values).encode("utf-8")).hexdigest()


def _metadata(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["TRACK_ID"]: row for row in csv.DictReader(handle, delimiter="\t")}


def _licenses(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    result = {}
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.fullmatch(r"\d+/\d+\.mp3", line.strip()):
            current = line.strip()
        elif current and line.startswith("Available under "):
            result[current] = line.removeprefix("Available under ").strip()
            current = None
    return result


def select_candidates(
    genre_tsv: Path,
    metadata_tsv: Path,
    *,
    per_style: int,
    audio_licenses: Path | None = None,
) -> list[dict]:
    metadata = _metadata(metadata_tsv)
    licenses = _licenses(audio_licenses) if audio_licenses else {}
    candidates = []
    with genre_tsv.open("r", encoding="utf-8", newline="") as handle:
        rows = csv.reader(handle, delimiter="\t")
        next(rows, None)
        for row in rows:
            if len(row) < 6:
                continue
            track_id, artist_id, album_id, relative_path, duration, *raw_tags = row
            tags = {value.split("---", 1)[-1] for value in raw_tags if value.startswith("genre---")}
            expected = sorted(style for style, tag in TARGET_TAGS.items() if tag in tags)
            if not expected:
                continue
            public = metadata.get(track_id, {})
            candidates.append({
                "clip_id": f"mtg-jamendo-{track_id}",
                "dataset": "mtg_jamendo",
                "source_track_id": track_id,
                "numeric_track_id": int(track_id.rsplit("_", 1)[-1]),
                "artist_group": artist_id,
                "album_id": album_id,
                "relative_path": relative_path,
                "duration": float(duration),
                "title": public.get("TRACK_NAME") or track_id,
                "artist": public.get("ARTIST_NAME") or artist_id,
                "public_url": public.get("URL"),
                "expected_styles": expected,
                "original_genre_tags": sorted(tags),
                "annotation_source": "mtg_jamendo_uploader_tags",
                "license": licenses.get(relative_path, "source-specific Creative Commons; verify before redistribution"),
                "split": "candidate",
            })
    selected_ids = set()
    selected = []
    for style in TARGET_TAGS:
        pool = [row for row in candidates if style in row["expected_styles"]]
        pool.sort(key=lambda row: _stable_key(style, row["artist_group"], row["source_track_id"]))
        artist_seen = set()
        chosen = []
        for row in pool:
            if row["artist_group"] in artist_seen:
                continue
            chosen.append(row)
            artist_seen.add(row["artist_group"])
            if len(chosen) >= per_style:
                break
        if len(chosen) < per_style:
            for row in pool:
                if row in chosen:
                    continue
                chosen.append(row)
                if len(chosen) >= per_style:
                    break
        for row in chosen:
            if row["clip_id"] not in selected_ids:
                selected.append(row)
                selected_ids.add(row["clip_id"])
    selected.sort(key=lambda row: row["clip_id"])
    return selected


def download_candidates(rows: list[dict], output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    ready = failed = 0
    for row in rows:
        target = output_dir / f"{row['clip_id']}.mp3"
        row["local_audio"] = str(target)
        if target.is_file() and target.stat().st_size > 4096:
            ready += 1
            continue
        url = f"https://mp3d.jamendo.com/?trackid={row['numeric_track_id']}&format=mp31"
        try:
            request = Request(url, headers={"User-Agent": "HarbeatResearchBenchmark/1.0"})
            with urlopen(request, timeout=60) as response:
                payload = response.read()
            if len(payload) <= 4096 or "audio" not in response.headers.get("Content-Type", ""):
                raise ValueError("response is not a valid audio payload")
            target.write_bytes(payload)
            ready += 1
        except (OSError, ValueError) as exc:
            row["download_error"] = f"{type(exc).__name__}: {exc}"
            failed += 1
    return {"ready": ready, "failed": failed, "total": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--per-style", type=int, default=10)
    parser.add_argument("--download-dir", type=Path)
    args = parser.parse_args()
    rows = select_candidates(
        args.dataset_root / "data" / "autotagging_genre.tsv",
        args.dataset_root / "data" / "raw.meta.tsv",
        per_style=max(1, args.per_style),
        audio_licenses=args.dataset_root / "audio_licenses.txt",
    )
    summary = None
    if args.download_dir:
        summary = download_candidates(rows, args.download_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"items": len(rows), "download": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
