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
    score_breakdown: dict = Field(default_factory=dict)
    confidence: float | None = None
    matched_labels: list[str] = Field(default_factory=list)
    recommendation_reason: list[str] = Field(default_factory=list)
    final_pick_score: float | None = None
    style_evidence_status: str | None = None
    external_sources: dict = Field(default_factory=dict)
    reason: list[str] = Field(default_factory=list)


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
    cursor_sec: float = 0.0
    queue_song_ids: list[str] = Field(default_factory=list)
    current_index: int = 0
    pool_song_ids: list[str] = Field(default_factory=list)
    max_wait_sec: float = 5.0
    intent: str | None = None
    active_queue_song_ids: list[str] = Field(default_factory=list)
    reserve_pool_song_ids: list[str] = Field(default_factory=list)
    played_song_ids: list[str] = Field(default_factory=list)
    blocked_song_ids: list[str] = Field(default_factory=list)
    exclude_song_ids: list[str] = Field(default_factory=list)
    cached_song_ids: list[str] = Field(default_factory=list)
    syncing_song_ids: list[str] = Field(default_factory=list)
    target_energy_bucket: dict | None = None
    current_style: str | None = None
    prefer_cached: bool = True
    mode: str = "preview"


class LivePoolPrepareRequest(BaseModel):
    active_queue_song_ids: list[str]
    style: str | None = None
    target_reserve_per_bucket: int = Field(default=2, ge=1, le=5)
    include_buckets: list[str] = Field(default_factory=list)
    exclude_song_ids: list[str] = Field(default_factory=list)


class LivePoolPrepareResponse(BaseModel):
    active_queue: list[str]
    reserve_pool: dict[str, list[str]]
    energy_profiles: dict
    sync_priority: dict[str, list[str]]


class FxItem(BaseModel):
    key: str
    label_zh: str
    default_duration: float
    category: str | None = None
    # When set, mobile should trigger this FX on the RK speaker via
    # POST /trigger {key: rk_key} rather than playing the rendered wav
    # through the phone's local audio.
    rk_key: int | None = None


class FxListResponse(BaseModel):
    fx: list[FxItem]
