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
    analysis_status: str = "none"
    beat_points: list[float] = Field(default_factory=list)
    cue_points: list[LibraryCuePoint] = Field(default_factory=list)
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
    analysis_status: str | None = None
    beat_points: list[float] | None = None
    cue_points: list[LibraryCuePoint] | None = None
    stems: dict | None = None


class LibrarySongData(LibrarySongBase):
    user_id: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LibrarySongListData(BaseModel):
    songs: list[LibrarySongData]
