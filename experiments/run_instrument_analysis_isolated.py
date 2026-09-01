"""Sequential Jetson inference adapter for ADTOF-PyTorch and PANNs.

Heavy dependencies are imported only inside the model functions so the runtime
contract and mapping logic remain testable without CUDA or model packages.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable, Sequence


RUNNER_VERSION = "instrument_analysis_isolated_v1"
DRUM_LABELS = {35: "kick", 38: "snare", 47: "tom", 42: "hihat", 49: "cymbal"}
PANNS_INSTRUMENT_LABELS = {
    "drums": {"Drum", "Drum kit", "Snare drum", "Bass drum", "Cymbal", "Hi-hat", "Timpani", "Tabla"},
    "percussion": {"Percussion", "Rattle", "Maraca", "Tambourine", "Marimba, xylophone", "Glockenspiel", "Vibraphone"},
    "bass": {"Bass guitar", "Double bass"},
    "acoustic_guitar": {"Acoustic guitar"},
    "electric_guitar": {"Electric guitar", "Guitar"},
    "piano": {"Piano", "Grand piano"},
    "electric_piano": {"Electric piano"},
    "synthesizer": {"Synthesizer"},
    "strings": {"String section", "Violin, fiddle", "Cello", "Viola", "Harp", "Orchestra"},
    "brass": {"Brass instrument", "Trumpet", "Trombone", "French horn"},
    "woodwind": {"Wind instrument, woodwind instrument", "Flute", "Saxophone", "Clarinet", "Oboe", "Bassoon"},
    "organ": {"Organ", "Hammond organ"},
    "sampler_fx": {"Sampler", "Effects unit", "Sound effect"},
    "voice": {"Singing", "Male singing", "Female singing", "Child singing", "Choir", "Vocal music", "Speech"},
}


def iter_audio_windows(
    duration_sec: float, *, window_sec: float = 10.0, hop_sec: float = 5.0
) -> Iterable[tuple[float, float]]:
    if duration_sec <= 0 or window_sec <= 0 or hop_sec <= 0:
        raise ValueError("durations must be positive")
    start = 0.0
    while start < duration_sec:
        yield round(start, 6), round(min(duration_sec, start + window_sec), 6)
        start += hop_sec


def broad_instrument_scores(labels: Sequence[str], scores: Sequence[float]) -> dict[str, float]:
    if len(labels) != len(scores):
        raise ValueError("labels and scores length mismatch")
    by_label = {str(label): float(score) for label, score in zip(labels, scores)}
    result: dict[str, float] = {}
    for instrument_class, source_labels in PANNS_INSTRUMENT_LABELS.items():
        present = [by_label[label] for label in source_labels if label in by_label]
        if present:
            value = max(present)
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError("PANNs probability is not finite or bounded")
            result[instrument_class] = round(value, 6)
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_revision(path: Path | None) -> str | None:
    if path is None:
        return None
    marker = path / "REVISION"
    if marker.is_file():
        return marker.read_text(encoding="utf-8").strip()[:64]
    try:
        return subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()[:64]
    except Exception:
        return None


def read_audioset_labels(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    labels = [str(row.get("display_name", "")).strip() for row in rows]
    if len(labels) != 527 or any(not label for label in labels):
        raise ValueError("AudioSet label file must contain 527 display_name rows")
    return labels


def peak_cuda_bytes(torch_module: Any) -> int:
    if torch_module.cuda.is_available():
        return int(torch_module.cuda.max_memory_allocated())
    return 0


def release_cuda(torch_module: Any, *objects: Any) -> None:
    del objects
    if torch_module.cuda.is_available():
        torch_module.cuda.empty_cache()


def run_adtof(
    *, drums_stem: Path, weights: Path, device: str, precision: str
) -> dict[str, Any]:
    import numpy as np
    import torch
    from adtof_pytorch import (
        FRAME_RNN_THRESHOLDS,
        LABELS_5,
        PeakPicker,
        calculate_n_bins,
        create_frame_rnn_model,
        load_audio_for_model,
        load_pytorch_weights,
    )

    started = time.monotonic()
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    model = create_frame_rnn_model(calculate_n_bins())
    model = load_pytorch_weights(model, str(weights), strict=False).eval().to(device)
    waveform = load_audio_for_model(str(drums_stem)).to(device)
    use_half = precision == "float16" and device == "cuda"
    if use_half:
        model = model.half()
        waveform = waveform.half()
    with torch.no_grad():
        activations = model(waveform).float().cpu().numpy()
    peaks = PeakPicker(thresholds=FRAME_RNN_THRESHOLDS, fps=100).pick(
        activations, labels=LABELS_5, label_offset=0
    )[0]
    events: list[dict[str, Any]] = []
    for class_index, midi_pitch in enumerate(LABELS_5):
        for event_time in peaks[int(midi_pitch)]:
            frame = min(activations.shape[1] - 1, max(0, int(round(event_time * 100))))
            events.append(
                {
                    "time_sec": round(float(event_time), 6),
                    "drum_class": DRUM_LABELS[int(midi_pitch)],
                    "confidence": round(float(np.clip(activations[0, frame, class_index], 0, 1)), 6),
                }
            )
    events.sort(key=lambda item: (item["time_sec"], item["drum_class"]))
    result = {
        "availability": "available",
        "checkpoint_sha256": sha256_file(weights),
        "source_revision": source_revision(Path(os.environ["ADTOF_SOURCE_ROOT"])) if os.environ.get("ADTOF_SOURCE_ROOT") else None,
        "events": events,
        "windows": [],
        "labels": [],
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "peak_cuda_bytes": peak_cuda_bytes(torch),
        "error": None,
    }
    release_cuda(torch, model, waveform)
    return result


def run_panns(
    *,
    audio: Path,
    weights: Path,
    labels_path: Path,
    source_root: Path,
    device: str,
    precision: str,
) -> tuple[dict[str, Any], float]:
    sys.path.insert(0, str(source_root / "pytorch"))
    sys.path.insert(0, str(source_root / "utils"))
    import librosa
    import numpy as np
    import torch
    from models import Cnn14_DecisionLevelMax

    started = time.monotonic()
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
    sample_rate = 32000
    waveform, _ = librosa.load(str(audio), sr=sample_rate, mono=True)
    duration_sec = float(len(waveform) / sample_rate)
    labels = read_audioset_labels(labels_path)
    model = Cnn14_DecisionLevelMax(
        sample_rate=sample_rate,
        window_size=1024,
        hop_size=320,
        mel_bins=64,
        fmin=50,
        fmax=14000,
        classes_num=len(labels),
    )
    checkpoint = torch.load(str(weights), map_location="cpu")
    model.load_state_dict(checkpoint["model"])
    model.eval().to(device)
    windows: list[dict[str, Any]] = []
    for start_sec, end_sec in iter_audio_windows(duration_sec):
        start = int(round(start_sec * sample_rate))
        stop = int(round(end_sec * sample_rate))
        clip = waveform[start:stop].astype(np.float32, copy=False)
        target_samples = sample_rate * 10
        if len(clip) < target_samples:
            clip = np.pad(clip, (0, target_samples - len(clip)))
        tensor = torch.from_numpy(clip[None, :]).to(device)
        with torch.no_grad():
            if precision == "float16" and device == "cuda":
                with torch.autocast(device_type="cuda", dtype=torch.float16):
                    output = model(tensor, None)["clipwise_output"]
            else:
                output = model(tensor, None)["clipwise_output"]
        scores = output.float().cpu().numpy()[0].tolist()
        windows.append(
            {
                "start_sec": start_sec,
                "end_sec": end_sec,
                "scores": [round(float(score), 7) for score in scores],
                "broad_scores": broad_instrument_scores(labels, scores),
            }
        )
    result = {
        "availability": "available",
        "checkpoint_sha256": sha256_file(weights),
        "source_revision": source_revision(source_root),
        "events": [],
        "windows": windows,
        "labels": labels,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "peak_cuda_bytes": peak_cuda_bytes(torch),
        "error": None,
    }
    release_cuda(torch, model)
    return result, duration_sec


def unavailable(error: str) -> dict[str, Any]:
    return {
        "availability": "unavailable",
        "checkpoint_sha256": None,
        "source_revision": None,
        "events": [],
        "windows": [],
        "labels": [],
        "elapsed_seconds": 0.0,
        "peak_cuda_bytes": 0,
        "error": error,
    }


def failed(exc: Exception, *, elapsed_seconds: float) -> dict[str, Any]:
    return {
        **unavailable(f"{type(exc).__name__}: {exc}"[:4096]),
        "availability": "failed",
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}-", suffix=".tmp", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--drums-stem", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--adtof-weights", type=Path, required=True)
    parser.add_argument("--panns-weights", type=Path, required=True)
    parser.add_argument("--panns-labels", type=Path, required=True)
    parser.add_argument("--panns-source", type=Path, required=True)
    parser.add_argument("--adtof-source", type=Path)
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--precision", choices=["float16", "float32"], default="float16")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audio = args.audio.expanduser().resolve()
    if not audio.is_file():
        raise FileNotFoundError(audio)
    device = args.device
    if args.adtof_source:
        os.environ["ADTOF_SOURCE_ROOT"] = str(args.adtof_source.expanduser().resolve())
        sys.path.insert(0, str(args.adtof_source.expanduser().resolve() / "src"))
    warnings: list[str] = []
    models: dict[str, Any] = {}
    if args.drums_stem and args.drums_stem.is_file():
        started = time.monotonic()
        try:
            models["adtof"] = run_adtof(
                drums_stem=args.drums_stem.expanduser().resolve(),
                weights=args.adtof_weights.expanduser().resolve(),
                device=device,
                precision=args.precision,
            )
        except Exception as exc:
            models["adtof"] = failed(exc, elapsed_seconds=time.monotonic() - started)
            warnings.append("ADTOF_FAILED")
    else:
        models["adtof"] = unavailable("DRUMS_STEM_MISSING")
        warnings.append("DRUMS_STEM_MISSING")

    started = time.monotonic()
    duration_sec = 0.0
    try:
        models["panns"], duration_sec = run_panns(
            audio=audio,
            weights=args.panns_weights.expanduser().resolve(),
            labels_path=args.panns_labels.expanduser().resolve(),
            source_root=args.panns_source.expanduser().resolve(),
            device=device,
            precision=args.precision,
        )
    except Exception as exc:
        models["panns"] = failed(exc, elapsed_seconds=time.monotonic() - started)
        warnings.append("PANNS_FAILED")
        import librosa

        duration_sec = float(librosa.get_duration(path=str(audio)))

    available = sum(model["availability"] == "available" for model in models.values())
    status = "ready" if available == 2 else "partial" if available == 1 else "failed"
    runtime_fingerprint = {
        "runner_version": RUNNER_VERSION,
        "python": sys.version.split()[0],
        "device": device,
        "precision": args.precision,
        "adtof_source_revision": source_revision(args.adtof_source),
        "panns_source_revision": source_revision(args.panns_source),
    }
    manifest = {
        "schema_name": "harbeat.instrument_runtime_manifest",
        "schema_version": "0.1.0",
        "runtime_fingerprint": runtime_fingerprint,
        "tracks": [
            {
                "audio_path": str(audio),
                "audio_sha256": sha256_file(audio),
                "duration_sec": round(duration_sec, 6),
                "status": status,
                "models": models,
                "warnings": warnings,
            }
        ],
    }
    atomic_json(args.output_dir.expanduser().resolve() / "manifest.json", manifest)
    return 0 if status != "failed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
