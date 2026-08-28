"""Optional mature-model adapters for drums and auxiliary style labels.

Drum events can replace the spectral proxy.  Discogs-style labels remain a
separate, traceable route: they may calibrate the 21-style mapping but never
replace the native time-frequency feature evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import shlex
import subprocess
import time
from typing import Any


MODEL_ADAPTER_VERSION = "feature_model_adapters_v4"


@dataclass(frozen=True)
class FeatureModelConfig:
    drum_command: str | None = None
    bass_command: str | None = None
    style_command: str | None = None
    instrument_command: str | None = None
    style_model_path: str | None = None
    style_metadata_path: str | None = None
    style_max_duration_seconds: float = 90.0
    timeout_seconds: float = 300.0

    @classmethod
    def from_env(cls) -> "FeatureModelConfig":
        return cls(
            drum_command=os.getenv("FEATURE_DRUM_TRANSCRIBER_COMMAND") or None,
            bass_command=os.getenv("FEATURE_BASS_TRANSCRIBER_COMMAND") or None,
            style_command=os.getenv("FEATURE_STYLE_TAGGER_COMMAND") or None,
            instrument_command=os.getenv("FEATURE_INSTRUMENT_TAGGER_COMMAND") or None,
            style_model_path=os.getenv("ESSENTIA_DISCOGS_MODEL_PATH") or None,
            style_metadata_path=os.getenv("ESSENTIA_DISCOGS_METADATA_PATH") or None,
            style_max_duration_seconds=max(
                30.0, float(os.getenv("ESSENTIA_STYLE_MAX_DURATION_SECONDS", "90")),
            ),
            timeout_seconds=max(5.0, float(os.getenv("FEATURE_MODEL_TIMEOUT_SECONDS", "300"))),
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
        template_parts = shlex.split(command_template)
        if not template_parts or all("{audio}" not in part for part in template_parts):
            return _route(engine, "error", error="command_must_contain_{audio}_placeholder")
        argv = [part.replace("{audio}", audio_path) for part in template_parts]
    except ValueError as exc:
        return _route(engine, "error", error=f"invalid_command: {exc}")

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
        detail = exc.stderr.strip()[-1000:] if isinstance(exc, subprocess.CalledProcessError) and exc.stderr else str(exc)
        return _route(
            engine,
            "error",
            error=f"{type(exc).__name__}: {detail}",
            elapsed_seconds=time.monotonic() - started,
        )


def _run_essentia_discogs(
    audio_path: str | None,
    *,
    model_path: str | None,
    metadata_path: str | None,
    max_duration_seconds: float,
) -> dict[str, Any]:
    engine = "essentia_discogs_effnet"
    if not model_path and not metadata_path:
        return _route(engine, "disabled", error="model_not_configured")
    if not audio_path or not os.path.isfile(audio_path):
        return _route(engine, "unavailable", error="audio_file_unavailable")
    if not model_path or not os.path.isfile(model_path):
        return _route(engine, "unavailable", error="model_file_unavailable")
    if not metadata_path or not os.path.isfile(metadata_path):
        return _route(engine, "unavailable", error="model_metadata_unavailable")
    started = time.monotonic()
    try:
        import numpy as np
        import essentia.standard as essentia_standard

        with open(metadata_path, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        labels = metadata.get("classes") or []
        if not isinstance(labels, list) or not labels:
            raise ValueError("model metadata must contain non-empty classes")
        start_time = 0.0
        source_duration = None
        try:
            import soundfile as sf

            source_duration = float(sf.info(audio_path).duration)
            start_time = max(0.0, (source_duration - max_duration_seconds) / 2.0)
        except (ImportError, OSError, RuntimeError, ValueError):
            pass
        end_time = start_time + max_duration_seconds
        full_audio = essentia_standard.MonoLoader(
            filename=audio_path,
            sampleRate=16000,
            resampleQuality=4,
        )()
        start_sample = int(round(start_time * 16000))
        maximum_samples = int(round(max_duration_seconds * 16000))
        audio = full_audio[start_sample : start_sample + maximum_samples]
        predictor = essentia_standard.TensorflowPredictEffnetDiscogs(
            graphFilename=model_path, output="PartitionedCall:0",
        )
        predictions = np.asarray(predictor(audio), dtype=float)
        if predictions.ndim != 2 or predictions.shape[1] != len(labels):
            raise ValueError(
                f"prediction shape {predictions.shape} does not match {len(labels)} labels"
            )
        means = np.mean(predictions, axis=0)
        upper = np.percentile(predictions, 75, axis=0)
        scores = 0.70 * means + 0.30 * upper
        ranked = np.argsort(scores)[::-1][:25]
        result = {
            "engine": engine,
            "model_name": metadata.get("name") or "EffnetDiscogs",
            "model_version": str(metadata.get("version") or "unknown"),
            "model_file": os.path.basename(model_path),
            "metadata_file": os.path.basename(metadata_path),
            "aggregation": "0.70*mean+0.30*p75",
            "audio_window": {
                "start_seconds": round(start_time, 3),
                "end_seconds": round(
                    min(end_time, source_duration) if source_duration is not None else end_time,
                    3,
                ),
                "maximum_duration_seconds": round(max_duration_seconds, 3),
                "selection": "center_window_when_duration_is_available",
            },
            "frame_count": int(predictions.shape[0]),
            "labels": [
                {
                    "label": str(labels[index]),
                    "score": round(float(scores[index]), 6),
                    "mean": round(float(means[index]), 6),
                    "p75": round(float(upper[index]), 6),
                }
                for index in ranked
            ],
        }
        return _route(
            engine,
            "ready",
            result=result,
            elapsed_seconds=time.monotonic() - started,
            license_name=metadata.get("license"),
        )
    except (ImportError, OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return _route(
            engine,
            "error",
            error=f"{type(exc).__name__}: {exc}",
            elapsed_seconds=time.monotonic() - started,
        )
def collect_mature_model_evidence(
    stem_paths: dict[str, str] | None,
    *,
    original_path: str | None = None,
    config: FeatureModelConfig | None = None,
) -> dict[str, Any]:
    """Collect configured mature routes without downloading model artifacts."""
    config = config or FeatureModelConfig.from_env()
    drum_route = _run_json_command(
        config.drum_command,
        (stem_paths or {}).get("drums"),
        engine="external_drum_transcriber",
        timeout_seconds=config.timeout_seconds,
    )
    bass_route = _run_json_command(
        config.bass_command,
        (stem_paths or {}).get("bass"),
        engine="external_bass_transcriber",
        timeout_seconds=config.timeout_seconds,
    )
    if config.style_command:
        style_route = _run_json_command(
            config.style_command,
            original_path,
            engine="external_style_tagger",
            timeout_seconds=config.timeout_seconds,
        )
    else:
        style_route = _run_essentia_discogs(
            original_path,
            model_path=config.style_model_path,
            metadata_path=config.style_metadata_path,
            max_duration_seconds=config.style_max_duration_seconds,
        )
    instrument_route = _run_json_command(
        config.instrument_command,
        original_path,
        engine="external_instrument_tagger",
        timeout_seconds=config.timeout_seconds,
    )
    routes = {
        "drum_transcription": drum_route,
        "bass_transcription": bass_route,
        "style_tags": style_route,
        "instrument_tags": instrument_route,
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
