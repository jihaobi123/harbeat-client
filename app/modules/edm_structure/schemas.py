"""Strict sidecar contracts for EDMFormer Shadow evidence."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
SHA256_PATTERN = r"^[a-fA-F0-9]{64}$"
EDM_LABELS = ("intro", "buildup", "drop", "breakdown", "outro", "silence")
EdmLabel = Literal["intro", "buildup", "drop", "breakdown", "outro", "silence"]


class ExpandedStructureHeadState(BaseModel):
    enabled: Literal[False] = False
    model_status: Literal["not_installed"] = "not_installed"
    model_version: Literal[None] = None
    input_contract_version: Literal["expanded_structure_input_v1"] = (
        "expanded_structure_input_v1"
    )
    output_contract_version: Literal["expanded_structure_output_v1"] = (
        "expanded_structure_output_v1"
    )

    model_config = ConfigDict(extra="forbid")


class EdmSegmentCandidate(BaseModel):
    canonical_section_id: str = Field(pattern=ID_PATTERN, min_length=1, max_length=128)
    start_bar_index: int = Field(ge=0)
    end_bar_index: int = Field(ge=1)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    canonical_boundary_source: Literal["songformer_bar_snap_v1"] = (
        "songformer_bar_snap_v1"
    )
    edmformer_label_candidate: EdmLabel
    edmformer_label_probabilities: dict[EdmLabel, float]
    edmformer_label_max_probabilities: dict[EdmLabel, float]
    edmformer_boundary_candidates: list[float] = Field(default_factory=list)
    validation_status: Literal["unreviewed", "reviewed", "rejected"] = "unreviewed"

    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "edmformer_label_probabilities", "edmformer_label_max_probabilities"
    )
    @classmethod
    def validate_probabilities(cls, value: dict[EdmLabel, float]) -> dict[EdmLabel, float]:
        if set(value) != set(EDM_LABELS):
            raise ValueError("all six EDM label probabilities are required")
        if any(probability < 0 or probability > 1 for probability in value.values()):
            raise ValueError("EDM probabilities must be between zero and one")
        return value

    @model_validator(mode="after")
    def validate_segment(self) -> "EdmSegmentCandidate":
        if self.end_bar_index <= self.start_bar_index or self.end_sec <= self.start_sec:
            raise ValueError("EDM segment ranges are invalid")
        total = sum(self.edmformer_label_probabilities.values())
        if abs(total - 1.0) > 1e-5:
            raise ValueError("mean EDM probabilities must be normalized")
        if self.edmformer_label_candidate != max(
            self.edmformer_label_probabilities,
            key=self.edmformer_label_probabilities.get,
        ):
            raise ValueError("candidate label must match the highest mean probability")
        if any(
            boundary <= self.start_sec or boundary >= self.end_sec
            for boundary in self.edmformer_boundary_candidates
        ):
            raise ValueError("comparison boundaries must fall inside the canonical block")
        return self


class EdmStructureAnalysisDocument(BaseModel):
    schema_name: Literal["harbeat.edm_structure_analysis"] = (
        "harbeat.edm_structure_analysis"
    )
    schema_version: Literal["0.1.0"] = "0.1.0"
    track_id: str = Field(pattern=ID_PATTERN, min_length=1, max_length=128)
    status: Literal["ready", "failed"]
    duration_sec: float = Field(gt=0)
    audio_sha256: str = Field(pattern=SHA256_PATTERN)
    timeline_fingerprint: str = Field(pattern=SHA256_PATTERN)
    songformer_sidecar_sha256: str = Field(pattern=SHA256_PATTERN)
    muq_sha256: str = Field(pattern=SHA256_PATTERN)
    musicfm_sha256: str = Field(pattern=SHA256_PATTERN)
    musicfm_stats_sha256: str = Field(pattern=SHA256_PATTERN)
    edmformer_sha256: str = Field(pattern=SHA256_PATTERN)
    deployment_status: Literal["shadow"] = "shadow"
    aggregation_version: Literal["edmformer_songformer_block_aggregation_v1"] = (
        "edmformer_songformer_block_aggregation_v1"
    )
    runtime_fingerprint: dict[str, object]
    segments: list[EdmSegmentCandidate]
    expanded_structure_head: ExpandedStructureHeadState = Field(
        default_factory=ExpandedStructureHeadState
    )
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = Field(default=None, max_length=4096)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_document(self) -> "EdmStructureAnalysisDocument":
        if self.status == "ready" and not self.segments:
            raise ValueError("ready EDM sidecar requires segments")
        if self.status == "failed" and (self.segments or not self.error):
            raise ValueError("failed EDM sidecar requires an error and no segments")
        previous_end_bar = -1
        for segment in self.segments:
            if segment.start_bar_index < previous_end_bar:
                raise ValueError("EDM segments must be monotonic and non-overlapping")
            if segment.end_sec > self.duration_sec + 1e-6:
                raise ValueError("EDM segment exceeds track duration")
            previous_end_bar = segment.end_bar_index
        return self

