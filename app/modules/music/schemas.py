from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class SongTagUpdateRequest(BaseModel):
    bpm: Optional[int] = None
    energy: Optional[str] = None
    style: Optional[str] = None
    vocal_type: Optional[str] = None
    era_tag: Optional[str] = None
    groove_tag: Optional[str] = None
    difficulty_fit: Optional[str] = None
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
