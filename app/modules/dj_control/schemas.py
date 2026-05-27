"""DJ Control schemas."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DanceStyleItem(BaseModel):
    key: str
    label_zh: str
    bpm_range: tuple[float, float]


class StyleListResponse(BaseModel):
    styles: list[DanceStyleItem]


class StylePickRequest(BaseModel):
    style: str
    target_duration_sec: float = Field(gt=0, le=24 * 3600)
    min_score: float = 0.35


class ScoredSong(BaseModel):
    song_id: str
    title: str
    artist: str
    bpm: float | None = None
    duration: float | None = None
    score: float
    energy: float | None = None


class StylePickResponse(BaseModel):
    style: str
    target_duration_sec: float
    achieved_duration_sec: float
    songs: list[ScoredSong]


class SequenceRequest(BaseModel):
    song_ids: list[str]
    preset: str = "warmup_to_peak"


class SequenceEntry(BaseModel):
    song_id: str
    position: int
    target_energy: float
    actual_energy: float
    breakdown: dict


class SequenceResponse(BaseModel):
    preset: str
    sequence: list[SequenceEntry]


class TransitionPlanRequest(BaseModel):
    prev_song_id: str
    next_song_id: str
    cursor_sec: float = 0.0
    rule_key: Optional[str] = None


class CutPlanRequest(BaseModel):
    strategy: str  # fast_cut | energy_up_cut | energy_down_cut
    current_song_id: str
    cursor_sec: float
    queue_song_ids: list[str]
    current_index: int
    pool_song_ids: list[str] = Field(default_factory=list)
    max_wait_sec: float = 5.0


class FxItem(BaseModel):
    key: str
    label_zh: str
    default_duration: float
    category: str | None = None


class FxListResponse(BaseModel):
    fx: list[FxItem]
