from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class SongTagUpdateRequest(BaseModel):
    bpm: Optional[int] = None
    energy: Optional[str] = None
    style: Optional[str] = None
    vocal_type: Optional[str] = None
    era_tag: Optional[str] = None
    groove_tag: Optional[str] = None
    difficulty_fit: Optional[str] = None
    tags: list[str] = []


class UpsertSongRequest(BaseModel):
    title: str
    artist: str
    bpm: Optional[int] = None
    energy: list[str] = []
    scenes: list[str] = []
    tags: list[str] = []


class CueCreateRequest(BaseModel):
    user_id: int
    song_id: int
    cue_type: str
    start_time: float
    end_time: Optional[float] = None
    label: Optional[str] = None


class CueData(BaseModel):
    id: int
    cue_type: str
    start_time: float
    end_time: Optional[float] = None
    label: Optional[str] = None


class SongData(BaseModel):
    id: int
    title: str
    artist: str
    audio_url: Optional[str] = None
    duration: Optional[float] = None
    bpm: Optional[int] = None
    energy: Optional[str] = None
    style: Optional[str] = None
    vocal_type: Optional[str] = None
    era_tag: Optional[str] = None
    groove_tag: Optional[str] = None
    difficulty_fit: Optional[str] = None
    tags: list[str] = []


class SongListData(BaseModel):
    songs: list[SongData]


class SongProcessRequest(BaseModel):
    styles: list[str] = Field(default_factory=list)
    bpm: Optional[int] = None
    energy: Optional[str] = None
    # balanced: 默认；hq: 更高质量（更耗时）；fast: 更快预览
    quality_mode: Literal["balanced", "hq", "fast"] = "balanced"


class SongProcessStyleMeta(BaseModel):
    selected_models: dict[str, str] = Field(default_factory=dict)
    bpm: Optional[int] = None
    energy: Optional[str] = None
    note: Optional[str] = None


class SongProcessResult(BaseModel):
    song_id: int
    processed_files: dict[str, str] = Field(default_factory=dict)
    meta: dict[str, SongProcessStyleMeta] = Field(default_factory=dict)
