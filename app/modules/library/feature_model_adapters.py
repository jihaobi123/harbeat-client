"""Optional adapters for mature audio-analysis models.

The main API process must remain usable when heavyweight ML runtimes are not
installed.  This module therefore exposes two integration forms:

* in-process adapters for torchcrepe and Spotify Basic Pitch;
* JSON command adapters for independently deployed drum-transcription and
  audio-tagging workers (ADTOF, Omnizart, YAMNet, PANNs, etc.).

Every route returns an explicit status and provenance record.  Missing models
are not silently converted into successful heuristic results.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import shlex
import subprocess
import time
from typing import Any

import librosa
import numpy as np


MODEL_ADAPTER_VERSION = "mature_model_adapters_v1"


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class FeatureModelConfig:
    drum_command: str | None
    tagger_command: str | None
    basic_pitch_command: str | None
    enable_torchcrepe: bool
    enable_basic_pitch: bool
    timeout_seconds: float
    torchcrepe_model: str
    torchcrepe_device: str

    @classmethod
    def from_env(cls) -> "FeatureModelConfig":
        return cls(
            drum_command=os.getenv("FEATURE_DRUM_TRANSCRIBER_COMMAND") or None,
            tagger_command=os.getenv("FEATURE_AUDIO_TAGGER_COMMAND") or None,
            basic_pitch_command=os.getenv("FEATURE_BASIC_PITCH_COMMAND") or None,
            enable_torchcrepe=_env_flag("FEATURE_ENABLE_TORCHCREPE", True),
            enable_basic_pitch=_env_flag("FEATURE_ENABLE_BASIC_PITCH", True),
            timeout_seconds=max(5.0, float(os.getenv("FEATURE_MODEL_TIMEOUT_SECONDS", "300"))),
            torchcrepe_model=os.getenv("FEATURE_TORCHCREPE_MODEL", "full").strip().lower(),
            torchcrepe_device=os.getenv("FEATURE_TORCHCREPE_DEVICE", "auto").strip().lower(),
        )


def _route(
    engine: str,
    status: str,
    *,
    result: dict[str, Any] | None = None,
    error: str | None = None,
    elapsed_seconds: float = 0.0,
    license_name: str | None = None,
) -> dict[str, Any]:
    return {
        "engine": engine,
        "status": status,
        "result": result or {},
        "error": error,
        "elapsed_seconds": round(float(elapsed_seconds), 4),
        "license": license_name,
    }


def _run_json_command(
    command_template: str | None,
    audio_path: str | None,
    *,
    engine: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    if not command_template:
        return _route(engine, "disabled", error="command_not_configured")
    if not audio_path or not os.path.isfile(audio_path):
        return _route(engine, "unavailable", error="audio_file_unavailable")

    try:
        argv = [part.replace("{audio}", audio_path) for part in shlex.split(command_template)]
    except ValueError as exc:
        return _route(engine, "error", error=f"invalid_command: {exc}")
    if not argv or all("{audio}" not in part for part in shlex.split(command_template)):
        return _route(engine, "error", error="command_must_contain_{audio}_placeholder")

    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        payload = json.loads(completed.stdout)
        if not isinstance(payload, dict):
            raise ValueError("model command must return one JSON object")
        return _route(
            str(payload.get("engine") or engine),
            "ready",
            result=payload,
            elapsed_seconds=time.monotonic() - started,
            license_name=payload.get("license"),
        )
    except subprocess.TimeoutExpired:
        return _route(engine, "error", error="model_timeout", elapsed_seconds=time.monotonic() - started)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError, ValueError) as exc:
        detail = str(exc)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            detail = exc.stderr.strip()[-1000:]
        return _route(
            engine,
            "error",
            error=f"{type(exc).__name__}: {detail}",
            elapsed_seconds=time.monotonic() - started,
        )


def _pitch_slide_ranges(
    pitch_hz: np.ndarray,
    confidence: np.ndarray,
    *,
    hop_seconds: float,
    minimum_confidence: float = 0.21,
) -> list[dict[str, float]]:
    pitch_hz = np.asarray(pitch_hz, dtype=float).reshape(-1)
    confidence = np.asarray(confidence, dtype=float).reshape(-1)
    length = min(len(pitch_hz), len(confidence))
    if length < 8:
        return []
    pitch_hz = pitch_hz[:length]
    confidence = confidence[:length]
    valid = (pitch_hz >= 25.0) & np.isfinite(pitch_hz) & (confidence >= minimum_confidence)
    midi = np.full(length, np.nan, dtype=float)
    midi[valid] = 69.0 + 12.0 * np.log2(pitch_hz[valid] / 440.0)
    minimum_frames = max(6, int(round(0.24 / hop_seconds)))
    maximum_frames = max(minimum_frames + 1, int(round(1.8 / hop_seconds)))
    step = max(2, minimum_frames // 3)
    found: list[dict[str, float]] = []
    for start in range(0, max(0, length - minimum_frames), step):
        stop = min(length, start + maximum_frames)
        segment = midi[start:stop]
        indices = np.where(np.isfinite(segment))[0]
        if len(indices) < minimum_frames or len(indices) / len(segment) < 0.68:
            continue
        values = segment[indices]
        motion = float(values[-1] - values[0])
        diffs = np.diff(values)
        monotonicity = max(float(np.mean(diffs >= -0.18)), float(np.mean(diffs <= 0.18)))
        if abs(motion) < 2.0 or monotonicity < 0.72:
            continue
        found.append({
            "start": round((start + int(indices[0])) * hop_seconds, 4),
            "end": round((start + int(indices[-1])) * hop_seconds, 4),
            "motion_semitones": round(motion, 3),
            "confidence": round(float(np.mean(confidence[start:stop][indices])), 4),
        })
    merged: list[dict[str, float]] = []
    for item in found:
        if merged and item["start"] <= merged[-1]["end"] + 0.08:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
            if abs(item["motion_semitones"]) > abs(merged[-1]["motion_semitones"]):
                merged[-1]["motion_semitones"] = item["motion_semitones"]
            merged[-1]["confidence"] = max(merged[-1]["confidence"], item["confidence"])
        else:
            merged.append(dict(item))
    return merged[:64]


def _torchcrepe_route(audio_path: str | None, config: FeatureModelConfig) -> dict[str, Any]:
    if not config.enable_torchcrepe:
        return _route("torchcrepe", "disabled", license_name="MIT")
    if not audio_path or not os.path.isfile(audio_path):
        return _route("torchcrepe", "unavailable", error="bass_stem_unavailable", license_name="MIT")
    started = time.monotonic()
    try:
        import torch
        import torchcrepe

        sample_rate = 16000
        audio, _ = librosa.load(audio_path, sr=sample_rate, mono=True)
        if len(audio) < sample_rate:
            return _route("torchcrepe", "unavailable", error="bass_stem_too_short", license_name="MIT")
        hop_length = 160
        device = config.torchcrepe_device
        if device == "auto":
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
        tensor = torch.from_numpy(np.asarray(audio, dtype=np.float32)).unsqueeze(0).to(device)
        with torch.no_grad():
            pitch, periodicity = torchcrepe.predict(
                tensor,
                sample_rate,
                hop_length,
                32.7,
                400.0,
                config.torchcrepe_model if config.torchcrepe_model in {"tiny", "full"} else "full",
                batch_size=1024,
                device=device,
                return_periodicity=True,
            )
        pitch_values = pitch.detach().cpu().numpy().reshape(-1)
        confidence_values = periodicity.detach().cpu().numpy().reshape(-1)
        voiced = confidence_values >= 0.21
        result = {
            "hop_seconds": hop_length / sample_rate,
            "frame_count": int(len(pitch_values)),
            "voiced_fraction": round(float(np.mean(voiced)), 4) if len(voiced) else 0.0,
            "median_pitch_hz": round(float(np.median(pitch_values[voiced])), 3) if np.any(voiced) else None,
            "mean_confidence": round(float(np.mean(confidence_values[voiced])), 4) if np.any(voiced) else 0.0,
            "slide_ranges": _pitch_slide_ranges(
                pitch_values,
                confidence_values,
                hop_seconds=hop_length / sample_rate,
            ),
        }
        return _route(
            "torchcrepe",
            "ready",
            result=result,
            elapsed_seconds=time.monotonic() - started,
            license_name="MIT",
        )
    except (ImportError, ModuleNotFoundError) as exc:
        return _route("torchcrepe", "unavailable", error=f"dependency_missing: {exc}", license_name="MIT")
    except Exception as exc:
        return _route(
            "torchcrepe", "error", error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started, license_name="MIT",
        )


def _basic_pitch_route(audio_path: str | None, config: FeatureModelConfig) -> dict[str, Any]:
    if not config.enable_basic_pitch:
        return _route("spotify_basic_pitch", "disabled", license_name="Apache-2.0")
    if config.basic_pitch_command:
        route = _run_json_command(
            config.basic_pitch_command,
            audio_path,
            engine="spotify_basic_pitch_worker",
            timeout_seconds=config.timeout_seconds,
        )
        if route.get("license") is None:
            route["license"] = "Apache-2.0"
        return route
    if not audio_path or not os.path.isfile(audio_path):
        return _route(
            "spotify_basic_pitch", "unavailable", error="bass_stem_unavailable", license_name="Apache-2.0",
        )
    started = time.monotonic()
    try:
        from basic_pitch.inference import predict

        _model_output, _midi, note_events = predict(audio_path)
        notes = []
        bend_note_count = 0
        for raw in note_events or []:
            if len(raw) < 4:
                continue
            start, end, midi_pitch, amplitude = raw[:4]
            bends = raw[4] if len(raw) > 4 and raw[4] is not None else []
            if len(bends):
                bend_note_count += 1
            notes.append({
                "start": round(float(start), 4),
                "end": round(float(end), 4),
                "midi_pitch": int(midi_pitch),
                "confidence": round(float(amplitude), 4),
                "has_pitch_bend": bool(len(bends)),
            })
        return _route(
            "spotify_basic_pitch",
            "ready",
            result={
                "note_count": len(notes),
                "pitch_bend_note_count": bend_note_count,
                "notes": notes[:1000],
            },
            elapsed_seconds=time.monotonic() - started,
            license_name="Apache-2.0",
        )
    except (ImportError, ModuleNotFoundError) as exc:
        return _route(
            "spotify_basic_pitch", "unavailable", error=f"dependency_missing: {exc}", license_name="Apache-2.0",
        )
    except Exception as exc:
        return _route(
            "spotify_basic_pitch", "error", error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started, license_name="Apache-2.0",
        )


def collect_mature_model_evidence(
    stem_paths: dict[str, str] | None,
    *,
    original_path: str | None = None,
    config: FeatureModelConfig | None = None,
) -> dict[str, Any]:
    """Run enabled mature routes and return a stable, auditable envelope."""
    config = config or FeatureModelConfig.from_env()
    stem_paths = stem_paths or {}
    drums_path = stem_paths.get("drums")
    bass_path = stem_paths.get("bass")
    tag_audio = original_path if original_path and os.path.isfile(original_path) else stem_paths.get("other")
    routes = {
        "drum_transcription": _run_json_command(
            config.drum_command,
            drums_path,
            engine="external_drum_transcriber",
            timeout_seconds=config.timeout_seconds,
        ),
        "bass_pitch": _torchcrepe_route(bass_path, config),
        "bass_notes": _basic_pitch_route(bass_path, config),
        "audio_tags": _run_json_command(
            config.tagger_command,
            tag_audio,
            engine="external_audio_tagger",
            timeout_seconds=config.timeout_seconds,
        ),
    }
    ready = [name for name, value in routes.items() if value["status"] == "ready"]
    failed = [name for name, value in routes.items() if value["status"] == "error"]
    return {
        "version": MODEL_ADAPTER_VERSION,
        "status": "ready" if ready else ("error" if failed else "unavailable"),
        "ready_routes": ready,
        "failed_routes": failed,
        "routes": routes,
    }
