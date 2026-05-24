#!/usr/bin/env python3
"""Build a multi-song automix batch report from the Jetson music library."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from transition_planner import build_pair_matrix, plan_mix  # noqa: E402

STEMS = ("vocals", "drums", "bass", "other")
ENERGY_MAP = {
    "low": 0.32,
    "medium": 0.58,
    "mid": 0.58,
    "high": 0.78,
    "very_high": 0.9,
}


def _energy(value: object) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return ENERGY_MAP.get(str(value or "medium").strip().lower(), 0.58)


def _camelot(value: object) -> int:
    match = re.match(r"(\d+)", str(value or "1"))
    if not match:
        return 1
    return max(1, min(12, int(match.group(1))))


def _format_from_path(path: object) -> str:
    suffix = Path(str(path or "")).suffix.lower().lstrip(".")
    return suffix or "audio"


def _file_entry(url: str, *, fmt: str, size: object = None, sha256: object = None) -> dict:
    entry = {"url": url, "format": fmt}
    if size is not None:
        entry["size"] = size
    if sha256:
        entry["sha256"] = sha256
    return entry


def normalize_jetson_song(
    raw: dict[str, Any],
    *,
    jetson_base_url: str = "http://192.168.5.100:8000",
    assume_stems: bool = False,
) -> dict:
    sid = str(raw.get("song_id", raw.get("id", raw.get("library_song_id", ""))))
    fmt = _format_from_path(raw.get("audio_url") or raw.get("source_path") or raw.get("format"))
    base = jetson_base_url.rstrip("/")
    bpm = raw.get("bpm")
    music_features = raw.get("music_features") or {}
    if bpm is None:
        bpm = music_features.get("bpm") or music_features.get("tempo")

    cues = raw.get("cues") or music_features.get("cues") or []
    sections = raw.get("sections") or raw.get("segments") or music_features.get("sections") or music_features.get("segments") or []
    beats = raw.get("beats") or raw.get("beat_points") or music_features.get("beat_points") or []
    stem_windows = raw.get("stem_activity_windows") or music_features.get("stem_activity_windows") or sections

    return {
        "song_id": sid,
        "title": raw.get("title", ""),
        "artist": raw.get("artist", ""),
        "duration": float(raw.get("duration") or raw.get("duration_sec") or 0.0),
        "bpm": float(bpm or 120.0),
        "bpm_curve": raw.get("bpm_curve") or music_features.get("bpm_curve") or [],
        "camelot": _camelot(raw.get("camelot_key") or raw.get("camelotKey") or raw.get("key")),
        "key": raw.get("key") or raw.get("camelot_key"),
        "energy": _energy(raw.get("energy", music_features.get("energy"))),
        "tags": list(raw.get("tags") or []),
        "cues": cues,
        "sections": sections,
        "stem_activity_windows": stem_windows,
        "beats": beats[:256] if isinstance(beats, list) else [],
        "has_stems": bool(raw.get("has_stems", assume_stems)),
        "files": {
            "original": _file_entry(f"{base}/api/stream/{sid}", fmt=fmt, size=raw.get("file_size"), sha256=raw.get("sha256")),
            "stems": {
                stem: _file_entry(f"{base}/api/stream/{sid}/stem/{stem}", fmt="wav")
                for stem in STEMS
            },
        },
    }


def fetch_music_songs(jetson_base_url: str, *, limit: int) -> list[dict]:
    url = f"{jetson_base_url.rstrip()}/api/music/songs"
    with urllib.request.urlopen(url, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    songs = payload.get("data", {}).get("songs", [])
    usable = [song for song in songs if song.get("audio_url") and song.get("duration")]
    return usable[:limit]


def build_batch_report(
    songs: list[dict],
    *,
    stems_available: bool = True,
    optimize_order: bool = True,
) -> dict:
    plan = plan_mix(songs, stems_available=stems_available, optimize_order=optimize_order)
    matrix = build_pair_matrix(songs, stems_available=stems_available)
    return {
        "source": "jetson_music_library",
        "tracks": songs,
        "pair_matrix": matrix,
        "pair_matrix_summary": plan.get("pair_matrix_summary", {}),
        "mix_plan": plan,
        "renders": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a HarBeat multi-song automix batch report.")
    parser.add_argument("--jetson", default="http://192.168.5.100:8000")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--songs-json", type=Path, help="Use a local JSON list instead of Jetson /api/music/songs.")
    parser.add_argument("--out", type=Path, default=Path("/tmp/harbeat_batch_mix_report.json"))
    parser.add_argument("--no-stems", action="store_true", help="Force non-stem planning.")
    parser.add_argument("--assume-stems", action="store_true", help="Treat generated stem stream URLs as available.")
    parser.add_argument("--keep-order", action="store_true", help="Do not optimize playlist order after the first track.")
    args = parser.parse_args()

    if args.songs_json:
        raw_songs = json.loads(args.songs_json.read_text(encoding="utf-8"))
    else:
        raw_songs = fetch_music_songs(args.jetson, limit=args.limit)
    songs = [
        normalize_jetson_song(song, jetson_base_url=args.jetson, assume_stems=args.assume_stems)
        for song in raw_songs[: args.limit]
    ]
    if len(songs) < 2:
        raise SystemExit("need at least 2 usable songs with audio_url and duration")

    report = build_batch_report(
        songs,
        stems_available=not args.no_stems,
        optimize_order=not args.keep_order,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "tracks": len(report["tracks"]),
        "pairs": len(report["pair_matrix"]),
        "transitions": len(report["mix_plan"].get("transitions", [])),
        "out": str(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
