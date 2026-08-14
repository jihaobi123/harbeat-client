from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import analyze_audio_for_planning


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze one song for HarBeat planning.")
    parser.add_argument("audio", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--title")
    parser.add_argument("--artist")
    parser.add_argument("--require-essentia", action="store_true")
    args = parser.parse_args(argv)
    result = analyze_audio_for_planning(
        args.audio,
        title=args.title,
        artist=args.artist,
        require_essentia=args.require_essentia,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "bpm": result["analysis"]["bpm"],
        "key": result["analysis"]["key"],
        "exit_candidates": len(result["dj_structure_v2"]["track1_exit_candidates"]),
        "entry_candidates": len(result["dj_structure_v2"]["track2_entry_candidates"]),
    }, sort_keys=True))
    return 0
