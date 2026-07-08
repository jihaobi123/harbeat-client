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
    target_duration_sec: float | None = Field(default=None, gt=0, le=24 * 3600)
    min_score: float = 0.35
    mode: str | None = None
    bpm_min: float | None = Field(default=None, ge=0, le=400)
    bpm_max: float | None = Field(default=None, ge=0, le=400)


class BpmBucketItem(BaseModel):
    label: str
    min_bpm: float
    max_bpm: float
    count: int


class ScoredSong(BaseModel):
    song_id: str
    title: str
    artist: str
    bpm: float | None = None
    camelot_key: str | None = None
    duration: float | None = None
    score: float
    energy: float | None = None
    analysis_status: str | None = None
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
    target_duration_sec: float | None = None
    achieved_duration_sec: float
    songs: list[ScoredSong]
    bpm_buckets: list[BpmBucketItem] = Field(default_factory=list)


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
    ordering_mode: str | None = None
    pair_scores: list[dict] = Field(default_factory=list)
    pair_breakdowns: list[dict] = Field(default_factory=list)


class TransitionPlanRequest(BaseModel):
    prev_song_id: str
    next_song_id: str
    cursor_sec: float = 0.0
    rule_key: Optional[str] = None
    transition_mode: str = "ordinary_xfade"
    eq_mix_user_mode: str = "auto"
    target_style: Optional[str] = None
    mix_preset: Optional[str] = None  # auto/fade/rise/blend/cut/overlap
    apply_phrase_alignment: bool = False
    target_lufs: Optional[float] = None


class SpotifyDecideRequest(BaseModel):
    prev_song_id: str
    next_song_id: str
    user_preference: str = "auto"  # auto/fade/rise/blend/cut/overlap


class SmartReorderRequest(BaseModel):
    song_ids: list[str]
    bpm_tolerance: float = 0.03
    prefer_energy_flow: bool = True


class SpotifyEQRequest(BaseModel):
    eq_type: str  # three_band_fade/mid_bass_swap/tail_bass_swap/head_bass_swap
    duration_beats: int = 32
    bpm: float = 120.0


class SpotifyFilterRequest(BaseModel):
    filter_type: str  # lowpass_in/lowpass_out/highpass_in/highpass_out
    duration_beats: int = 16
    bpm: float = 120.0


class SpotifyVolumeRequest(BaseModel):
    curve_type: str  # equal_power_sine/linear/exponential/smooth/overlap/quick_out/instant
    duration_beats: int = 16
    bpm: float = 120.0


class CutPlanRequest(BaseModel):
    strategy: str | None = None  # fast_cut | energy_up_cut | energy_down_cut | target_* intents
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
    # For target_dance_style intent
    target_style: str | None = None
    style_reserve_pool_song_ids: list[str] = Field(default_factory=list)


class LivePoolPrepareRequest(BaseModel):
    active_queue_song_ids: list[str]
    style: str | None = None
    target_reserve_per_bucket: int = Field(default=2, ge=1, le=5)
    include_buckets: list[str] = Field(default_factory=list)
    exclude_song_ids: list[str] = Field(default_factory=list)
    # For style reserve pool
    target_style_reserve_per_style: int = Field(default=2, ge=1, le=5)
    include_styles: list[str] = Field(default_factory=list)


class StylePoolStatus(BaseModel):
    available: int
    cached: int
    syncing: int
    status: str  # ready | syncing | empty | insufficient


class LivePoolPrepareResponse(BaseModel):
    active_queue: list[str]
    reserve_pool: dict[str, list[str]]
    energy_profiles: dict
    sync_priority: dict[str, list[str]]
    # For style reserve pool
    style_reserve_pool: dict[str, list[str]] = Field(default_factory=dict)
    style_pool_status: dict[str, StylePoolStatus] = Field(default_factory=dict)


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


class TargetStyleSelectedSong(BaseModel):
    song_id: str
    title: str
    artist: str
    style_score: float
    confidence: float
    matched_labels: list[str] = Field(default_factory=list)
    energy_score: float
    cache_status: str  # ready | syncing | not_cached | failed
    source: str  # active_queue | style_reserve_pool | library_fallback


class TargetStyleCutResponse(BaseModel):
    intent: str  # target_dance_style
    current_song: dict
    target_style: str
    selected_song: TargetStyleSelectedSong
    queue_action: dict
    candidate_score: float
    score_breakdown: dict
    recommended_transition_hint: str | None = None
    reason: list[str] = Field(default_factory=list)
    fallback: bool = False
    fallback_reason: str | None = None
