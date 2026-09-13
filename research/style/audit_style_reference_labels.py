#!/usr/bin/env python3
"""Audit reference identities/tags against MusicBrainz without model leakage."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

import httpx


USER_AGENT = "HarBeat-style-reference-audit/1.0 (https://github.com/jihaobi123/harbeat-client)"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _labels(recording: dict[str, Any]) -> list[str]:
    labels = []
    for key in ("genres", "tags"):
        for item in recording.get(key) or []:
            name = item.get("name") if isinstance(item, dict) else item
            if name and str(name).casefold() not in {label.casefold() for label in labels}:
                labels.append(str(name))
    return labels


def _matched_artist(recording: dict[str, Any]) -> str:
    names = []
    for credit in recording.get("artist-credit") or []:
        if not isinstance(credit, dict):
            continue
        name = (credit.get("artist") or {}).get("name") or credit.get("name")
        if name:
            names.append(str(name))
    return ", ".join(names)


def _fetch(client: httpx.Client, track: dict[str, Any]) -> dict[str, Any]:
    query = f'recording:"{track["title"]}" AND artist:"{track["primary_artist"]}"'
    response = None
    for attempt in range(4):
        response = client.get(
            "https://musicbrainz.org/ws/2/recording",
            params={"query": query, "fmt": "json", "limit": "1"},
        )
        if response.status_code not in {429, 502, 503, 504}:
            break
        if attempt < 3:
            retry_after = float(response.headers.get("Retry-After") or 0.0)
            time.sleep(max(retry_after, 2.0 * (attempt + 1)))
    assert response is not None
    response.raise_for_status()
    recordings = response.json().get("recordings") or []
    if not recordings:
        return {
            "status": "miss", "identity_score": 0.0, "matched_title": None,
            "matched_artist": None, "mbid": None, "external_labels": [],
        }
    best = recordings[0]
    score = float(best.get("score") or 0.0) / 100.0
    labels = _labels(best)
    status = "identity_confirmed" if score >= 0.80 else "identity_needs_review"
    if score >= 0.80 and labels:
        status = "identity_and_tags"
    return {
        "status": status,
        "identity_score": score,
        "matched_title": best.get("title"),
        "matched_artist": _matched_artist(best),
        "mbid": best.get("id"),
        "external_labels": labels,
        "result_count": len(recordings),
    }


def _render_report(rows: list[dict[str, Any]]) -> str:
    statuses = Counter(row["status"] for row in rows)
    tagged = [row for row in rows if row.get("external_labels")]
    lines = [
        "# MusicBrainz 外部标签与身份审计",
        "",
        f"> 生成时间：{datetime.now(timezone.utc).isoformat()}",
        "",
        "## 边界",
        "",
        "- 该审计只核对艺人/曲名身份并收集公开 tag；不进入模型输入。",
        "- MusicBrainz 未提供细分风格不代表文件夹标签错误，因此缺失 tag 不判冲突。",
        "- Remix/Edit/Instrumental 和低匹配分数仍需人工确认具体发行版本。",
        "",
        "## 汇总",
        "",
        f"- 审计歌曲：{len(rows)}；含公开 tag：{len(tagged)}。",
    ]
    for status, count in sorted(statuses.items()):
        lines.append(f"- `{status}`：{count} 首。")
    lines.extend([
        "",
        "详细逐曲结果见 `external_label_audit.csv`。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--interval", type=float, default=1.1)
    args = parser.parse_args()
    dataset_dir = args.dataset_dir.resolve()
    manifest = _read_jsonl(dataset_dir / "manifest.jsonl")
    cache_dir = dataset_dir / "external" / "musicbrainz"
    cache_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=15.0, headers={"User-Agent": USER_AGENT}) as client:
        for index, track in enumerate(manifest, start=1):
            path = cache_dir / f"{track['track_id']}.json"
            if args.resume and path.is_file():
                cached = json.loads(path.read_text(encoding="utf-8"))
                if cached.get("status") != "error":
                    print(f"[{index}/{len(manifest)}] skip {track['track_id']}", flush=True)
                    continue
            started = time.monotonic()
            try:
                result = _fetch(client, track)
            except Exception as exc:
                result = {
                    "status": "error", "identity_score": 0.0,
                    "matched_title": None, "matched_artist": None,
                    "mbid": None, "external_labels": [],
                    "error": f"{type(exc).__name__}: {exc}",
                }
            payload = {
                "track_id": track["track_id"],
                "primary_style": track["primary_style"],
                "query_artist": track["primary_artist"],
                "query_title": track["title"],
                "source": "musicbrainz_recording_search",
                **result,
            }
            _atomic_json(path, payload)
            print(
                f"[{index}/{len(manifest)}] {track['track_id']}: "
                f"{result['status']} score={result['identity_score']:.2f}", flush=True,
            )
            time.sleep(max(0.0, args.interval - (time.monotonic() - started)))
    rows = [
        json.loads((cache_dir / f"{track['track_id']}.json").read_text(encoding="utf-8"))
        for track in manifest
    ]
    reports = dataset_dir / "reports"
    with (reports / "external_label_audit.csv").open(
        "w", encoding="utf-8-sig", newline="",
    ) as handle:
        fields = [
            "track_id", "primary_style", "query_artist", "query_title", "status",
            "identity_score", "matched_artist", "matched_title", "mbid",
            "external_labels", "error",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                key: json.dumps(row.get(key), ensure_ascii=False)
                if isinstance(row.get(key), (list, dict)) else row.get(key)
                for key in fields
            })
    (reports / "external_label_audit.md").write_text(
        _render_report(rows), encoding="utf-8",
    )
    print(json.dumps({
        "status": "ready",
        "tracks": len(rows),
        "statuses": Counter(row["status"] for row in rows),
        "tagged_tracks": sum(bool(row.get("external_labels")) for row in rows),
    }, ensure_ascii=False, default=dict), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
