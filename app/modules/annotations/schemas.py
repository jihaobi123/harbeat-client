"""Contracts for Bar-level presence candidates and human revisions."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


PresenceElement = Literal["vocal", "drums", "bass", "melody"]
ELEMENT_NAMES = ("vocal", "drums", "bass", "melody")


class PresenceRange(BaseModel):
    start_bar_index: int = Field(ge=0)
    end_bar_index: int = Field(gt=0)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.end_bar_index <= self.start_bar_index:
            raise ValueError("end_bar_index must be greater than start_bar_index")
        return self


class TimelineBarSnapshot(BaseModel):
    index: int = Field(ge=0)
    start_sec: float = Field(ge=0)
    end_sec: float = Field(gt=0)
    beat_start_index: int = Field(ge=0)
    beat_count: int = Field(ge=1, le=32)
    is_partial: bool

    @model_validator(mode="after")
    def validate_time_bounds(self):
        if self.end_sec <= self.start_sec:
            raise ValueError("Bar end_sec must be greater than start_sec")
        return self


class TimelineSnapshot(BaseModel):
    source: Literal["downbeats", "beat_grid"]
    meter_numerator: int = Field(ge=1, le=32)
    confidence: float = Field(ge=0, le=1)
    version: str = Field(min_length=1)
    bars: list[TimelineBarSnapshot] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bar_indexes(self):
        if [bar.index for bar in self.bars] != list(range(len(self.bars))):
            raise ValueError("Timeline Bar indexes must be contiguous from zero")
        return self


class ElementCandidate(BaseModel):
    availability: Literal["available", "unavailable", "invalid"]
    requires_review: bool
    confidence_cap: float = Field(ge=0, le=1)
    bar_probabilities: list[float]
    bar_features: list[dict[str, Any]]
    candidate_ranges: list[PresenceRange]
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_probabilities(self):
        if any(value < 0 or value > self.confidence_cap for value in self.bar_probabilities):
            raise ValueError("Bar probabilities must respect confidence_cap")
        return self


class CandidateSnapshot(BaseModel):
    sample_rate: Optional[int] = Field(default=None, gt=0)
    elements: dict[PresenceElement, ElementCandidate]

    @model_validator(mode="after")
    def validate_elements(self):
        if set(self.elements) != set(ELEMENT_NAMES):
            raise ValueError("Candidate snapshot must contain all four elements")
        return self


class ElementReview(BaseModel):
    review_state: Literal["reviewed", "unknown", "rejected"]
    ranges: list[PresenceRange]

    @model_validator(mode="after")
    def validate_state_ranges(self):
        if self.review_state != "reviewed" and self.ranges:
            raise ValueError("unknown or rejected elements cannot contain ranges")
        return self


class ReviewRevision(BaseModel):
    revision: int = Field(ge=2)
    annotation_status: Literal["reviewed", "adjudicated"]
    actor_id: str = Field(min_length=1, max_length=128)
    created_at: datetime
    elements: dict[PresenceElement, ElementReview]

    @model_validator(mode="after")
    def validate_elements(self):
        if set(self.elements) != set(ELEMENT_NAMES):
            raise ValueError("Review revision must contain all four elements")
        return self


class PresenceAnnotationBundle(BaseModel):
    schema_name: Literal["harbeat.presence_annotation_bundle"]
    schema_version: Literal["1.0.0"]
    dataset_version: str = Field(min_length=1)
    track_id: str = Field(min_length=1, max_length=128)
    user_id: int = Field(gt=0)
    timeline: TimelineSnapshot
    candidate_source: str = Field(min_length=1)
    threshold_version: str = Field(min_length=1)
    revision: int = Field(ge=1)
    candidates: CandidateSnapshot
    revisions: list[ReviewRevision]
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_revision_sequence(self):
        expected = list(range(2, self.revision + 1))
        actual = [item.revision for item in self.revisions]
        if actual != expected:
            raise ValueError("Revision history must be contiguous from revision 2")
        return self


class PresenceReviewRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    elements: dict[PresenceElement, ElementReview]

    @model_validator(mode="after")
    def validate_elements(self):
        if set(self.elements) != set(ELEMENT_NAMES):
            raise ValueError("Review request must contain all four elements")
        return self
