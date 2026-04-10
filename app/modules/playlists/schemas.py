from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SongImportItem(BaseModel):
    title: str
    artist: str
    audio_url: Optional[str] = None
    duration: Optional[float] = None
    bpm: Optional[float] = None
    tags: list[str] = []


class PlaylistImportRequest(BaseModel):
    user_id: int
    playlist_name: str
    songs: list[SongImportItem]
    source_type: str = "manual"


class PlaylistImportData(BaseModel):
    playlist_id: int
    import_count: int
    pending_analysis_count: int


class PlaylistSummaryData(BaseModel):
    id: int
    user_id: int
    playlist_name: str
    source_type: str
    song_count: int


class PlaylistSongData(BaseModel):
    song_id: int
    library_song_id: Optional[str] = None
    title: str
    artist: str
    audio_url: Optional[str] = None
    duration: Optional[float] = None
    bpm: Optional[float] = None
    key: Optional[str] = None
    energy: Optional[float] = None
    format: Optional[str] = None
    analysis_status: Optional[str] = None
    tags: list[str] = []
    order_index: int


class PlaylistDetailData(BaseModel):
    id: int
    user_id: int
    playlist_name: str
    source_type: str
    songs: list[PlaylistSongData]


class PlaylistListData(BaseModel):
    playlists: list[PlaylistSummaryData]


class PlaylistSongTagUpdateRequest(BaseModel):
    tags: list[str]


class PlaylistSongOrderItem(BaseModel):
    song_id: int
    order_index: int


class PlaylistReorderRequest(BaseModel):
    songs: list[PlaylistSongOrderItem]


class StyleMixRequest(BaseModel):
    style: str
    duration_minutes: int = 30
    bpm: Optional[int] = None
    energy: Optional[str] = None
    playlist_id: Optional[int] = None
    quality_mode: Literal["balanced", "hq", "fast"] = "balanced"
    random_seed: Optional[int] = None
    diversity: float = Field(default=0.35, ge=0.0, le=1.0)
    user_id: Optional[int] = None


class StyleMixResult(BaseModel):
    playlist: list[PlaylistSongData] = Field(default_factory=list)
    processed_files: dict[int, str] = Field(default_factory=dict)
    meta: dict[int, dict[str, str]] = Field(default_factory=dict)


class DjFxAutomationPoint(BaseModel):
    target: Literal["from", "to"] = "to"
    time_sec: float
    gain_db: float = 0.0
    lowpass_hz: float = 18000.0
    highpass_hz: float = 30.0
    eq_low_db: float = 0.0
    eq_mid_db: float = 0.0
    eq_high_db: float = 0.0


class DjTransitionPlanItem(BaseModel):
    from_song_id: int
    to_song_id: int
    entry_beat: int
    exit_beat: int
    entry_time_sec: Optional[float] = None
    exit_time_sec: Optional[float] = None
    from_beat_interval_sec: Optional[float] = None
    to_beat_interval_sec: Optional[float] = None
    phase_anchor_sec: Optional[float] = None
    crossfade_sec: float
    tempo_ratio: float
    key_relation: str
    transition_technique: str = "crossfade"
    energy_target: str
    fx_automation: list[DjFxAutomationPoint] = Field(default_factory=list)
    score: float = 0.0


class DjMixPlanRequest(BaseModel):
    style: str
    duration_minutes: int = 30
    bpm: Optional[int] = None
    energy: Optional[str] = None
    playlist_id: Optional[int] = None
    quality_mode: Literal["balanced", "hq", "fast"] = "balanced"
    strict_harmonic: bool = False
    max_tempo_shift: float = 0.08
    random_seed: Optional[int] = None
    diversity: float = Field(default=0.35, ge=0.0, le=1.0)
    candidate_window: int = Field(default=4, ge=1, le=8)
    user_id: Optional[int] = None


class DjMixPlanResult(BaseModel):
    playlist: list[PlaylistSongData] = Field(default_factory=list)
    processed_files: dict[int, str] = Field(default_factory=dict)
    meta: dict[int, dict[str, str]] = Field(default_factory=dict)
    transition_plan: list[DjTransitionPlanItem] = Field(default_factory=list)


class DjOfflineMixRequest(BaseModel):
    style: str
    duration_minutes: int = 30
    bpm: Optional[int] = None
    energy: Optional[str] = None
    playlist_id: Optional[int] = None
    quality_mode: Literal["balanced", "hq", "fast"] = "balanced"
    strict_harmonic: bool = False
    max_tempo_shift: float = 0.08
    random_seed: Optional[int] = None
    diversity: float = Field(default=0.35, ge=0.0, le=1.0)
    candidate_window: int = Field(default=4, ge=1, le=8)
    user_id: Optional[int] = None
    output_format: Literal["wav", "mp3", "both"] = "both"
    output_name: str = "final_mix"
    stem_aware: bool = True
    auto_separate_stems: bool = False
    max_auto_stem_tracks: int = Field(default=1, ge=0, le=8)
    stem_separation_timeout_sec: int = Field(default=120, ge=15, le=600)


class DjOfflineMixResult(BaseModel):
    mix_plan: DjMixPlanResult
    output_files: dict[str, str] = Field(default_factory=dict)
    stream_files: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    stem_rule_events: list[dict[str, Any]] = Field(default_factory=list)
    sample_rate: int = 44100
    duration_sec: float = 0.0
