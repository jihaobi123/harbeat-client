#!/usr/bin/env python3
"""Train and freeze comparable section relabeler candidates.

All validation is grouped by song.  Candidate files are immutable snapshots:
they include the exact feature contract, scaler, classifier, input hashes and
development track IDs needed for a later blind comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import warnings
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.modules.library.section_relabeler import STRUCTURE_LABELS, feature_names
from scripts.train_section_relabeler import (
    aligned_probabilities,
    choose_threshold,
    collect_rows,
    export_parameters,
    gated_predictions,
    metrics,
)


SCHEMA_VERSION = "harbeat_section_candidate_library_v1"
PRIMARY_SEED = 20260831
STABILITY_SEEDS = (20260831, 1, 7, 17, 29, 43, 71, 101, 313, 997)
C_GRID = (0.0003, 0.001, 0.003, 0.01, 0.03)
LOCAL_DIMENSIONS = 52
STRUCTURE_DIMENSIONS = 76


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--audio-cache", type=Path, required=True)
    parser.add_argument("--stem-cache", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--minimum-override-precision", type=float, default=0.90)
    parser.add_argument("--minimum-override-count", type=int, default=10)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def matrix_sha256(values: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(values, dtype=np.float64)
    digest = hashlib.sha256()
    digest.update(str(contiguous.shape).encode("ascii"))
    digest.update(contiguous.tobytes())
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_feature_cache(path: Path) -> tuple[dict[tuple[str, int], np.ndarray], int]:
    with np.load(path, allow_pickle=False) as payload:
        values = np.asarray(payload["features"], dtype=np.float64)
        track_ids = payload["track_ids"].astype(str)
        indices = payload["segment_indices"].astype(int)
    if values.ndim != 2 or len(values) != len(track_ids) or len(values) != len(indices):
        raise ValueError(f"invalid feature cache: {path}")
    lookup: dict[tuple[str, int], np.ndarray] = {}
    for track_id, index, row in zip(track_ids, indices, values):
        key = (str(track_id), int(index))
        if key in lookup:
            raise ValueError(f"duplicate feature cache key {key}: {path}")
        lookup[key] = row
    return lookup, int(values.shape[1])


def align_cache(
    records: list[dict[str, Any]], lookup: dict[tuple[str, int], np.ndarray], dimensions: int, name: str
) -> np.ndarray:
    rows: list[np.ndarray] = []
    missing: list[tuple[str, int]] = []
    for record in records:
        key = (str(record["track_id"]), int(record["segment_index"]))
        value = lookup.get(key)
        if value is None:
            missing.append(key)
        else:
            rows.append(value)
    if missing:
        raise ValueError(f"{name} is missing {len(missing)} trainable segment keys; first={missing[0]}")
    result = np.vstack(rows) if rows else np.zeros((0, dimensions), dtype=np.float64)
    if result.shape != (len(records), dimensions):
        raise ValueError(f"{name} shape mismatch: {result.shape}")
    return result


def fit_model(x: np.ndarray, y: np.ndarray, c_value: float, seed: int):
    scaler = StandardScaler().fit(x)
    scaler.scale_ = np.where(scaler.scale_ < 1e-8, 1.0, scaler.scale_)
    with warnings.catch_warnings():
        # NumPy 2 can emit transient overflow warnings inside sklearn's line
        # search even when the converged parameters are finite.  We validate
        # the exported state explicitly below instead of treating those trial
        # steps as model output.
        warnings.simplefilter("ignore", RuntimeWarning)
        classifier = LogisticRegression(
            C=c_value,
            max_iter=3000,
            solver="lbfgs",
            random_state=seed,
        ).fit(scaler.transform(x), y)
    if not all(
        np.all(np.isfinite(value))
        for value in (scaler.mean_, scaler.scale_, classifier.coef_, classifier.intercept_)
    ):
        raise ValueError("classifier converged to non-finite parameters")
    return scaler, classifier


def oof_probabilities(
    x: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray,
    *,
    c_value: float,
    folds: int,
    seed: int,
) -> tuple[np.ndarray, list[str]]:
    labels = sorted(set(y.tolist()))
    result = np.zeros((len(y), len(labels)), dtype=np.float64)
    splitter = StratifiedGroupKFold(
        n_splits=min(folds, len(set(groups.tolist()))), shuffle=True, random_state=seed
    )
    for train_index, validation_index in splitter.split(x, y, groups):
        scaler, classifier = fit_model(x[train_index], y[train_index], c_value, seed)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            result[validation_index] = aligned_probabilities(
                classifier, scaler.transform(x[validation_index]), labels
            )
    if not np.all(np.isfinite(result)):
        raise ValueError("cross-validation produced non-finite probabilities")
    return result, labels


def per_class_metrics(y: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    labels = list(STRUCTURE_LABELS)
    precision, recall, f1, support = precision_recall_fscore_support(
        y, prediction, labels=labels, zero_division=0
    )
    return {
        label: {
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
            "support": int(support[index]),
        }
        for index, label in enumerate(labels)
    }


def summarize_stability(values: list[dict[str, Any]]) -> dict[str, Any]:
    numeric = ("accuracy", "macro_f1", "changed_count", "fixed_errors", "introduced_errors", "net_gain", "override_precision")
    summary: dict[str, Any] = {"runs": values}
    for key in numeric:
        samples = np.asarray([float(item[key]) for item in values])
        summary[key] = {
            "minimum": float(np.min(samples)),
            "median": float(np.median(samples)),
            "maximum": float(np.max(samples)),
        }
    return summary


def train_candidate(
    *,
    candidate_id: str,
    description: str,
    components: list[str],
    names: list[str],
    x: np.ndarray,
    y: np.ndarray,
    originals: np.ndarray,
    groups: np.ndarray,
    records: list[dict[str, Any]],
    args: argparse.Namespace,
    dataset_sha256: str,
    cache_hashes: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    best: tuple[tuple[float, float, float, float], float, float, np.ndarray, list[str], dict[str, Any]] | None = None
    hyperparameter_trials: list[dict[str, Any]] = []
    for c_value in C_GRID:
        probabilities, labels = oof_probabilities(
            x, y, groups, c_value=c_value, folds=args.folds, seed=PRIMARY_SEED
        )
        threshold, result = choose_threshold(
            probabilities,
            labels,
            originals,
            y,
            args.minimum_override_precision,
            args.minimum_override_count,
        )
        score = (float(result["net_gain"]), float(result["macro_f1"]), float(result["override_precision"]), -c_value)
        hyperparameter_trials.append({
            "c": c_value,
            "selected_threshold_for_c": threshold,
            "metrics": result,
        })
        if best is None or score > best[0]:
            best = (score, c_value, threshold, probabilities, labels, result)
    assert best is not None
    _, c_value, threshold, primary_oof, labels, primary = best
    primary_prediction, primary_proposed = gated_predictions(primary_oof, labels, originals, threshold)
    raw_prediction = np.asarray([labels[index] for index in np.argmax(primary_oof, axis=1)])
    stability_runs: list[dict[str, Any]] = []
    for seed in STABILITY_SEEDS:
        probabilities, seed_labels = oof_probabilities(
            x, y, groups, c_value=c_value, folds=args.folds, seed=seed
        )
        prediction, _ = gated_predictions(probabilities, seed_labels, originals, threshold)
        result = metrics(y, prediction, originals)
        result["seed"] = seed
        stability_runs.append(result)

    scaler, classifier = fit_model(x, y, c_value, PRIMARY_SEED)
    coefficients, intercept = export_parameters(classifier)
    parameter_hash = hashlib.sha256(
        np.ascontiguousarray(coefficients).tobytes()
        + np.ascontiguousarray(intercept).tobytes()
        + np.ascontiguousarray(scaler.mean_).tobytes()
        + np.ascontiguousarray(scaler.scale_).tobytes()
    ).hexdigest()
    model_version = f"{candidate_id}_{parameter_hash[:12]}"
    model = {
        "schema_version": SCHEMA_VERSION,
        "model_version": model_version,
        "candidate_id": candidate_id,
        "status": "frozen_development_candidate_not_production_selected",
        "architecture": "standard_scaler_multinomial_logistic_regression_with_residual_gate",
        "description": description,
        "input_contract": {
            "components": components,
            "feature_names": names,
            "dimensions": len(names),
            "row_identity": ["track_id", "segment_index"],
            "requires_existing_songformer_boundaries": True,
        },
        "training_contract": {
            "dataset_sha256": dataset_sha256,
            "feature_matrix_sha256": matrix_sha256(x),
            "development_track_ids": sorted(set(groups.tolist())),
            "segments": int(len(y)),
            "independent_tracks": int(len(set(groups.tolist()))),
            "class_counts": dict(Counter(y.tolist())),
            "grouping": "StratifiedGroupKFold grouped by track_id",
            "folds": args.folds,
            "primary_seed": PRIMARY_SEED,
            "stability_seeds": list(STABILITY_SEEDS),
            "c_grid": list(C_GRID),
            "selected_c": c_value,
            "minimum_override_precision": args.minimum_override_precision,
            "minimum_override_count": args.minimum_override_count,
            "input_cache_sha256": {key: cache_hashes[key] for key in components if key in cache_hashes},
        },
        "parameters": {
            "labels": [str(value) for value in classifier.classes_],
            "feature_mean": scaler.mean_.tolist(),
            "feature_scale": scaler.scale_.tolist(),
            "coefficients": coefficients.tolist(),
            "intercept": intercept.tolist(),
            "override_threshold": threshold,
            "parameter_sha256": parameter_hash,
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
            "platform": platform.platform(),
            "blas_threads": 1,
        },
    }
    changes = []
    for index, record in enumerate(records):
        if primary_prediction[index] != originals[index]:
            changes.append({
                **record,
                "proposed": str(primary_proposed[index]),
                "final": str(primary_prediction[index]),
                "correct": bool(primary_prediction[index] == y[index]),
            })
    report = {
        "model_version": model_version,
        "candidate_id": candidate_id,
        "description": description,
        "dimensions": int(x.shape[1]),
        "selected_c": c_value,
        "override_threshold": threshold,
        "hyperparameter_trials": hyperparameter_trials,
        "primary_grouped_oof": {
            **primary,
            "per_class": per_class_metrics(y, primary_prediction),
            "ungated_classifier_accuracy": float(accuracy_score(y, raw_prediction)),
            "ungated_classifier_macro_f1": float(
                f1_score(y, raw_prediction, labels=list(STRUCTURE_LABELS), average="macro", zero_division=0)
            ),
            "changes": changes,
        },
        "repeated_grouped_oof": summarize_stability(stability_runs),
    }
    return model, report


def candidate_matrices(
    base: np.ndarray,
    audio: np.ndarray,
    stems: np.ndarray,
) -> list[tuple[str, str, list[str], list[str], np.ndarray]]:
    base_names = feature_names()
    audio_names = [f"mixed_audio_dsp_{index:03d}" for index in range(audio.shape[1])]
    stem_names = [f"demucs_stems_{index:03d}" for index in range(stems.shape[1])]
    return [
        ("c01_songformer_local_v1", "SongFormer probabilities, adjacent labels, duration and position only.", ["songformer_local"], base_names[:LOCAL_DIMENSIONS], base[:, :LOCAL_DIMENSIONS]),
        ("c02_whole_song_structure_v2", "Local evidence plus whole-song recurrence and relative occurrence features.", ["songformer_local", "whole_song_structure"], base_names[:STRUCTURE_DIMENSIONS], base[:, :STRUCTURE_DIMENSIONS]),
        ("c03_encoder_projection_v3", "Whole-song structure plus fixed MusicFM/MuQ encoder projections.", ["songformer_local", "whole_song_structure", "encoder_projection"], base_names, base),
        ("c04_mixed_audio_v4", "Encoder candidate plus boundary-aligned mixed-audio DSP evidence.", ["songformer_local", "whole_song_structure", "encoder_projection", "mixed_audio_dsp"], base_names + audio_names, np.hstack((base, audio))),
        ("c05_demucs_stems_v5", "Encoder candidate plus vocal/drum/bass/other stem evidence.", ["songformer_local", "whole_song_structure", "encoder_projection", "demucs_stems"], base_names + stem_names, np.hstack((base, stems))),
        ("c06_audio_and_stems_v6", "All available local, whole-song, encoder, mixed-audio and stem evidence.", ["songformer_local", "whole_song_structure", "encoder_projection", "mixed_audio_dsp", "demucs_stems"], base_names + audio_names + stem_names, np.hstack((base, audio, stems))),
    ]


def main() -> int:
    args = parse_args()
    if args.folds < 2:
        raise SystemExit("--folds must be at least 2")
    dataset_path = args.dataset.resolve()
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    base, y, originals, groups, records = collect_rows(payload, "development", include_low_confidence=False)
    if len(y) < 20:
        raise SystemExit("not enough trainable development data")
    audio_lookup, audio_dimensions = load_feature_cache(args.audio_cache.resolve())
    stem_lookup, stem_dimensions = load_feature_cache(args.stem_cache.resolve())
    audio = align_cache(records, audio_lookup, audio_dimensions, "mixed-audio cache")
    stems = align_cache(records, stem_lookup, stem_dimensions, "stem cache")
    dataset_sha256 = sha256_file(dataset_path)
    cache_hashes = {
        "mixed_audio_dsp": sha256_file(args.audio_cache.resolve()),
        "demucs_stems": sha256_file(args.stem_cache.resolve()),
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    manifest_models: list[dict[str, Any]] = []
    with threadpool_limits(limits=1):
        for candidate_id, description, components, names, x in candidate_matrices(base, audio, stems):
            print(f"training {candidate_id}: {x.shape}", flush=True)
            model, report = train_candidate(
                candidate_id=candidate_id,
                description=description,
                components=components,
                names=names,
                x=x,
                y=y,
                originals=originals,
                groups=groups,
                records=records,
                args=args,
                dataset_sha256=dataset_sha256,
                cache_hashes=cache_hashes,
            )
            model_path = args.output_dir / "models" / f"{candidate_id}.json"
            report_path = args.output_dir / "reports" / f"{candidate_id}.json"
            atomic_json(model_path, model)
            atomic_json(report_path, report)
            reports.append(report)
            manifest_models.append({
                "candidate_id": candidate_id,
                "model_version": model["model_version"],
                "model_path": str(model_path.relative_to(args.output_dir)),
                "model_sha256": sha256_file(model_path),
                "report_path": str(report_path.relative_to(args.output_dir)),
                "primary_accuracy": report["primary_grouped_oof"]["accuracy"],
                "primary_macro_f1": report["primary_grouped_oof"]["macro_f1"],
                "primary_fixed_errors": report["primary_grouped_oof"]["fixed_errors"],
                "primary_introduced_errors": report["primary_grouped_oof"]["introduced_errors"],
                "stability_net_gain": report["repeated_grouped_oof"]["net_gain"],
            })
            print(
                f"  accuracy={report['primary_grouped_oof']['accuracy']:.4f} "
                f"fixed={report['primary_grouped_oof']['fixed_errors']} "
                f"harmed={report['primary_grouped_oof']['introduced_errors']}",
                flush=True,
            )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "purpose": "frozen candidates for future untouched blind-test comparison",
        "selection_status": "no winner selected; blind test required",
        "dataset_sha256": dataset_sha256,
        "development_segments": int(len(y)),
        "development_tracks": int(len(set(groups.tolist()))),
        "known_track_ids": sorted(set(groups.tolist())),
        "models": manifest_models,
    }
    atomic_json(args.output_dir / "manifest.json", manifest)
    print(json.dumps({"manifest": str(args.output_dir / 'manifest.json'), "models": len(manifest_models)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
