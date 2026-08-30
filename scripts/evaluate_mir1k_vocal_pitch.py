#!/usr/bin/env python3
"""Validate the production pYIN vocal-pitch chain on MIR-1K.

MIR-1K provides an isolated vocal channel, 20 ms frame-wise MIDI-pitch
annotations, and vocal/non-vocal activity labels.  This evaluator measures the
same pYIN, probability gate, RMS activity gate, range, contiguous pitch motion,
and sustain definitions used by the pre-style feature pipeline.

The claim is deliberately limited to isolated vocals.  Rap/singing identity
and a mixture-to-Demucs-to-pitch chain require separate annotations/tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import librosa
import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.benchmark_evaluation import binary_metrics  # noqa: E402
from app.modules.library.vocal_pitch_analysis import (  # noqa: E402
    HOP_LENGTH,
    analyze_vocal_pitch,
    vocal_pitch_descriptors,
    vocal_pitch_view,
)


BENCHMARK_NAME = "MIR-1K"
ARCHIVE_MD5 = "1810d01457ccbb84a0b41c4da53eee74"
TARGET_SAMPLE_RATE = 22_050
REFERENCE_HOP_SECONDS = 0.020


def song_group(stem: str) -> str:
    """Keep clips from one karaoke song on the same deterministic split."""
    return stem.rsplit("_", 1)[0]


def split_for(stem: str) -> str:
    digest = hashlib.sha256(song_group(stem).encode("utf-8")).digest()
    return "calibration" if digest[0] < 128 else "heldout"


def load_reference(root: Path, stem: str) -> tuple[np.ndarray, np.ndarray]:
    pitch = np.atleast_1d(np.loadtxt(root / "PitchLabel" / f"{stem}.pv", dtype=float))
    activity = np.atleast_1d(
        np.loadtxt(root / "vocal-nonvocalLabel" / f"{stem}.vocal", dtype=float)
    )
    length = min(len(pitch), len(activity))
    return pitch[:length], activity[:length] > 0


def estimate_production_pitch(audio: np.ndarray, sr: int) -> dict[str, Any]:
    audio = librosa.resample(
        np.asarray(audio, dtype=float), orig_sr=sr, target_sr=TARGET_SAMPLE_RATE,
    ) if sr != TARGET_SAMPLE_RATE else np.asarray(audio, dtype=float)
    return analyze_vocal_pitch(audio, TARGET_SAMPLE_RATE)


def align_to_reference(
    values: np.ndarray, reference_length: int, *, fill_value: float = 0.0,
) -> np.ndarray:
    if reference_length <= 0:
        return np.asarray([], dtype=float)
    if len(values) == 0:
        return np.full(reference_length, fill_value, dtype=float)
    times = (np.arange(reference_length, dtype=float) + 1.0) * REFERENCE_HOP_SECONDS
    indices = np.rint(times * TARGET_SAMPLE_RATE / HOP_LENGTH).astype(int)
    indices = np.clip(indices, 0, len(values) - 1)
    return np.asarray(values)[indices]


def _metric_pair(expected: list[bool], predicted: list[bool]) -> dict[str, Any]:
    return binary_metrics(expected, predicted)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    reference_voiced = np.concatenate([row["reference_voiced"] for row in rows])
    predicted_voiced = np.concatenate([row["predicted_voiced"] for row in rows])
    correct_pitch = np.concatenate([row["correct_pitch"] for row in rows])
    frame_metrics = _metric_pair(reference_voiced.tolist(), predicted_voiced.tolist())
    raw_pitch_accuracy = float(np.sum(correct_pitch) / max(np.sum(reference_voiced), 1))
    overall_accuracy = float(np.mean(
        correct_pitch | (~reference_voiced & ~predicted_voiced)
    ))

    descriptor_specs = {
        "pitch_range_semitones": {"threshold": 6.0, "tolerance": 2.0},
        "median_100ms_contiguous_motion_semitones": {"threshold": 1.0, "tolerance": 0.5},
        "pitch_sustain_ratio": {"threshold": 0.55, "tolerance": 0.15},
        "melodic_contour_score": {"threshold": 0.55, "tolerance": 0.15},
    }
    descriptors = {}
    for name, spec in descriptor_specs.items():
        expected_values = np.asarray([row["reference_descriptors"][name] for row in rows])
        predicted_values = np.asarray([row["predicted_descriptors"][name] for row in rows])
        errors = np.abs(expected_values - predicted_values)
        decisions = _metric_pair(
            (expected_values >= spec["threshold"]).tolist(),
            (predicted_values >= spec["threshold"]).tolist(),
        )
        descriptors[name] = {
            "definition_threshold": spec["threshold"],
            "absolute_error_tolerance": spec["tolerance"],
            "mean_absolute_error": round(float(np.mean(errors)), 4),
            "within_tolerance_fraction": round(
                float(np.mean(errors <= spec["tolerance"])), 4,
            ),
            "decision_metrics": decisions,
        }

    pitch_range_metrics = descriptors["pitch_range_semitones"]
    pitch_range_decision = pitch_range_metrics["decision_metrics"]
    contour_metrics = descriptors["melodic_contour_score"]
    contour_decision = contour_metrics["decision_metrics"]
    feature_release_gates = {
        "vocal_pitch_frame_track": {
            "passed": bool(
                frame_metrics["f1"] >= 0.80
                and raw_pitch_accuracy >= 0.80
                and overall_accuracy >= 0.80
            ),
            "scope": "isolated_vocal_frame_pitch_at_50_cent",
        },
        "vocal_pitch_range": {
            "passed": bool(
                pitch_range_decision["positive_count"] >= 10
                and pitch_range_decision["negative_count"] >= 10
                and pitch_range_decision["accuracy"] >= 0.80
                and pitch_range_decision["precision"] >= 0.80
                and pitch_range_decision["recall"] >= 0.70
                and pitch_range_decision["f1"] >= 0.80
                and pitch_range_metrics["within_tolerance_fraction"] >= 0.80
            ),
            "scope": "isolated_vocal_p90_minus_p10_pitch_range",
        },
        "pitch_sustain_ratio": {
            "passed": bool(
                descriptors["pitch_sustain_ratio"]["within_tolerance_fraction"] >= 0.80
            ),
            "scope": "isolated_vocal_continuous_ratio_with_absolute_tolerance_0_15",
        },
        "melodic_contour": {
            "passed": bool(
                contour_decision["positive_count"] >= 10
                and contour_decision["negative_count"] >= 10
                and contour_decision["accuracy"] >= 0.80
                and contour_decision["precision"] >= 0.80
                and contour_decision["recall"] >= 0.70
                and contour_decision["f1"] >= 0.80
            ),
            "scope": "range_plus_100ms_motion_rule_only",
        },
    }

    gate_reasons = []
    if len(rows) < 50:
        gate_reasons.append("fewer_than_50_heldout_clips")
    if raw_pitch_accuracy < 0.80:
        gate_reasons.append("raw_pitch_accuracy_below_0_80")
    if overall_accuracy < 0.80:
        gate_reasons.append("overall_accuracy_below_0_80")
    for name, values in descriptors.items():
        metrics = values["decision_metrics"]
        if metrics["positive_count"] >= 10 and metrics["negative_count"] >= 10:
            if metrics["accuracy"] < 0.80 or metrics["f1"] < 0.80:
                gate_reasons.append(f"{name}_decision_below_0_80")
        elif values["within_tolerance_fraction"] < 0.80:
            gate_reasons.append(f"{name}_continuous_agreement_below_0_80")
    return {
        "frame_metrics": {
            **frame_metrics,
            "raw_pitch_accuracy_50_cent": round(raw_pitch_accuracy, 4),
            "overall_accuracy_50_cent": round(overall_accuracy, 4),
        },
        "descriptor_metrics": descriptors,
        "feature_release_gates": feature_release_gates,
        "release_gate": {
            "passed": not gate_reasons,
            "reasons": gate_reasons,
            "claim_scope": "isolated_vocal_channel_to_pitch_descriptors",
        },
    }


def _selection_score(summary: dict[str, Any]) -> float:
    frame = summary["frame_metrics"]
    descriptor = summary["descriptor_metrics"]
    components = [
        frame["f1"],
        frame["raw_pitch_accuracy_50_cent"],
        frame["overall_accuracy_50_cent"],
        descriptor["pitch_range_semitones"]["decision_metrics"]["f1"],
        descriptor["pitch_sustain_ratio"]["within_tolerance_fraction"],
        descriptor["melodic_contour_score"]["decision_metrics"]["f1"],
    ]
    return float(min(components))


def evaluate(
    root: Path,
    *,
    split: str,
    limit: int | None = None,
    thresholds: tuple[float, ...] = (0.10,),
    vocal_stem_root: Path | None = None,
) -> dict[str, Any]:
    paths = sorted(
        (root / "Wavfile").glob("*.wav"),
        key=lambda path: hashlib.sha256(path.stem.encode("utf-8")).hexdigest(),
    )
    if split != "all":
        paths = [path for path in paths if split_for(path.stem) == split]
    if limit is not None:
        paths = paths[:max(0, limit)]
    normalized_thresholds = tuple(sorted({float(value) for value in thresholds}))
    if not normalized_thresholds or any(not 0.0 <= value <= 1.0 for value in normalized_thresholds):
        raise ValueError("thresholds must contain probabilities in [0,1]")
    rows_by_threshold: dict[float, list[dict[str, Any]]] = {
        value: [] for value in normalized_thresholds
    }
    for index, path in enumerate(paths, start=1):
        if vocal_stem_root is None:
            audio, sr = sf.read(path, always_2d=True)
            # Official MIR-1K layout: accompaniment left, isolated vocal right.
            prediction_audio = audio[:, 1]
        else:
            stem_path = vocal_stem_root / path.stem / "vocals.wav"
            if not stem_path.is_file():
                raise FileNotFoundError(stem_path)
            audio, sr = sf.read(stem_path, always_2d=True)
            prediction_audio = np.mean(audio, axis=1)
        estimated = estimate_production_pitch(prediction_audio, sr)
        reference_pitch, reference_active = load_reference(root, path.stem)
        reference_voiced = (reference_pitch > 0) & reference_active
        reference_descriptors = vocal_pitch_descriptors(
            reference_pitch,
            reference_active,
            frame_hop_seconds=REFERENCE_HOP_SECONDS,
        )
        predicted_active = align_to_reference(
            estimated["active"].astype(float), len(reference_pitch),
        ) >= 0.5
        for threshold in normalized_thresholds:
            view = vocal_pitch_view(
                estimated, TARGET_SAMPLE_RATE,
                minimum_voiced_probability=threshold,
            )
            predicted_pitch = align_to_reference(view["midi"], len(reference_pitch))
            predicted_voiced = (predicted_pitch > 0) & predicted_active
            correct_pitch = (
                reference_voiced & predicted_voiced
                & (np.abs(reference_pitch - predicted_pitch) <= 0.5)
            )
            rows_by_threshold[threshold].append({
                "id": path.stem,
                "song_group": song_group(path.stem),
                "reference_voiced": reference_voiced,
                "predicted_voiced": predicted_voiced,
                "correct_pitch": correct_pitch,
                "reference_descriptors": reference_descriptors,
                "predicted_descriptors": view["descriptors"],
            })
        print(f"[{index}/{len(paths)}] {path.stem}", file=sys.stderr, flush=True)
    summaries = {threshold: summarize(rows) for threshold, rows in rows_by_threshold.items()}
    if vocal_stem_root is not None:
        for summary in summaries.values():
            summary["release_gate"]["claim_scope"] = (
                "external_vocal_stem_to_pitch_descriptors"
            )
            for gate in summary["feature_release_gates"].values():
                gate["scope"] = gate["scope"].replace(
                    "isolated_vocal", "external_vocal_stem",
                )
    selected_threshold = max(
        normalized_thresholds,
        key=lambda value: (_selection_score(summaries[value]), summaries[value]["frame_metrics"]["overall_accuracy_50_cent"]),
    )
    rows = rows_by_threshold[selected_threshold]
    result = {
        "benchmark": BENCHMARK_NAME,
        "dataset_license": "CC BY 4.0 (Figshare record 5802891)",
        "official_archive_md5": ARCHIVE_MD5,
        "split": split,
        "split_rule": "SHA256(singer_song_group), first byte <128 calibration else heldout",
        "clip_count": len(rows),
        "song_group_count": len({row["song_group"] for row in rows}),
        "method": "production_pyin_rms_gate_v5",
        "parameters": {
            "sample_rate": TARGET_SAMPLE_RATE,
            "hop_length": HOP_LENGTH,
            "fmin": "C2",
            "fmax": "C7",
            "minimum_voiced_probability": selected_threshold,
            "reference_hop_seconds": REFERENCE_HOP_SECONDS,
            "pitch_tolerance_cents": 50,
        },
        "input_mode": (
            "isolated_official_vocal_channel"
            if vocal_stem_root is None else "external_vocal_stem"
        ),
        "vocal_stem_root": None if vocal_stem_root is None else str(vocal_stem_root),
        "claim_limit": [
            (
                "isolated MIR-1K vocal channel only"
                if vocal_stem_root is None else
                "external vocal stems generated from MIR-1K mixtures"
            ),
            "does not validate rap-versus-singing identity",
            *(
                ["does not validate Demucs separation plus pitch as one chain"]
                if vocal_stem_root is None else []
            ),
            "melodic_contour means range-plus-contiguous-motion, not melody transcription",
        ],
        "threshold_selection": {
            "candidate_thresholds": list(normalized_thresholds),
            "selected_threshold": selected_threshold,
            "selection_objective": "maximize minimum of frame and descriptor validation metrics",
            "selection_score": round(_selection_score(summaries[selected_threshold]), 4),
        },
        **summaries[selected_threshold],
        "tracks": [{
            "id": row["id"],
            "song_group": row["song_group"],
            "reference_descriptors": row["reference_descriptors"],
            "predicted_descriptors": row["predicted_descriptors"],
        } for row in rows],
    }
    if len(normalized_thresholds) > 1:
        result["threshold_results"] = {
            str(value): {
                "selection_score": round(_selection_score(summaries[value]), 4),
                **summaries[value],
            }
            for value in normalized_thresholds
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, required=True)
    parser.add_argument("--split", choices=("calibration", "heldout", "all"), default="heldout")
    parser.add_argument("--limit", type=int)
    parser.add_argument(
        "--thresholds", default="0.10",
        help="comma-separated pYIN voiced-probability thresholds",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--vocal-stem-root", type=Path,
        help="optional <root>/<clip-id>/vocals.wav tree for full-chain evaluation",
    )
    args = parser.parse_args()
    thresholds = tuple(float(value) for value in args.thresholds.split(",") if value.strip())
    result = evaluate(
        args.dataset_root,
        split=args.split,
        limit=args.limit,
        thresholds=thresholds,
        vocal_stem_root=args.vocal_stem_root,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
