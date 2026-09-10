#!/usr/bin/env python3
"""Run the Jetson same-style preprocessing pipeline for one audio file."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.same_style_preprocess import (  # noqa: E402
    PreprocessConfig,
    run_same_style_preprocess,
)


def _git_sha() -> str:
    configured = os.getenv("HARBEAT_RELEASE_GIT_SHA", "").strip()
    if configured:
        return configured
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout.strip()
    except Exception:
        marker = ROOT / "RELEASE_GIT_SHA"
        if marker.is_file():
            return marker.read_text(encoding="utf-8").strip()
        raise RuntimeError("set HARBEAT_RELEASE_GIT_SHA or deploy RELEASE_GIT_SHA")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio", type=Path)
    parser.add_argument("--track-id", required=True)
    parser.add_argument("--title")
    parser.add_argument("--artist")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.getenv("HARBEAT_PREPROCESS_ROOT", "/mnt/nas/harbeat/preprocess")),
    )
    parser.add_argument("--device", default=os.getenv("HARBEAT_PREPROCESS_DEVICE", "cuda"))
    parser.add_argument("--demucs-model", default="htdemucs")
    parser.add_argument("--allow-missing-mdx23c", action="store_true")
    args = parser.parse_args()
    config = PreprocessConfig.from_values(
        root=args.root,
        git_sha=_git_sha(),
        device=args.device,
        demucs_model=args.demucs_model,
        require_mdx23c=not args.allow_missing_mdx23c,
    )
    manifest = run_same_style_preprocess(
        args.audio,
        args.track_id,
        config=config,
        schema_path=ROOT / "contracts" / "schemas" / "analysis" / "same-style-track-preprocess-v1.schema.json",
        title=args.title,
        artist=args.artist,
    )
    print(
        json.dumps(
            {
                "track_id": manifest["track_id"],
                "analysis_run_id": manifest["analysis_run_id"],
                "status": manifest["status"],
                "root": str(config.root),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
