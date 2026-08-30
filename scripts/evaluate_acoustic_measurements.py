#!/usr/bin/env python3
"""Analytical validation for objective acoustic measurements.

The benchmark validates numerical DSP quantities, not perceptual words such as
bright, dark, lo-fi or distorted.  Those semantic features require separately
annotated listening data.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.acoustic_measurement_analysis import (  # noqa: E402
    analyze_acoustic_measurements,
)


def _fraction(values: list[bool]) -> float:
    return float(np.mean(values)) if values else 0.0


def evaluate(*, sample_rate: int = 44_100, duration_seconds: float = 2.0) -> dict[str, Any]:
    length = int(round(sample_rate * duration_seconds))
    time = np.arange(length, dtype=float) / sample_rate
    frequencies = np.geomspace(55.0, 8000.0, 64)
    rows = []
    for frequency in frequencies:
        audio = 0.5 * np.sin(2.0 * np.pi * frequency * time)
        result = analyze_acoustic_measurements(audio, sample_rate)
        centroid = float(result["spectral_centroid_hz"])
        zcr_hz = float(result["zero_crossing_rate"]) * sample_rate / 2.0
        rows.append({
            "frequency_hz": float(frequency),
            "centroid_hz": centroid,
            "centroid_within_tolerance": bool(
                abs(centroid - frequency) <= max(25.0, 0.03 * frequency)
            ),
            "zcr_frequency_hz": zcr_hz,
            "zcr_within_tolerance": bool(
                abs(zcr_hz - frequency) <= max(12.0, 0.06 * frequency)
            ),
            "crest_factor_within_tolerance": bool(
                abs(float(result["crest_factor"]) - np.sqrt(2.0)) <= 0.03
            ),
            "high_band_correct": bool(
                float(result["high_frequency_energy_ratio"]) <= 0.05
                if frequency <= 1700.0
                else float(result["high_frequency_energy_ratio"]) >= 0.90
                if frequency >= 2400.0
                else True
            ),
        })

    clipping_rows = []
    for ratio in np.linspace(0.0, 0.5, 21):
        audio = np.full(length, 0.25, dtype=float)
        count = int(round(ratio * length))
        audio[:count] = 1.0
        measured = float(analyze_acoustic_measurements(audio, sample_rate)["clipping_candidate_ratio"])
        clipping_rows.append({
            "expected": float(count / length),
            "measured": measured,
            "within_tolerance": bool(abs(measured - count / length) <= 1.0 / length),
        })

    metrics = {
        "sine_sample_count": len(rows),
        "clipping_sample_count": len(clipping_rows),
        "centroid_within_tolerance_fraction": round(_fraction([
            row["centroid_within_tolerance"] for row in rows
        ]), 4),
        "zcr_within_tolerance_fraction": round(_fraction([
            row["zcr_within_tolerance"] for row in rows
        ]), 4),
        "crest_factor_within_tolerance_fraction": round(_fraction([
            row["crest_factor_within_tolerance"] for row in rows
        ]), 4),
        "high_band_classification_accuracy": round(_fraction([
            row["high_band_correct"] for row in rows
        ]), 4),
        "clipping_ratio_within_tolerance_fraction": round(_fraction([
            row["within_tolerance"] for row in clipping_rows
        ]), 4),
    }
    names = [name for name in metrics if name.endswith(("fraction", "accuracy"))]
    failures = [name for name in names if float(metrics[name]) < 0.80]
    return {
        "benchmark": "analytical deterministic signal measurement audit",
        "validation_scope": "objective_DSP_measurements_only_not_perceptual_semantics",
        "metrics": metrics,
        "release_gate": {
            "passed": not failures,
            "minimum_within_tolerance_fraction": 0.80,
            "reasons": [f"{name}_below_0_80" for name in failures],
        },
        "sine_rows": rows,
        "clipping_rows": clipping_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate()
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
