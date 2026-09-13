#!/usr/bin/env python3
"""Run the Jetson same-style preprocessing pipeline for one audio file."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from preprocessing.publisher import (  # noqa: E402
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
        "--style-label",
        action="append",
        default=[],
        help="human-authored style label; repeat for multiple labels",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.getenv("HARBEAT_PREPROCESS_ROOT", "/mnt/nas/harbeat/preprocess")),
    )
    parser.add_argument("--device", default=os.getenv("HARBEAT_PREPROCESS_DEVICE", "cuda"))
    parser.add_argument("--demucs-model", default="htdemucs")
    parser.add_argument("--allow-missing-mdx23c", action="store_true")
    parser.add_argument(
        "--disable-adtof",
        action="store_true",
        help="skip the optional ADTOF event route; MDX23C drum stem separation still runs",
    )
    args = parser.parse_args()
    config = PreprocessConfig.from_values(
        root=args.root,
        git_sha=_git_sha(),
        device=args.device,
        demucs_model=args.demucs_model,
        require_mdx23c=not args.allow_missing_mdx23c,
        use_adtof=not args.disable_adtof,
    )
    manifest = run_same_style_preprocess(
        args.audio,
        args.track_id,
        config=config,
        schema_path=ROOT / "contracts" / "schemas" / "analysis" / "same-style-track-preprocess-v1.schema.json",
        title=args.title,
        artist=args.artist,
        style_labels=args.style_label,
    )
    # Additive contract: do not change the immutable base manifest or its hash.
    # Reusing an existing base run still completes/retries this independent stage.
    from preprocessing.vocal_activity import publish_vocal_activity
    manifest_key = (
        f"published/tracks/{manifest['track_id']}/runs/"
        f"{manifest['analysis_run_id']}/manifest.json"
    )
    vocal_pointer = publish_vocal_activity(config.root, manifest_key)
    print(
        json.dumps(
            {
                "track_id": manifest["track_id"],
                "analysis_run_id": manifest["analysis_run_id"],
                "status": manifest["status"],
                "root": str(config.root),
                "vocal_activity": vocal_pointer,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
