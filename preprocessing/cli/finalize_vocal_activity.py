#!/usr/bin/env python3
"""Validate a completed vocal batch and export a timestamped JSON-only bundle."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from preprocessing.cli.validate_vocal_activity import validate
from preprocessing.cli.export_vocal_activity_bundle import export_bundle
from preprocessing.publisher import _atomic_json


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/mnt/nas/harbeat/preprocess"))
    parser.add_argument("--index", default="published/indexes/style_library_vocal_activity_v1.json")
    args = parser.parse_args()
    root = args.root.resolve()
    report = validate(root, args.index)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    report_path = root / "reports" / "vocal_activity" / f"validation_{stamp}.json"
    _atomic_json(report_path, report)
    destination = root.parent / "exports" / f"{Path(args.index).stem}_{stamp}.zip"
    bundle = export_bundle(root, args.index, destination)
    receipt = {"status": "ready", "validated_tracks": report["validated_tracks"],
               "interval_count": report["interval_count"], "accuracy_evaluated": False,
               "validation_report": str(report_path), "bundle": bundle}
    # Operational receipt, separate from immutable marker and audio assets.
    _atomic_json(root / "reports/vocal_activity/latest_delivery.json", receipt)
    print(json.dumps(receipt, ensure_ascii=False))
