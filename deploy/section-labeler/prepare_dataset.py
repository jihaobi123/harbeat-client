#!/usr/bin/env python3
"""Create the server copy of the annotation dataset with server audio paths."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--audio-root", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.source.read_text(encoding="utf-8"))
    for track in payload.get("tracks", []):
        original = Path(str(track["audio_path"]))
        track["audio_path"] = str(args.audio_root / original.as_posix().lstrip("/"))

    args.destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.destination.with_suffix(args.destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
