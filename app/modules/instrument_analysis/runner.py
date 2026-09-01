"""Bounded subprocess runner for isolated ADTOF and PANNs inference."""
from __future__ import annotations

import json
import math
from pathlib import Path
import shlex
import subprocess
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InstrumentRuntimeError(RuntimeError):
    """The isolated runtime failed or returned an unsafe manifest."""


class RuntimeModelResult(BaseModel):
    availability: Literal["available", "unavailable", "failed"]
    checkpoint_sha256: Optional[str] = None
    source_revision: Optional[str] = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    windows: list[dict[str, Any]] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    elapsed_seconds: float = Field(ge=0)
    peak_cuda_bytes: int = Field(ge=0)
    error: Optional[str] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("events", "windows")
    @classmethod
    def validate_finite_payloads(cls, values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def visit(value: Any) -> None:
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("runtime output contains a non-finite value")
            if isinstance(value, dict):
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(values)
        return values


class InstrumentRuntimeResult(BaseModel):
    track_id: str
    audio_path: str
    audio_sha256: str
    duration_sec: float = Field(gt=0)
    status: Literal["ready", "partial", "failed"]
    runtime_fingerprint: dict[str, Any]
    models: dict[Literal["adtof", "panns"], RuntimeModelResult]
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_models(self) -> "InstrumentRuntimeResult":
        if set(self.models) != {"adtof", "panns"}:
            raise ValueError("runtime must report both models")
        return self


class InstrumentAnalysisRunner:
    def __init__(
        self,
        *,
        command_template: str,
        work_dir: Union[str, Path],
        timeout_sec: int,
    ):
        self.command_template = str(command_template).strip()
        self.work_dir = Path(work_dir).expanduser().resolve()
        self.timeout_sec = max(10, int(timeout_sec))

    def _command(self, audio_path: Path, drums_stem: Optional[Path]) -> list[str]:
        if not self.command_template:
            raise InstrumentRuntimeError("instrument-analysis command is not configured")
        if "{audio}" not in self.command_template or "{output_dir}" not in self.command_template:
            raise InstrumentRuntimeError("command must contain {audio} and {output_dir}")
        raw_tokens = shlex.split(self.command_template)
        command: list[str] = []
        skip_next = False
        for index, token in enumerate(raw_tokens):
            if skip_next:
                skip_next = False
                continue
            if drums_stem is None and token in {"--drums-stem", "--drums_stem"}:
                if index + 1 < len(raw_tokens) and "{drums_stem}" in raw_tokens[index + 1]:
                    skip_next = True
                continue
            if drums_stem is None and "{drums_stem}" in token:
                continue
            command.append(
                token.replace("{audio}", str(audio_path))
                .replace("{output_dir}", str(self.work_dir))
                .replace("{drums_stem}", str(drums_stem) if drums_stem else "")
            )
        return command

    def _lock(self):
        import fcntl

        self.work_dir.mkdir(parents=True, exist_ok=True)
        handle = (self.work_dir / ".instrument-analysis.lock").open("a+")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    def _execute(self, command: list[str]) -> None:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=self.timeout_sec,
            shell=False,
        )

    def _read_result(self, audio_path: Path) -> InstrumentRuntimeResult:
        try:
            manifest = json.loads((self.work_dir / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InstrumentRuntimeError("runtime manifest is missing or invalid") from exc
        tracks = manifest.get("tracks")
        if not isinstance(tracks, list):
            raise InstrumentRuntimeError("runtime manifest tracks are invalid")
        requested = str(audio_path.expanduser().resolve())
        track = next(
            (
                item
                for item in tracks
                if isinstance(item, dict) and str(item.get("audio_path", "")) == requested
            ),
            None,
        )
        if track is None:
            raise InstrumentRuntimeError("runtime manifest did not contain the requested audio")
        runtime_fingerprint = manifest.get("runtime_fingerprint")
        if not isinstance(runtime_fingerprint, dict) or not runtime_fingerprint:
            raise InstrumentRuntimeError("runtime fingerprint is missing")
        try:
            return InstrumentRuntimeResult.model_validate(
                {
                    **track,
                    "track_id": "placeholder",
                    "runtime_fingerprint": runtime_fingerprint,
                }
            )
        except ValueError as exc:
            message = str(exc)
            if "non-finite" in message:
                raise InstrumentRuntimeError("runtime manifest contains non-finite values") from exc
            raise InstrumentRuntimeError("runtime manifest violates the contract") from exc

    def run(
        self,
        *,
        track_id: str,
        audio_path: Union[str, Path],
        stems: dict[str, str],
    ) -> InstrumentRuntimeResult:
        resolved_audio = Path(audio_path).expanduser().resolve()
        if not resolved_audio.is_file():
            raise InstrumentRuntimeError("audio file does not exist")
        raw_drums = stems.get("drums")
        drums_stem = Path(raw_drums).expanduser().resolve() if raw_drums else None
        if drums_stem is not None and not drums_stem.is_file():
            drums_stem = None
        lock_handle = self._lock()
        try:
            self._execute(self._command(resolved_audio, drums_stem))
            result = self._read_result(resolved_audio)
        finally:
            lock_handle.close()
        warnings = list(result.warnings)
        if drums_stem is None and "DRUMS_STEM_MISSING" not in warnings:
            warnings.append("DRUMS_STEM_MISSING")
        return result.model_copy(update={"track_id": track_id, "warnings": warnings})

