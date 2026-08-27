"""Optional dedicated drum-transcription worker adapter.

The current feature pipeline consumes only detailed drum events from an
external model. Bass identity, pitch motion and production descriptors are
owned by the current time-frequency modules, so obsolete model routes are not
started here.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
import shlex
import subprocess
import time
from typing import Any


MODEL_ADAPTER_VERSION = "drum_model_adapter_v2"


@dataclass(frozen=True)
class FeatureModelConfig:
    drum_command: str | None
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "FeatureModelConfig":
        return cls(
            drum_command=os.getenv("FEATURE_DRUM_TRANSCRIBER_COMMAND") or None,
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


def collect_mature_model_evidence(
    stem_paths: dict[str, str] | None,
    *,
    original_path: str | None = None,
    config: FeatureModelConfig | None = None,
) -> dict[str, Any]:
    """Collect the one mature-model route consumed by the current pipeline."""
    del original_path
    config = config or FeatureModelConfig.from_env()
    route = _run_json_command(
        config.drum_command,
        (stem_paths or {}).get("drums"),
        engine="external_drum_transcriber",
        timeout_seconds=config.timeout_seconds,
    )
    routes = {"drum_transcription": route}
    ready = [name for name, value in routes.items() if value["status"] == "ready"]
    failed = [name for name, value in routes.items() if value["status"] == "error"]
    return {
        "version": MODEL_ADAPTER_VERSION,
        "status": "ready" if ready else ("error" if failed else "unavailable"),
        "ready_routes": ready,
        "failed_routes": failed,
        "routes": routes,
    }
