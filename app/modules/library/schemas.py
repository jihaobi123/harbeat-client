from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LibraryCuePoint(BaseModel):
    id: str
    time: float
    label: str
    color: str


class LibrarySongBase(BaseModel):
    id: str
    title: str
    artist: str
    duration: float = 0
    format: str
    file_size: int = 0
    source_type: str
    source_path: str = ""
    platform_id: str | None = None
    platform_url: str | None = None
    bpm: float | None = None
    key: str | None = None
    camelot_key: str | None = None
    energy: float | None = None
    genres: list[dict] = Field(default_factory=list)
    genre_status: str = "none"
    genre_source: str | None = None
    music_features: dict = Field(default_factory=dict)
    dance_styles: list[dict] = Field(default_factory=list)
    dance_style_scores: dict = Field(default_factory=dict)
    dance_style_status: str = "none"
    classifier_params: dict = Field(default_factory=dict)
    classifier_version: str | None = None
    analysis_status: str = "none"
    beat_points: list[float] = Field(default_factory=list)
    cue_points: list[LibraryCuePoint] = Field(default_factory=list)
    beat_confidence: float | None = None
    beat_grid_offset: float | None = None
    beat_grid_interval: float | None = None
    beat_engines_used: list[str] = Field(default_factory=list)
    beat_needs_review: int = 0
    stems: dict | None = None
    song_id: int | None = None
    created_at: datetime


class LibrarySongCreateRequest(LibrarySongBase):
    user_id: int


class LibrarySongUpdateRequest(BaseModel):
    title: str | None = None
    artist: str | None = None
    duration: float | None = None
    format: str | None = None
    file_size: int | None = None
    source_type: str | None = None
    source_path: str | None = None
    platform_id: str | None = None
    platform_url: str | None = None
    bpm: float | None = None
    key: str | None = None
    camelot_key: str | None = None
    energy: float | None = None
    genres: list[dict] | None = None
    genre_status: str | None = None
    genre_source: str | None = None
    music_features: dict | None = None
    dance_styles: list[dict] | None = None
    dance_style_scores: dict | None = None
    dance_style_status: str | None = None
    classifier_params: dict | None = None
    classifier_version: str | None = None
    analysis_status: str | None = None
    beat_points: list[float] | None = None
    cue_points: list[LibraryCuePoint] | None = None
    beat_confidence: float | None = None
    beat_grid_offset: float | None = None
    beat_grid_interval: float | None = None
    beat_engines_used: list[str] | None = None
    beat_needs_review: bool | None = None
    stems: dict | None = None


class DanceStyleClassifyRequest(BaseModel):
    params: dict = Field(default_factory=dict)
    top_k: int = Field(5, ge=1, le=13)
    threshold: float = Field(0.35, ge=0.0, le=1.0)


class BeatCorrectionRequest(BaseModel):
    """Manual beat/BPM correction from human review."""
    bpm: float | None = None
    grid_offset: float | None = None
    downbeat_phase: int | None = Field(None, ge=0, le=3)


class LibrarySongData(LibrarySongBase):
    user_id: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LibrarySongListData(BaseModel):
    songs: list[LibrarySongData]
