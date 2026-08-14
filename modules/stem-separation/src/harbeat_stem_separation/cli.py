"""Command-line entry point for standalone four-stem separation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .runner import SubprocessDemucsRunner
from .separator import StemSeparationError, StemSeparator, separation_result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Separate one audio file into four Demucs stems.")
    parser.add_argument("audio_path")
    parser.add_argument("output_root")
    parser.add_argument("--model", default="htdemucs")
    parser.add_argument("--model-repo", type=Path)
    parser.add_argument("--timeout-sec", type=int, default=120)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runner = SubprocessDemucsRunner(model_repo=args.model_repo) if args.model_repo else None
    separator = StemSeparator(model=args.model, timeout_sec=args.timeout_sec, runner=runner)
    try:
        stems = separator.separate(args.audio_path, args.output_root)
        result = separation_result("separated", stems)
    except StemSeparationError as exc:
        result = separation_result("failed", error=str(exc))

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
