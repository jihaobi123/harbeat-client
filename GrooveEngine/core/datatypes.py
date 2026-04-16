"""Core shared data structures for GrooveEngine."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.enums import DeckState, FXType, PhraseType, TransitionType


class BeatPoint(BaseModel):
    """Represents a beat in absolute and musical coordinates."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    time: float = Field(ge=0.0)
    bar: int = Field(ge=1)
    beat_in_bar: int = Field(ge=1, le=4)
    is_downbeat: bool = False


class BeatGrid(BaseModel):
    """Full beat and bar representation for a track."""

    model_config = ConfigDict(extra="forbid")

    bpm: float = Field(gt=0.0)
    beats: list[BeatPoint]
    bars: int = Field(ge=1)
    downbeats: list[float]


class RawBeatSequence(BaseModel):
    """Backend-native beat extraction result before bar-phase correction."""

    model_config = ConfigDict(extra="forbid")

    bpm: float = Field(gt=0.0)
    beat_times: list[float] = Field(default_factory=list)
    source: str = "librosa"
    confidence_hint: float = Field(default=0.5, ge=0.0, le=1.0)
    frame_hop_length: int | None = Field(default=None, gt=0)
    fallback_used: bool = False


class PhaseCorrectionResult(BaseModel):
    """Result of selecting the most likely bar-phase offset."""

    model_config = ConfigDict(extra="forbid")

    selected_offset: int = Field(ge=0, le=3)
    offset_scores: list[float] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    ambiguous: bool = False

    low_band_scores: list[float] = Field(default_factory=list)
    onset_scores: list[float] = Field(default_factory=list)
    regularity_scores: list[float] = Field(default_factory=list)

    notes: list[str] = Field(default_factory=list)


class BeatAnalysis(BaseModel):
    """Confidence and diagnostics for beat/downbeat/bar-phase extraction."""

    model_config = ConfigDict(extra="forbid")

    beat_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    downbeat_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    bar_phase_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    sub_beat_confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    source: str = "librosa"
    fallback_used: bool = False

    estimated_phase_offset: int = Field(default=0, ge=0, le=3)
    beat_count: int = Field(default=0, ge=0)

    local_tempo_stability: float = Field(default=0.5, ge=0.0, le=1.0)
    downbeat_regularness: float = Field(default=0.5, ge=0.0, le=1.0)
    onset_alignment_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    low_band_alignment_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    local_window_stability_min: float = Field(default=0.5, ge=0.0, le=1.0)
    local_window_stability_mean: float = Field(default=0.5, ge=0.0, le=1.0)
    unstable_segments_detected: int = Field(default=0, ge=0)

    phase_drift_risk: float = Field(default=0.5, ge=0.0, le=1.0)
    long_blend_stability: float = Field(default=0.5, ge=0.0, le=1.0)
    estimated_phase_error_beats: float = Field(default=0.0, ge=0.0)
    recommended_max_overlap_beats: int = Field(default=8, ge=1)

    beat_usable: bool = False
    phrase_sync_usable: bool = False
    long_blend_usable: bool = False
    drift_prone: bool = False

    usable_for_long_blend: bool = False
    usable_for_phrase_sync: bool = False
    ambiguous_bar_phase: bool = False

    warnings: list[str] = Field(default_factory=list)
    sync_warnings: list[str] = Field(default_factory=list)


class EnergyPoint(BaseModel):
    """Energy information quantized to a bar."""

    model_config = ConfigDict(extra="forbid")

    bar: int = Field(ge=1)
    start_time: float = Field(ge=0.0)
    end_time: float = Field(ge=0.0)
    rms: float = Field(ge=0.0)
    spectral_flux: float = Field(ge=0.0)
    combined: float = Field(ge=0.0)


class BandDescriptor(BaseModel):
    """Simplified band-energy summary for a bar."""

    model_config = ConfigDict(extra="forbid")

    bar: int = Field(ge=1)
    sub: float = Field(default=0.0, ge=0.0)
    bass: float = Field(default=0.0, ge=0.0)
    low_mid: float = Field(default=0.0, ge=0.0)
    mid: float = Field(default=0.0, ge=0.0)
    high: float = Field(default=0.0, ge=0.0)
    vocal_presence: float = Field(default=0.0, ge=0.0, le=1.0)
    transient_density: float = Field(default=0.0, ge=0.0)


class LoudnessPoint(BaseModel):
    """Short-term loudness proxy per bar."""

    model_config = ConfigDict(extra="forbid")

    bar: int = Field(ge=1)
    rms_db: float = 0.0
    peak_db: float = 0.0
    short_loudness: float = Field(default=0.0, ge=0.0, le=1.0)


class StereoPoint(BaseModel):
    """Stereo image summary for a bar."""

    model_config = ConfigDict(extra="forbid")

    bar: int = Field(ge=1)
    width: float = Field(default=0.0, ge=0.0, le=1.0)
    balance: float = Field(default=0.0, ge=-1.0, le=1.0)


class DanceabilityPoint(BaseModel):
    """Dancer-followability summary per bar."""

    model_config = ConfigDict(extra="forbid")

    bar: int = Field(ge=1)
    eight_count_clarity: float = Field(default=0.5, ge=0.0, le=1.0)
    downbeat_clarity: float = Field(default=0.5, ge=0.0, le=1.0)
    groove_stability: float = Field(default=0.5, ge=0.0, le=1.0)
    followability: float = Field(default=0.5, ge=0.0, le=1.0)
    two_bar_stability: float = Field(default=0.5, ge=0.0, le=1.0)
    pulse_clarity: float = Field(default=0.5, ge=0.0, le=1.0)
    transition_safe: bool = False


class PhraseSegment(BaseModel):
    """A phrase segment aligned to bar boundaries with DJ mixing semantics."""

    model_config = ConfigDict(extra="forbid")

    phrase_type: PhraseType
    start_time: float = Field(ge=0.0)
    end_time: float = Field(ge=0.0)
    start_bar: int = Field(ge=1)
    end_bar: int = Field(ge=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    mix_role: Literal[
        "safe_intro",
        "groove_entry",
        "energy_lift",
        "peak_release",
        "reset_zone",
        "outro_release",
        "neutral",
    ] = "neutral"
    boundary_strength_in: float = Field(default=0.5, ge=0.0, le=1.0)
    boundary_strength_out: float = Field(default=0.5, ge=0.0, le=1.0)
    mix_in_score: float = Field(default=0.5, ge=0.0, le=1.0)
    mix_out_score: float = Field(default=0.5, ge=0.0, le=1.0)
    reset_score: float = Field(default=0.0, ge=0.0, le=1.0)
    sustain_score: float = Field(default=0.5, ge=0.0, le=1.0)


class PhraseAnchor(BaseModel):
    """DJ-usable phrase entry or release anchor."""

    model_config = ConfigDict(extra="forbid")

    bar: int = Field(ge=1)
    beat: int = Field(default=1, ge=1, le=4)
    anchor_type: Literal["phrase_start", "phrase_end", "eight_count_start", "downbeat", "reset_point"]
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    phrase_type: PhraseType = PhraseType.UNKNOWN
    mix_role: str = "neutral"
    entry_score: float = Field(default=0.5, ge=0.0, le=1.0)
    exit_score: float = Field(default=0.5, ge=0.0, le=1.0)
    boundary_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class MusicalKey(BaseModel):
    """Harmonic metadata."""

    model_config = ConfigDict(extra="forbid")

    tonic: str = "Unknown"
    mode: Literal["major", "minor", "unknown"] = "unknown"
    camelot: str | None = None


class TrackMetadata(BaseModel):
    """Canonical analyzer output persisted to JSON."""

    model_config = ConfigDict(extra="forbid")

    track_id: str
    title: str
    artist: str | None = None
    path: str
    duration_seconds: float = Field(gt=0.0)
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)
    beatgrid: BeatGrid
    beat_analysis: BeatAnalysis = Field(default_factory=BeatAnalysis)
    phrases: list[PhraseSegment]
    phrase_anchors: list[PhraseAnchor] = Field(default_factory=list)
    energy_bars: list[EnergyPoint]
    band_descriptors: list[BandDescriptor] = Field(default_factory=list)
    loudness_profile: list[LoudnessPoint] = Field(default_factory=list)
    stereo_profile: list[StereoPoint] = Field(default_factory=list)
    danceability_profile: list[DanceabilityPoint] = Field(default_factory=list)
    key: MusicalKey = Field(default_factory=MusicalKey)
    analyzer_versions: dict[str, str] = Field(default_factory=dict)

    def bar_count(self) -> int:
        """Return the total number of bars in the track."""

        return self.beatgrid.bars

    def phrase_at_bar(self, bar: int) -> PhraseSegment | None:
        """Return the phrase containing the requested bar."""

        for phrase in self.phrases:
            if phrase.start_bar <= bar <= phrase.end_bar:
                return phrase
        return None

    def energy_at_bar(self, bar: int) -> EnergyPoint | None:
        """Return the energy point for a bar."""

        for energy in self.energy_bars:
            if energy.bar == bar:
                return energy
        return None

    def band_at_bar(self, bar: int) -> BandDescriptor | None:
        """Return the band descriptor for a bar."""

        for descriptor in self.band_descriptors:
            if descriptor.bar == bar:
                return descriptor
        return None

    def loudness_at_bar(self, bar: int) -> LoudnessPoint | None:
        """Return loudness summary for a bar."""

        for point in self.loudness_profile:
            if point.bar == bar:
                return point
        return None

    def danceability_at_bar(self, bar: int) -> DanceabilityPoint | None:
        """Return danceability summary for a bar."""

        for point in self.danceability_profile:
            if point.bar == bar:
                return point
        return None


class SyncAlignmentResult(BaseModel):
    """Normalized offline dual-deck sync alignment diagnostics."""

    model_config = ConfigDict(extra="forbid")

    anchor_bar_a: int = Field(ge=1)
    anchor_bar_b: int = Field(ge=1)
    anchor_time_a: float = Field(ge=0.0)
    anchor_time_b: float = Field(ge=0.0)
    timeline_anchor_time_a: float = Field(ge=0.0)
    timeline_anchor_time_b: float = Field(ge=0.0)
    requested_phase_offset_beats: float = 0.0
    effective_phase_offset_beats: float = 0.0
    anchor_delta_beats: float = 0.0
    estimated_phase_error_beats: float = Field(default=0.0, ge=0.0)
    drift_risk: float = Field(default=0.5, ge=0.0, le=1.0)
    long_overlap_safe: bool = False
    recommended_max_overlap_beats: int | None = Field(default=None, ge=1)
    notes: list[str] = Field(default_factory=list)

    applied_phase_offset_beats: float = 0.0
    estimated_drift_risk: float = Field(default=0.5, ge=0.0, le=1.0)
    long_blend_safe: bool = False


class AutomationPoint(BaseModel):
    """Single automation value at a given timeline beat."""

    model_config = ConfigDict(extra="forbid")

    beat_offset: float
    fx_type: FXType
    value: float
    deck: Literal["A", "B", "master"]


class AutomationLane(BaseModel):
    """Named list of automation points for a strategy."""

    model_config = ConfigDict(extra="forbid")

    name: str
    points: list[AutomationPoint]


class TransitionWindowScore(BaseModel):
    """Scored transition candidate between two search windows."""

    model_config = ConfigDict(extra="forbid")

    track_a_exit_bar: int = Field(ge=1)
    track_b_entry_bar: int = Field(ge=1)
    overlap_beats: int = Field(ge=1)
    target_bpm: float = Field(gt=0.0)
    phase_offset_beats: float = 0.0
    phase_error_beats: float = Field(default=0.0, ge=0.0)
    alignment_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    handoff_profile: str = "smooth_blend"
    phrase_score: float = Field(ge=0.0, le=1.0)
    energy_score: float = Field(ge=0.0, le=1.0)
    harmonic_score: float = Field(ge=0.0, le=1.0)
    strategy_bias_score: float = Field(default=0.5, ge=0.0, le=1.0)
    phase_alignment_score: float = Field(default=0.5, ge=0.0, le=1.0)
    spectral_conflict_score: float = Field(default=0.5, ge=0.0, le=1.0)
    loudness_continuity_score: float = Field(default=0.5, ge=0.0, le=1.0)
    dance_continuity_score: float = Field(default=0.5, ge=0.0, le=1.0)
    sync_drift_risk: float = Field(default=0.5, ge=0.0, le=1.0)
    recommended_max_overlap_beats: int | None = Field(default=None, ge=1)
    total_score: float = Field(ge=0.0, le=1.0)
    strategy: TransitionType
    search_rank: int | None = None
    notes: list[str] = Field(default_factory=list)


class TransitionPlan(BaseModel):
    """Mixer-ready transition decision returned by the planner."""

    model_config = ConfigDict(extra="forbid")

    mix_start_time: float = Field(ge=0.0)
    overlap_duration_beats: float = Field(gt=0.0)
    target_bpm: float = Field(gt=0.0)
    phase_offset_beats: float = 0.0
    alignment_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    handoff_profile: str = "smooth_blend"
    strategy: TransitionType
    track_a_exit_bar: int = Field(ge=1)
    track_b_entry_bar: int = Field(ge=1)
    automation: list[AutomationLane]
    score_breakdown: TransitionWindowScore


class PlaylistTransition(BaseModel):
    """Transition chosen between adjacent playlist tracks."""

    model_config = ConfigDict(extra="forbid")

    track_a_id: str
    track_b_id: str
    plan: TransitionPlan


class PlaylistPlan(BaseModel):
    """End-to-end ordering and transition plan for a playlist."""

    model_config = ConfigDict(extra="forbid")

    ordered_track_ids: list[str]
    ordered_titles: list[str]
    transitions: list[PlaylistTransition]
    average_score: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class DeckStatus:
    """Runtime state snapshot for a deck."""

    deck_id: str
    state: DeckState = DeckState.STOPPED
    track_path: Path | None = None
    track_title: str | None = None
    track_artist: str | None = None
    bpm: float | None = None
    master_sync: bool = False
    gain: float = 1.0
    low_eq: float = 1.0
    high_pass: float = 0.0
    active_fx: list[FXType] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
