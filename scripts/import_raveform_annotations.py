#!/usr/bin/env python3
"""Convert local Raveform JSON metadata to HarBeat AnnotationRecord JSONL."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.modules.annotations.public_datasets import convert_raveform_track  # noqa: E402


def _track_payloads(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        tracks = payload
        inherited: dict[str, Any] = {}
    elif isinstance(payload, dict) and isinstance(payload.get("tracks"), list):
        tracks = payload["tracks"]
        inherited = {
            key: payload[key]
            for key in ("dataset", "source_version")
            if key in payload
        }
    elif isinstance(payload, dict):
        return [payload]
    else:
        raise ValueError("input must be one track, a track list, or an object with tracks")

    result: list[dict[str, Any]] = []
    for track in tracks:
        if not isinstance(track, dict):
            raise ValueError("every Raveform track must be a JSON object")
        result.append({**inherited, **track})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert local Raveform section metadata; no audio is downloaded."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--created-at", default=None)
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    records = [
        record
        for track in _track_payloads(payload)
        for record in convert_raveform_track(
            track,
            args.dataset_version,
            created_at=args.created_at,
        )
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records)
    args.output.write_text(content, encoding="utf-8")
    print(f"wrote {len(records)} candidate records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
