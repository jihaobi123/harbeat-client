"""Typed contracts used by the assisted annotation API and store."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Granularity = Literal["track", "section", "bar", "beat", "event"]
AnnotationStatus = Literal["candidate", "annotated", "reviewed", "adjudicated", "rejected"]


class AnnotationRecord(BaseModel):
    schema_name: Literal["harbeat.annotation_record"] = "harbeat.annotation_record"
    schema_version: Literal["1.0.0"] = "1.0.0"
    annotation_id: str = Field(min_length=1, max_length=128)
    dataset_version: str = Field(min_length=1)
    track_id: str = Field(min_length=1, max_length=128)
    task_id: str = Field(min_length=1, max_length=128)
    granularity: Granularity
    start_sec: float | None = Field(default=None, ge=0)
    end_sec: float | None = Field(default=None, gt=0)
    start_bar_index: int | None = Field(default=None, ge=0)
    end_bar_index: int | None = Field(default=None, ge=1)
    value: Any
    annotator_id: str = Field(min_length=1, max_length=128)
    annotation_status: AnnotationStatus
    annotator_confidence: float | None = Field(default=None, ge=0, le=1)
    candidate_source: str | None = None
    created_at: str

    model_config = ConfigDict(extra="forbid")

    @field_validator("created_at")
    @classmethod
    def validate_utc_timestamp(cls, value: str) -> str:
        if not value.endswith("Z"):
            raise ValueError("created_at must be a UTC timestamp ending in Z")
        try:
            datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError as exc:
            raise ValueError("created_at must be an ISO-8601 timestamp") from exc
        return value

    @model_validator(mode="after")
    def validate_ranges(self) -> "AnnotationRecord":
        if (self.start_sec is None) != (self.end_sec is None):
            raise ValueError("start_sec and end_sec must both be set or both be null")
        if self.start_sec is not None and self.end_sec <= self.start_sec:
            raise ValueError("end_sec must be greater than start_sec")
        if (self.start_bar_index is None) != (self.end_bar_index is None):
            raise ValueError("start_bar_index and end_bar_index must both be set or both be null")
        if self.start_bar_index is not None and self.end_bar_index <= self.start_bar_index:
            raise ValueError("end_bar_index must be greater than start_bar_index")
        return self


class StoredAnnotationSet(BaseModel):
    schema_name: Literal["harbeat.annotation_set"] = "harbeat.annotation_set"
    schema_version: Literal["1.0.0"] = "1.0.0"
    dataset_version: str
    track_id: str
    timeline_fingerprint: str = ""
    revision: int = Field(default=0, ge=0)
    annotations: list[AnnotationRecord] = Field(default_factory=list)
    updated_at: str | None = None

    model_config = ConfigDict(extra="forbid")

