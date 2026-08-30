#!/usr/bin/env python3
"""Audit the current 808 identity rule on canonical drum-machine samples.

The Open Drums repository contains recordings from real TR-808, TR-909 and
TR-707 machines.  This evaluator deliberately exercises the production bass
feature analyser instead of a second benchmark-only implementation.

This benchmark can reject a weak identity rule, but it cannot validate a
general modern-808 detector: the positive files are parameter variations from
one source machine and do not cover tuning, distortion, layering or melodic
use in released mixes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable

import librosa
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.bass_feature_analysis import analyze_bass_features  # noqa: E402
from app.modules.library.benchmark_evaluation import binary_metrics  # noqa: E402


def discover_samples(dataset_root: Path) -> list[dict[str, Any]]:
    """Return the fixed positive and hard-negative sample inventory."""
    positive = sorted((dataset_root / "tr-808" / "TR808WAV" / "BD").glob("*.WAV"))
    tr909 = sorted((dataset_root / "tr-909" / "TR909all").glob("BT*.WAV"))
    tr707_root = dataset_root / "tr-707" / "TR707WAV"
    tr707 = [tr707_root / "BassDrum1.wav", tr707_root / "BassDrum2.wav"]
    tr707 = [path for path in tr707 if path.is_file()]
    return [
        *({"path": path, "expected": True, "source": "TR-808"} for path in positive),
        *({"path": path, "expected": False, "source": "TR-909"} for path in tr909),
        *({"path": path, "expected": False, "source": "TR-707"} for path in tr707),
    ]


def repeated_sample(
    path: Path,
    *,
    target_sr: int = 22_050,
    duration_seconds: float = 10.0,
    interval_seconds: float = 0.75,
) -> tuple[np.ndarray, list[float]]:
    """Build a deterministic repeated-kick excerpt suitable for song analysis."""
    sample, _ = librosa.load(path, sr=target_sr, mono=True)
    sample = np.asarray(sample, dtype=np.float32)
    peak = float(np.max(np.abs(sample))) if len(sample) else 0.0
    if peak > 0:
        sample = sample / peak * 0.8
    output = np.zeros(int(round(duration_seconds * target_sr)), dtype=np.float32)
    onsets = np.arange(0.5, duration_seconds - 0.25, interval_seconds, dtype=float)
    for onset in onsets:
        start = int(round(float(onset) * target_sr))
        end = min(len(output), start + len(sample))
        output[start:end] += sample[: end - start]
    output = np.clip(output, -1.0, 1.0)
    return output, [float(value) for value in onsets]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    metrics = binary_metrics(
        (bool(row["expected"]) for row in rows),
        (bool(row["predicted"]) for row in rows),
    )
    reasons = []
    if metrics["positive_count"] < 20 or metrics["negative_count"] < 20:
        reasons.append("insufficient_sample_support")
    for name in ("accuracy", "precision", "recall", "f1"):
        if float(metrics[name]) < 0.80:
            reasons.append(f"{name}_below_0_80")
    # Parameter settings from one source instrument are correlated observations,
    # not independent positive devices.  Keep the result audit-only even if a
    # future hand-written rule happens to fit this pack perfectly.
    reasons.append("single_positive_source_machine_cannot_validate_general_808_identity")
    return {
        "metrics": metrics,
        "release_gate": {
            "passed": False,
            "reasons": reasons,
            "minimum_accuracy_precision_recall_f1": 0.80,
        },
    }


def evaluate_dataset(
    dataset_root: Path,
    *,
    analyser: Callable[..., dict[str, Any]] = analyze_bass_features,
) -> dict[str, Any]:
    inventory = discover_samples(dataset_root)
    if not inventory:
        raise FileNotFoundError(f"no Open Drums samples found below {dataset_root}")
    rows = []
    for index, item in enumerate(inventory, start=1):
        audio, onsets = repeated_sample(item["path"])
        drum_analysis = {
            "status": "ready",
            "events": {
                "kick": [
                    {"time": value, "confidence": 1.0, "subtype": "annotated_kick"}
                    for value in onsets
                ]
            },
        }
        result = analyser(
            audio,
            audio,
            22_050,
            drum_analysis=drum_analysis,
            original_audio=audio,
        )
        feature = result["features"]["808_timbre_candidate"]
        rows.append({
            "file": str(item["path"].relative_to(dataset_root)),
            "source": item["source"],
            "expected": bool(item["expected"]),
            "predicted": bool(feature.get("detected")),
            "score": round(float(feature.get("score", 0.0)), 4),
            "threshold": feature.get("decision_threshold"),
        })
        print(f"[{index}/{len(inventory)}] {item['source']} {item['path'].name}", file=sys.stderr)
    summary = summarize(rows)
    return {
        "benchmark": "Open Drums canonical drum-machine bass-drum audit",
        "source_repository": "https://github.com/fluid-music/open-drums",
        "protocol": "production_analyser,repeated_10s_events,TR808_positive,TR909_TR707_negative",
        "claim_scope": "reject_current_rule_only_not_general_808_validation",
        "feature": "low_frequency.808_timbre_candidate",
        "sample_count_by_source": {
            source: sum(row["source"] == source for row in rows)
            for source in sorted({row["source"] for row in rows})
        },
        **summary,
        "samples": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate_dataset(args.dataset_root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
