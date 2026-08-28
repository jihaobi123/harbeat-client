#!/usr/bin/env python3
"""Recompute stem features and styles while reusing saved core analysis and stems."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.high_frequency_style_classifier import classify_high_frequency_styles  # noqa: E402
from app.modules.library.stem_analysis import analyze_stem_files  # noqa: E402


REQUIRED_STEMS = ("vocals", "drums", "bass", "other")


def _write_checkpoint(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _reanalyze(track: dict) -> dict:
    source = track.get("file")
    stems = track.get("stems") or {}
    missing = [name for name in REQUIRED_STEMS if not Path(str(stems.get(name, ""))).is_file()]
    if not source or not Path(source).is_file():
        raise FileNotFoundError(f"source audio unavailable: {source}")
    if missing:
        raise FileNotFoundError(f"saved stems unavailable: {', '.join(missing)}")
    core = track.get("core") or {}
    started = time.monotonic()
    stem_analysis = analyze_stem_files(
        stems,
        original_path=source,
        bpm=float(core.get("bpm", 0.0) or 0.0),
        beat_points=list(core.get("beat_points") or []),
        downbeats=list(core.get("downbeats") or []),
        key_profile=dict(core.get("key_profile") or {}),
    )
    updated = deepcopy(track)
    updated["status"] = "completed"
    updated["reanalyzed_elapsed_sec"] = round(time.monotonic() - started, 3)
    updated["stem_analysis"] = stem_analysis
    updated["style_analysis"] = classify_high_frequency_styles(stem_analysis.get("feature_analysis"))
    updated.pop("error", None)
    return updated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_results", type=Path)
    parser.add_argument("output_results", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    payload = json.loads(args.source_results.read_text(encoding="utf-8"))
    payload["reanalyzed_from"] = str(args.source_results.resolve())
    payload["reanalyzed_at"] = datetime.now(timezone.utc).isoformat()
    tracks = payload.get("tracks") or []
    selected = tracks[: args.limit] if args.limit > 0 else tracks
    failures = 0
    for index, track in enumerate(selected, start=1):
        title = track.get("title") or Path(track.get("file", "unknown")).stem
        print(f"[{index}/{len(selected)}] reanalyzing: {title}", flush=True)
        try:
            replacement = _reanalyze(track)
            top = ((replacement.get("style_analysis") or {}).get("primary_style_candidate") or {})
            print(
                f"[{index}/{len(selected)}] completed in {replacement['reanalyzed_elapsed_sec']:.1f}s: "
                f"{top.get('style_id', 'none')}={float(top.get('score', 0.0)):.3f}",
                flush=True,
            )
        except Exception as exc:
            failures += 1
            replacement = deepcopy(track)
            replacement["status"] = "error"
            replacement["error"] = f"{type(exc).__name__}: {exc}"
            print(f"[{index}/{len(selected)}] failed: {replacement['error']}", flush=True)
        tracks[index - 1] = replacement
        _write_checkpoint(args.output_results, payload)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
