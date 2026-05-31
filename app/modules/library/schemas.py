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
    music_features: dict = Field(default_factory=dict)
    dance_styles: list[dict] = Field(default_factory=list)
    dance_style_scores: dict = Field(default_factory=dict)
    dance_style_status: str = "none"
    analysis_status: str = "none"
    beat_points: list[float] = Field(default_factory=list)
    bpm_curve: list[dict] = Field(default_factory=list)
    tempo_stability: float | None = None
    beat_confidence: float | None = None
    beat_confidence_details: dict = Field(default_factory=dict)
    beat_grid_offset: float | None = None
    beat_grid_interval: float | None = None
    beat_engines_used: list[str] = Field(default_factory=list)
    beat_needs_review: bool = False
    energy_curve: list[dict] = Field(default_factory=list)
    loudness_profile: dict = Field(default_factory=dict)
    transition_windows: list[dict] = Field(default_factory=list)
    stem_activity: dict = Field(default_factory=dict)
    stem_activity_windows: list[dict] = Field(default_factory=list)
    stem_quality_score: float | None = None
    intro_is_clean: bool = False
    outro_is_clean: bool = False
    has_drum_loop: bool = False
    cue_points: list[LibraryCuePoint] = Field(default_factory=list)
    downbeats: list[float] = Field(default_factory=list)
    phrase_map: list[dict] = Field(default_factory=list)
    key_confidence: float | None = None
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
    music_features: dict | None = None
    dance_styles: list[dict] | None = None
    dance_style_scores: dict | None = None
    dance_style_status: str | None = None
    analysis_status: str | None = None
    beat_points: list[float] | None = None
    bpm_curve: list[dict] | None = None
    tempo_stability: float | None = None
    beat_confidence: float | None = None
    beat_confidence_details: dict | None = None
    beat_grid_offset: float | None = None
    beat_grid_interval: float | None = None
    beat_engines_used: list[str] | None = None
    beat_needs_review: bool | None = None
    energy_curve: list[dict] | None = None
    loudness_profile: dict | None = None
    transition_windows: list[dict] | None = None
    stem_activity: dict | None = None
    stem_activity_windows: list[dict] | None = None
    stem_quality_score: float | None = None
    intro_is_clean: bool | None = None
    outro_is_clean: bool | None = None
    has_drum_loop: bool | None = None
    cue_points: list[LibraryCuePoint] | None = None
    downbeats: list[float] | None = None
    phrase_map: list[dict] | None = None
    key_confidence: float | None = None
    stems: dict | None = None


class LibrarySongData(LibrarySongBase):
    user_id: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LibrarySongListData(BaseModel):
    songs: list[LibrarySongData]
