"""Strict contracts for shared instrument-analysis Shadow sidecars."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
SHA256_PATTERN = r"^[a-fA-F0-9]{64}$"
DRUM_CLASSES = ("kick", "snare", "hihat", "tom", "cymbal")
INSTRUMENT_CLASSES = (
    "drums",
    "percussion",
    "bass",
    "acoustic_guitar",
    "electric_guitar",
    "piano",
    "electric_piano",
    "synthesizer",
    "strings",
    "brass",
    "woodwind",
    "organ",
    "sampler_fx",
    "voice",
)

Availability = Literal["available", "unavailable", "failed"]
ValidationStatus = Literal["unreviewed", "reviewed", "rejected"]
DrumClass = Literal["kick", "snare", "hihat", "tom", "cymbal"]
InstrumentClass = Literal[
    "drums",
    "percussion",
    "bass",
    "acoustic_guitar",
    "electric_guitar",
    "piano",
    "electric_piano",
    "synthesizer",
    "strings",
    "brass",
    "woodwind",
    "organ",
    "sampler_fx",
    "voice",
]


class ModelEvidence(BaseModel):
    model_id: str = Field(min_length=1, max_length=128)
    model_version: str = Field(min_length=1, max_length=128)
    deployment_status: Literal["shadow"] = "shadow"
    availability: Availability
    checkpoint_sha256: Optional[str] = Field(
        default=None, pattern=SHA256_PATTERN
    )
    source_revision: Optional[str] = Field(default=None, min_length=7, max_length=64)
    license_status: Literal["review_required", "approved", "blocked"]
    error: Optional[str] = Field(default=None, max_length=4096)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_evidence(self) -> "ModelEvidence":
        if self.availability == "available" and not self.checkpoint_sha256:
            raise ValueError("available model evidence requires a checkpoint hash")
        if self.availability == "failed" and not self.error:
            raise ValueError("failed model evidence requires an explicit error")
        return self


class DrumEvent(BaseModel):
    time_sec: float = Field(ge=0)
    drum_class: DrumClass
    confidence: float = Field(ge=0, le=1)
    bar_index: int = Field(ge=0)
    beat_index_in_bar: int = Field(ge=0)
    beat_position: float = Field(ge=1)

    model_config = ConfigDict(extra="forbid")


class DrumSummary(BaseModel):
    event_counts: dict[DrumClass, int]
    density_per_sec: float = Field(ge=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("event_counts")
    @classmethod
    def validate_counts(cls, value: dict[DrumClass, int]) -> dict[DrumClass, int]:
        if set(value) != set(DRUM_CLASSES):
            raise ValueError("event_counts must contain all five drum classes")
        if any(count < 0 for count in value.values()):
            raise ValueError("event counts cannot be negative")
        return value


class InstrumentProbability(BaseModel):
    instrument_class: InstrumentClass
    mean_probability: float = Field(ge=0, le=1)
    max_probability: float = Field(ge=0, le=1)
    active_coverage: float = Field(ge=0, le=1)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_probability_order(self) -> "InstrumentProbability":
        if self.max_probability < self.mean_probability:
            raise ValueError("max_probability cannot be below mean_probability")
        return self


class InstrumentBarAnalysis(BaseModel):
    bar_index: int = Field(ge=0)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    drum_events: list[DrumEvent] = Field(default_factory=list)
    drum_summary: DrumSummary
    instrument_probabilities: list[InstrumentProbability] = Field(default_factory=list)
    validation_status: ValidationStatus = "unreviewed"

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_bar(self) -> "InstrumentBarAnalysis":
        if self.end_sec <= self.start_sec:
            raise ValueError("bar end must be greater than start")
        seen: set[str] = set()
        for probability in self.instrument_probabilities:
            if probability.instrument_class in seen:
                raise ValueError("instrument probabilities must be unique per class")
            seen.add(probability.instrument_class)
        for event in self.drum_events:
            if event.bar_index != self.bar_index:
                raise ValueError("drum event bar_index does not match its parent bar")
            if not self.start_sec <= event.time_sec < self.end_sec:
                raise ValueError("drum event is outside its parent bar")
        return self


class InstrumentAnalysisDocument(BaseModel):
    schema_name: Literal["harbeat.instrument_analysis"] = "harbeat.instrument_analysis"
    schema_version: Literal["0.1.0"] = "0.1.0"
    track_id: str = Field(pattern=ID_PATTERN, min_length=1, max_length=128)
    status: Literal["ready", "partial", "failed"]
    duration_sec: float = Field(gt=0)
    audio_sha256: str = Field(pattern=SHA256_PATTERN)
    timeline_fingerprint: str = Field(pattern=SHA256_PATTERN)
    taxonomy_version: Literal["instrument_taxonomy@0.1.0"]
    aggregation_version: Literal["instrument_bar_aggregation_v1"] = (
        "instrument_bar_aggregation_v1"
    )
    runtime_fingerprint: dict[str, object]
    models: dict[Literal["adtof", "panns"], ModelEvidence]
    bars: list[InstrumentBarAnalysis]
    warnings: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_document(self) -> "InstrumentAnalysisDocument":
        if set(self.models) != {"adtof", "panns"}:
            raise ValueError("models must contain exactly adtof and panns")
        if self.status == "ready" and not self.bars:
            raise ValueError("ready document requires bar results")
        if self.status == "failed" and self.bars:
            raise ValueError("failed document cannot publish bar results")
        previous_index = -1
        previous_end = 0.0
        for bar in self.bars:
            if bar.bar_index <= previous_index or bar.start_sec < previous_end - 1e-6:
                raise ValueError("bars must be monotonic and non-overlapping")
            if bar.end_sec > self.duration_sec + 1e-6:
                raise ValueError("bar exceeds track duration")
            for event in bar.drum_events:
                if event.time_sec > self.duration_sec:
                    raise ValueError("event exceeds track duration")
            previous_index = bar.bar_index
            previous_end = bar.end_sec
        return self
