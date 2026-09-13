#!/usr/bin/env python3
"""Validate marker delivery contracts and binding; this is not an accuracy test."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "vendor"))
import jsonschema
from preprocessing.vocal_activity import storage_path
from preprocessing.publisher import _atomic_json, _sha256, _utc_now


def validate(root: Path, index_key: str) -> dict:
    index = json.loads(storage_path(root, index_key).read_text())
    if index["processed_tracks"] != index["total_tracks"] or len(index["items"]) != index["total_tracks"]:
        raise ValueError("incomplete index")
    schema = json.loads((ROOT / "contracts/schemas/analysis/vocal-activity-v1.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    rows = []
    identities = set()
    for item in index["items"]:
        if item["status"] != "ready":
            raise ValueError(f"not ready: {item['track_id']}")
        identity = item["track_id"], item["analysis_run_id"]
        if identity in identities:
            raise ValueError("duplicate track/run identity")
        identities.add(identity)
        report_path = storage_path(root, item["vocal_activity_storage_key"])
        if _sha256(report_path) != item["vocal_activity_sha256"]:
            raise ValueError("report hash mismatch")
        if json.loads((report_path.parent / "_SUCCESS.json").read_text())["vocal_activity_sha256"] != item["vocal_activity_sha256"]:
            raise ValueError("report success marker mismatch")
        report = json.loads(report_path.read_text())
        validator.validate(report)
        if any(report["source"][key] != item[key] for key in report["source"]):
            raise ValueError("report input binding differs from index")
        base_path = storage_path(root, item["manifest_storage_key"])
        if _sha256(base_path) != item["manifest_sha256"]:
            raise ValueError("base manifest hash mismatch")
        base = json.loads(base_path.read_text())
        if (base["track_id"], base["analysis_run_id"]) != identity:
            raise ValueError("base identity mismatch")
        if json.loads((base_path.parent / "_SUCCESS.json").read_text())["manifest_sha256"] != item["manifest_sha256"]:
            raise ValueError("base success marker mismatch")
        stem = base["assets"]["stems"]["vocals"]
        if (stem["storage_key"], stem["sha256"]) != (item["vocal_storage_key"], item["vocal_sha256"]):
            raise ValueError("vocal source binding mismatch")
        spans = report["intervals"]
        if not all(0 <= s["start_ms"] < s["end_ms"] <= report["duration_ms"] for s in spans):
            raise ValueError("invalid interval bounds")
        if not all(a["end_ms"] <= b["start_ms"] for a, b in zip(spans, spans[1:])):
            raise ValueError("intervals overlap or are unsorted")
        active = sum(s["end_ms"] - s["start_ms"] for s in spans)
        if active != report["active_duration_ms"] or bool(spans) != report["has_vocals"]:
            raise ValueError("invalid duration summary")
        if abs(active / report["duration_ms"] - report["coverage_ratio"]) > 1e-12:
            raise ValueError("invalid coverage ratio")
        rows.append({"track_id": item["track_id"], "title": item.get("title"),
                     "style_labels": item.get("style_labels", []), "interval_count": len(spans),
                     "duration_ms": report["duration_ms"], "active_duration_ms": active,
                     "coverage_ratio": report["coverage_ratio"]})
    return {"validated_at": _utc_now(), "source_index": index_key, "validated_tracks": len(rows),
            "style_counts": dict(Counter(label for row in rows for label in row["style_labels"])),
            "interval_count": sum(row["interval_count"] for row in rows),
            "accuracy_evaluated": False, "items": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--index", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate(args.root.resolve(), args.index)
    if args.output:
        _atomic_json(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k != "items"}, ensure_ascii=False))
