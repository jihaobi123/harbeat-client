"""Bounded subprocess runner for the isolated EDMFormer Shadow runtime."""
from __future__ import annotations

import json
import math
from pathlib import Path
import shlex
import subprocess
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.edm_structure.schemas import EDM_LABELS, EdmLabel


SHA256_PATTERN = r"^[a-fA-F0-9]{64}$"


class EdmRuntimeError(RuntimeError):
    """The isolated runtime failed or returned an unsafe manifest."""


class EdmRuntimeFrame(BaseModel):
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    probabilities: dict[EdmLabel, float]

    model_config = ConfigDict(extra="forbid")

    @field_validator("probabilities")
    @classmethod
    def validate_probabilities(cls, value: dict[EdmLabel, float]) -> dict[EdmLabel, float]:
        if set(value) != set(EDM_LABELS):
            raise ValueError("all six EDM probabilities are required")
        if any(not math.isfinite(item) for item in value.values()):
            raise ValueError("runtime output contains a non-finite value")
        if any(item < 0 or item > 1 for item in value.values()):
            raise ValueError("runtime probabilities must be bounded")
        if abs(sum(value.values()) - 1.0) > 1e-5:
            raise ValueError("runtime probabilities must be normalized")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> "EdmRuntimeFrame":
        if self.end_sec <= self.start_sec:
            raise ValueError("runtime frame range is invalid")
        return self


class EdmRuntimeResult(BaseModel):
    track_id: str
    audio_path: str
    audio_sha256: str = Field(pattern=SHA256_PATTERN)
    duration_sec: float = Field(gt=0)
    status: Literal["ready", "failed"]
    frames: list[EdmRuntimeFrame]
    boundary_candidates: list[float]
    muq_sha256: str = Field(pattern=SHA256_PATTERN)
    musicfm_sha256: str = Field(pattern=SHA256_PATTERN)
    musicfm_stats_sha256: str = Field(pattern=SHA256_PATTERN)
    edmformer_sha256: str = Field(pattern=SHA256_PATTERN)
    runtime_fingerprint: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = Field(default=None, max_length=4096)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_result(self) -> "EdmRuntimeResult":
        if self.status == "ready" and (not self.frames or self.error):
            raise ValueError("ready runtime output requires frames and no error")
        if self.status == "failed" and (self.frames or not self.error):
            raise ValueError("failed runtime output requires an error and no frames")
        previous_end = -1.0
        for frame in self.frames:
            if frame.start_sec < previous_end - 1e-6:
                raise ValueError("runtime frames must be monotonic and non-overlapping")
            if frame.end_sec > self.duration_sec + 0.2:
                raise ValueError("runtime frame exceeds track duration")
            previous_end = frame.end_sec
        if any(
            not math.isfinite(boundary)
            or boundary <= 0
            or boundary >= self.duration_sec
            for boundary in self.boundary_candidates
        ):
            raise ValueError("runtime boundary candidate is invalid")
        if self.boundary_candidates != sorted(set(self.boundary_candidates)):
            raise ValueError("runtime boundary candidates must be unique and sorted")
        return self


class EdmStructureRunner:
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

    def _command(self, audio_path: Path) -> list[str]:
        if not self.command_template:
            raise EdmRuntimeError("EDMFormer command is not configured")
        if "{audio}" not in self.command_template or "{output_dir}" not in self.command_template:
            raise EdmRuntimeError("command must contain {audio} and {output_dir}")
        return [
            token.replace("{audio}", str(audio_path)).replace(
                "{output_dir}", str(self.work_dir)
            )
            for token in shlex.split(self.command_template)
        ]

    def _lock(self):
        import fcntl

        self.work_dir.mkdir(parents=True, exist_ok=True)
        handle = (self.work_dir / ".edmformer.lock").open("a+")
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

    def _read_result(self, audio_path: Path) -> EdmRuntimeResult:
        try:
            manifest = json.loads(
                (self.work_dir / "manifest.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise EdmRuntimeError("runtime manifest is missing or invalid") from exc
        if manifest.get("schema_name") != "harbeat.edmformer_runtime_manifest":
            raise EdmRuntimeError("runtime manifest has the wrong schema")
        tracks = manifest.get("tracks")
        if not isinstance(tracks, list):
            raise EdmRuntimeError("runtime manifest tracks are invalid")
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
            raise EdmRuntimeError("runtime manifest did not contain the requested audio")
        runtime_fingerprint = manifest.get("runtime_fingerprint")
        if not isinstance(runtime_fingerprint, dict) or not runtime_fingerprint:
            raise EdmRuntimeError("runtime fingerprint is missing")
        try:
            return EdmRuntimeResult.model_validate(
                {
                    **track,
                    "track_id": "placeholder",
                    "runtime_fingerprint": runtime_fingerprint,
                }
            )
        except ValueError as exc:
            if "non-finite" in str(exc):
                raise EdmRuntimeError("runtime manifest contains a non-finite value") from exc
            raise EdmRuntimeError("runtime manifest violates the contract") from exc

    def run(
        self, *, track_id: str, audio_path: Union[str, Path]
    ) -> EdmRuntimeResult:
        resolved_audio = Path(audio_path).expanduser().resolve()
        if not resolved_audio.is_file():
            raise EdmRuntimeError("audio file does not exist")
        lock_handle = self._lock()
        try:
            self._execute(self._command(resolved_audio))
            result = self._read_result(resolved_audio)
        finally:
            lock_handle.close()
        return result.model_copy(update={"track_id": track_id})
