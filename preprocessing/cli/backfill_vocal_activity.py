#!/usr/bin/env python3
"""Resume Silero-only backfill from a frozen or live published library index."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from preprocessing.vocal_activity import SileroDetector, publish_vocal_activity, storage_path
from preprocessing.publisher import _atomic_json, _track_lock, _utc_now


def backfill(root: Path, index_key: str, output_key: str, *, detector=None, workers: int = 1) -> dict:
    # Distinct outputs for EDM snapshot and complete library; never rewrite source.
    if index_key == output_key:
        raise ValueError("output index must differ from source")
    if workers not in range(1, 5) or (detector is not None and workers != 1):
        raise ValueError("use 1-4 workers; injected detector requires one worker")
    index = json.loads(storage_path(root, index_key).read_text())
    output = storage_path(root, output_key)
    import hashlib
    with _track_lock(root, "vocal-index-" + hashlib.sha256(output_key.encode()).hexdigest()[:24], 21600):
        local = threading.local()
        model_lock = threading.Lock()
        items = []
        summary = {}

        def analyze(item):
            result = {"track_id": item["track_id"], "analysis_run_id": item.get("analysis_run_id"),
                      "title": item.get("title"), "style_labels": item.get("style_labels", [])}
            try:
                # Silero has recurrent state: never share one instance across songs
                # being inferred concurrently. Each worker owns its own model.
                if not hasattr(local, "detector"):
                    with model_lock:
                        local.detector = detector or SileroDetector()
                if not item.get("manifest_storage_key"):
                    raise ValueError("no published base analysis")
                manifest = json.loads(storage_path(root, item["manifest_storage_key"]).read_text())
                if (manifest["track_id"], manifest["analysis_run_id"]) != (item["track_id"], item["analysis_run_id"]):
                    raise ValueError("index and manifest identity mismatch")
                result.update(publish_vocal_activity(root, item["manifest_storage_key"], detector=local.detector))
                result["error"] = None
            except Exception as exc:
                result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            return result

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for i, result in enumerate(pool.map(analyze, index["items"]), 1):
                items.append(result)
                summary = {"schema_name": "harbeat_vocal_activity_index", "schema_version": "1.0.0",
                           "generated_at": _utc_now(), "source_index_storage_key": index_key,
                           "total_tracks": len(index["items"]), "processed_tracks": len(items),
                           "status_summary": dict(Counter(x["status"] for x in items)), "items": items}
                _atomic_json(output, summary)
                print(f"[{i}/{len(index['items'])}] {result['track_id']} {result['status']} {result['error'] or ''}", flush=True)
        return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/mnt/nas/harbeat/preprocess"))
    parser.add_argument("--index", default="published/indexes/style_library_v1.json")
    parser.add_argument("--output", default="published/indexes/style_library_vocal_activity_v1.json")
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=3)
    args = parser.parse_args()
    result = backfill(args.root.resolve(), args.index, args.output, workers=args.workers)
    print(json.dumps({k: v for k, v in result.items() if k != "items"}, ensure_ascii=False))
    return 2 if result.get("status_summary", {}).get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())
