from __future__ import annotations

from typing import Literal, Optional

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
    title: str
    artist: str
    audio_url: Optional[str] = None
    duration: Optional[float] = None
    bpm: Optional[int] = None
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


class StyleMixRequest(BaseModel):
    style: str
    duration_minutes: int = 30
    bpm: Optional[int] = None
    energy: Optional[str] = None
    quality_mode: Literal["balanced", "hq", "fast"] = "balanced"


class StyleMixResult(BaseModel):
    playlist: list[PlaylistSongData] = Field(default_factory=list)
    processed_files: dict[int, str] = Field(default_factory=dict)
    stem_files: dict[int, dict[str, str]] = Field(default_factory=dict)
    meta: dict[int, dict[str, str]] = Field(default_factory=dict)


# ── DJ Auto-Mix schemas (DJ.studio-inspired) ──────────────────────────────

class DJMixRequest(BaseModel):
    """Request for AI-powered DJ set generation via Harmonize algorithm."""
    style: str
    duration_minutes: int = 30
    bpm: Optional[int] = None
    energy: Optional[str] = None
    energy_profile: str = "journey"       # warmup | peak | cooldown | journey | free
    harmonic_weight: str = "balanced"     # bpm_first | key_first | balanced
    overlap_bars: int = 8                 # bars of A/B overlap for transition
    transition_style: str = "smooth"      # smooth | power | bass_swap | echo_out | filter | cut | slam
    quality_mode: Literal["balanced", "hq", "fast"] = "balanced"
    start_song_id: Optional[int] = None


class SegmentInfo(BaseModel):
    """Full-song play range (mix-in/mix-out points)."""
    start_sec: float
    end_sec: float
    bars: int
    label: str = ""


class TransitionData(BaseModel):
    """Transition metadata between two songs (DJ.studio-style)."""
    from_song_id: int
    to_song_id: int
    score: float
    bpm_score: float
    key_score: float
    energy_score: float
    # Full-song play ranges
    a_play_start: float = 0.0
    a_play_end: float = 0.0
    b_play_start: float = 0.0
    b_play_end: float = 0.0
    # Overlap
    overlap_bars: int = 8
    overlap_sec: float = 0.0
    mix_start_time: float = 0.0       # time in A where overlap begins
    mix_duration_sec: float = 0.0
    mix_duration_bars: int = 8
    b_cue_time: float = 0.0
    bpm_shift: float = 1.0
    # Per-stem automation curves (sampled at 10Hz)
    automation: Optional[dict] = None


class DJMixResult(BaseModel):
    """Complete DJ set with ordering + transitions + processed files."""
    playlist: list[PlaylistSongData] = Field(default_factory=list)
    processed_files: dict[int, str] = Field(default_factory=dict)
    stem_files: dict[int, dict[str, str]] = Field(default_factory=dict)
    segments: dict[int, SegmentInfo] = Field(default_factory=dict)
    transitions: list[TransitionData] = Field(default_factory=list)
    energy_profile: str = "journey"
    harmonic_weight: str = "balanced"
    total_duration_sec: float = 0
    avg_score: float = 0
