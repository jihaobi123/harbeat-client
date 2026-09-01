"""Strict shared SongFormer section results for the annotation Pilot.

These sidecars are model candidates shared by every annotator. They are kept
outside the per-user annotation store so rerunning SongFormer never rewrites
human labels.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Literal, Mapping, Optional, Sequence, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SAFE_TRACK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
RELABELER_INPUT_CONTRACT = "songformer_section_relabeler_input_v1"
RELABELER_OUTPUT_CONTRACT = "songformer_section_relabeler_output_v1"


class SongFormerSectionInvalid(ValueError):
    """A SongFormer sidecar is unsafe or violates the frozen contract."""


class RelabelerState(BaseModel):
    """Frozen placeholder for the residual classifier that is not deployed."""

    enabled: Literal[False] = False
    mode: Literal["disabled"] = "disabled"
    model_status: Literal["not_installed"] = "not_installed"
    model_version: Literal[None] = None
    input_contract_version: Literal[
        "songformer_section_relabeler_input_v1"
    ] = RELABELER_INPUT_CONTRACT
    output_contract_version: Literal[
        "songformer_section_relabeler_output_v1"
    ] = RELABELER_OUTPUT_CONTRACT

    model_config = ConfigDict(extra="forbid")


class SongFormerSegment(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    label: str = Field(min_length=1, max_length=64)
    label_probabilities: dict[str, float] = Field(default_factory=dict)
    label_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    label_margin: Optional[float] = Field(default=None, ge=0, le=1)

    model_config = ConfigDict(extra="forbid")

    @field_validator("label_probabilities")
    @classmethod
    def validate_probabilities(cls, value: dict[str, float]) -> dict[str, float]:
        for label, probability in value.items():
            if not label or probability < 0.0 or probability > 1.0:
                raise ValueError("label probabilities must use named values between 0 and 1")
        return value

    @model_validator(mode="after")
    def validate_time(self) -> "SongFormerSegment":
        if self.end <= self.start:
            raise ValueError("segment end must be greater than start")
        return self


class SongFormerSectionDocument(BaseModel):
    schema_name: Literal["harbeat.songformer_sections"] = "harbeat.songformer_sections"
    schema_version: Literal["1.0.0"] = "1.0.0"
    track_id: str = Field(min_length=1, max_length=128, pattern=SAFE_TRACK_ID.pattern)
    status: Literal["ready", "failed"] = "ready"
    audio_fingerprint: str = Field(min_length=1, max_length=256)
    runtime_fingerprint: dict[str, Any]
    cache_namespace: Optional[str] = None
    segments: list[SongFormerSegment]
    relabeler: RelabelerState = Field(default_factory=RelabelerState)
    error: Optional[str] = Field(default=None, max_length=4096)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_document(self) -> "SongFormerSectionDocument":
        if self.status == "ready" and not self.segments:
            raise ValueError("ready document requires segments")
        if self.status == "failed" and self.segments:
            raise ValueError("failed document cannot publish partial segments")
        previous_end: Optional[float] = None
        for segment in self.segments:
            if previous_end is not None and segment.start < previous_end - 1e-6:
                raise ValueError("SongFormer segments overlap or are not monotonic")
            previous_end = segment.end
        return self


def songformer_document(
    *,
    track_id: str,
    audio_fingerprint: str,
    runtime_fingerprint: Mapping[str, Any],
    segments: Sequence[Union[Mapping[str, Any], SongFormerSegment]],
    cache_namespace: Optional[str] = None,
    status: Literal["ready", "failed"] = "ready",
    error: Optional[str] = None,
) -> SongFormerSectionDocument:
    """Build a validated document with the classifier explicitly disabled."""

    return SongFormerSectionDocument(
        track_id=track_id,
        status=status,
        audio_fingerprint=audio_fingerprint,
        runtime_fingerprint=dict(runtime_fingerprint),
        cache_namespace=cache_namespace,
        segments=list(segments),
        relabeler=RelabelerState(),
        error=error,
    )


class SongFormerSectionStore:
    """Atomic filesystem store for shared model candidates."""

    def __init__(self, root: Union[str, Path]):
        self.root = Path(root).expanduser()

    @staticmethod
    def _validate_track_id(track_id: str) -> str:
        if not isinstance(track_id, str) or not SAFE_TRACK_ID.fullmatch(track_id):
            raise SongFormerSectionInvalid("unsafe SongFormer track_id")
        return track_id

    def _path(self, track_id: str) -> Path:
        return self.root / f"{self._validate_track_id(track_id)}.json"

    def load(self, track_id: str) -> Optional[SongFormerSectionDocument]:
        path = self._path(track_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            document = SongFormerSectionDocument.model_validate(payload)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise SongFormerSectionInvalid(
                f"SongFormer sidecar for {track_id} is invalid"
            ) from exc
        if document.track_id != track_id:
            raise SongFormerSectionInvalid("SongFormer sidecar track_id mismatch")
        return document

    def save(self, document: SongFormerSectionDocument) -> None:
        path = self._path(document.track_id)
        self.root.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(
            document.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        temporary_path: Optional[Path] = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f".{document.track_id}.songformer-",
                suffix=".tmp",
                dir=self.root,
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, path)
            temporary_path = None
        except OSError as exc:
            raise SongFormerSectionInvalid(
                f"SongFormer sidecar for {document.track_id} could not be saved"
            ) from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
