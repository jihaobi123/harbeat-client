#!/usr/bin/env python3
"""Preflight a section-label dataset before training."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.section_relabel_dataset import (
    DatasetValidationError,
    validate_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--require-audio", action="store_true")
    parser.add_argument("--require-development-complete", action="store_true")
    parser.add_argument("--require-test-complete", action="store_true")
    parser.add_argument("--include-low-confidence", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = args.dataset.expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        required = tuple(
            split
            for split, enabled in (
                ("development", args.require_development_complete),
                ("test", args.require_test_complete),
            )
            if enabled
        )
        report = validate_dataset(
            payload,
            require_audio=args.require_audio,
            require_complete_splits=required,
            include_low_confidence=args.include_low_confidence,
        )
    except (OSError, json.JSONDecodeError, DatasetValidationError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"status": "valid", **report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
