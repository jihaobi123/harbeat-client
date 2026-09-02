#!/usr/bin/env python3
"""Produce an evidence audit for a section relabel training dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.section_relabel_dataset import (
    annotation_is_reviewed,
    annotation_is_trainable,
    track_is_excluded,
    validate_dataset,
)
from app.modules.library.section_relabeler import (
    STRUCTURE_LABELS,
    canonical_target_structure_label,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--audio-cache", type=Path)
    parser.add_argument("--stem-cache", type=Path)
    return parser.parse_args()


def _percentile(values: list[float], value: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), value)) if values else 0.0


def _cache_keys(path: Path | None) -> tuple[set[tuple[str, int]], dict[str, Any]]:
    if path is None or not path.is_file():
        return set(), {"available": False, "path": str(path) if path else None}
    raw = path.read_bytes()
    with np.load(path, allow_pickle=False) as payload:
        keys = set(zip(payload["track_ids"].astype(str), payload["segment_indices"].astype(int)))
        features = payload["features"]
        detail = {
            "available": True,
            "path": str(path.resolve()),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "rows": int(features.shape[0]),
            "dimensions": int(features.shape[1]),
            "failures": int(len(payload["failures"])) if "failures" in payload else None,
        }
    return keys, detail


def build_audit(
    payload: dict[str, Any],
    *,
    dataset_path: Path,
    dataset_sha256: str,
    audio_cache: Path | None,
    stem_cache: Path | None,
) -> dict[str, Any]:
    validation = validate_dataset(payload, include_low_confidence=False)
    audio_keys, audio_detail = _cache_keys(audio_cache)
    stem_keys, stem_detail = _cache_keys(stem_cache)
    split_summary: dict[str, Any] = {}
    development_rows: list[dict[str, Any]] = []

    for split in ("development", "test"):
        tracks = [track for track in payload.get("tracks", []) if track.get("split") == split]
        clean = [track for track in tracks if not track_is_excluded(track)]
        all_segment_count = sum(len(track.get("segments") or []) for track in tracks)
        clean_segment_count = sum(len(track.get("segments") or []) for track in clean)
        reviewed = trainable = 0
        for track in clean:
            for segment in track.get("segments") or []:
                annotation = dict(segment.get("annotation") or {})
                reviewed += int(annotation_is_reviewed(annotation))
                trainable += int(annotation_is_trainable(annotation))
        split_summary[split] = {
            "all_tracks": len(tracks),
            "excluded_tracks": len(tracks) - len(clean),
            "usable_tracks": len(clean),
            "all_segments": all_segment_count,
            "usable_segments": clean_segment_count,
            "reviewed_segments": reviewed,
            "trainable_segments": trainable,
        }

    target_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    target_tracks: dict[str, set[str]] = defaultdict(set)
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    styles: dict[str, Counter[str]] = defaultdict(Counter)
    transitions: Counter[str] = Counter()
    sequence_patterns: Counter[str] = Counter()
    durations: dict[str, list[float]] = defaultdict(list)
    position_errors: Counter[str] = Counter()
    position_totals: Counter[str] = Counter()
    confidence_errors: Counter[str] = Counter()
    confidence_totals: Counter[str] = Counter()
    trainable_keys: set[tuple[str, int]] = set()
    trainable_track_ids: set[str] = set()

    for track in payload.get("tracks") or []:
        if track.get("split") != "development" or track_is_excluded(track):
            continue
        track_id = str(track["track_id"])
        style = str(track.get("style") or "unknown")
        sequence: list[str] = []
        segments = list(track.get("segments") or [])
        for position, segment in enumerate(segments):
            annotation = dict(segment.get("annotation") or {})
            if not annotation_is_trainable(annotation):
                continue
            target = canonical_target_structure_label(annotation.get("human_label"))
            source = canonical_target_structure_label(
                segment.get("structure_label_candidate")
                or segment.get("songformer_label")
                or segment.get("label")
            )
            if target not in STRUCTURE_LABELS:
                continue
            key = (track_id, int(segment.get("segment_index", position)))
            trainable_keys.add(key)
            trainable_track_ids.add(track_id)
            target_counts[target] += 1
            source_counts[source] += 1
            target_tracks[target].add(track_id)
            confusion[source][target] += 1
            correct = source == target
            styles[style]["segments"] += 1
            styles[style]["correct"] += int(correct)
            styles[style]["tracks_marker_" + track_id] = 1
            duration = max(0.0, float(segment.get("end", 0.0)) - float(segment.get("start", 0.0)))
            durations[target].append(duration)
            quartile = min(4, int(4 * position / max(len(segments), 1)) + 1)
            position_totals[f"Q{quartile}"] += 1
            position_errors[f"Q{quartile}"] += int(not correct)
            probability = dict(segment.get("structure_label_probabilities") or {})
            confidence = max((float(value) for value in probability.values()), default=0.0)
            bucket = "<0.60" if confidence < 0.60 else "0.60-0.79" if confidence < 0.80 else "0.80-0.94" if confidence < 0.95 else ">=0.95"
            confidence_totals[bucket] += 1
            confidence_errors[bucket] += int(not correct)
            sequence.append(target)
            development_rows.append({"track_id": track_id, "segment_index": key[1], "target": target})
        compact = [label for index, label in enumerate(sequence) if index == 0 or label != sequence[index - 1]]
        for previous, following in zip(compact, compact[1:]):
            transitions[f"{previous} -> {following}"] += 1
        if compact:
            sequence_patterns[" -> ".join(compact)] += 1

    style_report: dict[str, Any] = {}
    for style, counts in sorted(styles.items()):
        tracks = sum(1 for key in counts if key.startswith("tracks_marker_"))
        segments = counts["segments"]
        style_report[style] = {
            "tracks": tracks,
            "segments": segments,
            "songformer_accuracy": counts["correct"] / segments if segments else 0.0,
        }

    label_report = {}
    for label in STRUCTURE_LABELS:
        values = durations[label]
        label_report[label] = {
            "segments": target_counts[label],
            "independent_tracks": len(target_tracks[label]),
            "median_duration_seconds": statistics.median(values) if values else 0.0,
            "duration_p10_seconds": _percentile(values, 10),
            "duration_p90_seconds": _percentile(values, 90),
        }

    baseline_correct = sum(confusion[label][label] for label in STRUCTURE_LABELS)
    trainable_count = sum(target_counts.values())
    audio_detail["development_trainable_coverage"] = (
        len(trainable_keys & audio_keys) / len(trainable_keys) if trainable_keys else 0.0
    )
    stem_detail["development_trainable_coverage"] = (
        len(trainable_keys & stem_keys) / len(trainable_keys) if trainable_keys else 0.0
    )
    warnings: list[str] = []
    for label, item in label_report.items():
        if item["independent_tracks"] < 10:
            warnings.append(f"{label} only appears in {item['independent_tracks']} independent development tracks")
    warnings.append(
        "Segments in one song are correlated; model selection and evaluation must group by track_id."
    )
    warnings.append(
        "The current eight-song test split is historically exposed; final selection needs a new untouched blind test set."
    )

    return {
        "audit_schema_version": "harbeat_section_dataset_audit_v1",
        "dataset": str(dataset_path.resolve()),
        "dataset_sha256": dataset_sha256,
        "dataset_validation": validation,
        "split_summary": split_summary,
        "development": {
            "effective_independent_samples": len(trainable_track_ids),
            "trainable_segments": trainable_count,
            "songformer_baseline_correct": baseline_correct,
            "songformer_baseline_errors": trainable_count - baseline_correct,
            "songformer_baseline_accuracy": baseline_correct / trainable_count if trainable_count else 0.0,
            "labels": label_report,
            "source_label_counts": dict(source_counts),
            "source_to_human_confusion": {key: dict(value) for key, value in sorted(confusion.items())},
            "styles": style_report,
            "position_quartiles": {
                key: {
                    "segments": position_totals[key],
                    "errors": position_errors[key],
                    "error_rate": position_errors[key] / position_totals[key] if position_totals[key] else 0.0,
                }
                for key in sorted(position_totals)
            },
            "songformer_confidence_buckets": {
                key: {
                    "segments": confidence_totals[key],
                    "errors": confidence_errors[key],
                    "error_rate": confidence_errors[key] / confidence_totals[key] if confidence_totals[key] else 0.0,
                }
                for key in ("<0.60", "0.60-0.79", "0.80-0.94", ">=0.95")
            },
            "most_common_transitions": transitions.most_common(30),
            "most_common_compact_sequences": sequence_patterns.most_common(20),
        },
        "feature_sources": {
            "songformer_local": {"dimensions": 52, "coverage": 1.0},
            "whole_song_structure": {"dimensions": 24, "coverage": 1.0},
            "encoder_projection": {"dimensions": 1024, "coverage": 1.0},
            "mixed_audio_dsp": audio_detail,
            "demucs_stems": stem_detail,
        },
        "warnings": warnings,
    }


def render_markdown(audit: dict[str, Any]) -> str:
    development = audit["development"]
    split = audit["split_summary"]
    lines = [
        "# Section relabel dataset audit",
        "",
        f"Dataset SHA-256: `{audit['dataset_sha256']}`",
        "",
        "## Usable evidence",
        "",
        f"- All data: {split['development']['all_tracks']} development songs + {split['test']['all_tracks']} historical test songs.",
        f"- Intentionally excluded: {split['development']['excluded_tracks']} structurally chaotic development songs.",
        f"- Trainable development evidence: {development['trainable_segments']} segments from {development['effective_independent_samples']} independent songs.",
        f"- SongFormer baseline: {development['songformer_baseline_correct']}/{development['trainable_segments']} correct ({development['songformer_baseline_accuracy']:.2%}).",
        "",
        "## Labels",
        "",
        "| Label | Segments | Independent songs | Median duration | P10–P90 duration |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, item in development["labels"].items():
        lines.append(
            f"| {label} | {item['segments']} | {item['independent_tracks']} | {item['median_duration_seconds']:.1f}s | {item['duration_p10_seconds']:.1f}–{item['duration_p90_seconds']:.1f}s |"
        )
    lines.extend(["", "## Feature coverage", "", "| Source | Dimensions | Development coverage |", "|---|---:|---:|"])
    for name, item in audit["feature_sources"].items():
        coverage = item.get("coverage", item.get("development_trainable_coverage", 0.0))
        lines.append(f"| {name} | {item.get('dimensions', 0)} | {coverage:.2%} |")
    lines.extend(["", "## Main cautions", ""])
    lines.extend(f"- {warning}" for warning in audit["warnings"])
    lines.extend([
        "",
        "The JSON companion contains complete source→human confusion, style breakdown, position/confidence error rates, transitions, and compact whole-song sequences.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    raw = args.dataset.read_bytes()
    payload = json.loads(raw)
    audit = build_audit(
        payload,
        dataset_path=args.dataset,
        dataset_sha256=hashlib.sha256(raw).hexdigest(),
        audio_cache=args.audio_cache,
        stem_cache=args.stem_cache,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(render_markdown(audit), encoding="utf-8")
    print(json.dumps({"json": str(args.json_output), "markdown": str(args.markdown_output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
