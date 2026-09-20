"""Shared data models for the pure planning layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Mapping, Optional


class TransitionMethod(str, Enum):
    """High-level transition method selected by the DJ rules."""

    FX_DIRECT_CUT = "fx_direct_cut"
    FX_SOFT_OVERLAP = "fx_soft_overlap"
    MIX_BLEND = "mix_blend"
    STEM_BLEND = "stem_blend"


class TempoRelation(str, Enum):
    """How track B can be tempo-aligned to track A."""

    DIRECT = "direct"
    B_IS_DOUBLE_A = "b_is_double_a"
    B_IS_HALF_A = "b_is_half_a"
    UNMATCHED = "unmatched"


@dataclass(frozen=True)
class DensityProfile:
    """0.0-1.0 density estimates for a song section or cue window."""

    vocal: float = 0.0
    bass: float = 0.0
    melody: float = 0.0

    @property
    def average(self) -> float:
        return (self.vocal + self.bass + self.melody) / 3.0


@dataclass(frozen=True)
class DrumProfile:
    """Compact drum feature representation.

    Hits are normalized positions in a 16-step bar grid.
    """

    sound_tags: frozenset[str] = field(default_factory=frozenset)
    rhythm_hits: tuple[int, ...] = field(default_factory=tuple)
    kick_hits: tuple[int, ...] = field(default_factory=tuple)
    snare_clap_hits: tuple[int, ...] = field(default_factory=tuple)
    hihat_hits: tuple[int, ...] = field(default_factory=tuple)
    bass_hits: tuple[int, ...] = field(default_factory=tuple)
    percussion_hits: tuple[int, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sound_tags",
            frozenset(str(tag).strip().lower() for tag in self.sound_tags if str(tag).strip()),
        )
        for field_name in (
            "rhythm_hits",
            "kick_hits",
            "snare_clap_hits",
            "hihat_hits",
            "bass_hits",
            "percussion_hits",
        ):
            hits = getattr(self, field_name)
            normalized = tuple(sorted({int(hit) % 16 for hit in hits}))
            object.__setattr__(self, field_name, normalized)

    @property
    def all_hits(self) -> tuple[int, ...]:
        merged = set(self.rhythm_hits)
        merged.update(self.kick_hits)
        merged.update(self.snare_clap_hits)
        merged.update(self.hihat_hits)
        merged.update(self.bass_hits)
        merged.update(self.percussion_hits)
        return tuple(sorted(merged))


@dataclass(frozen=True)
class PhraseMarker:
    """Phrase or bar-boundary marker supplied by beatgrid/structure analysis."""

    time_seconds: float
    bar_index: int
    phrase_bars: int = 8
    section_name: str | None = None
    risk_score: float = 0.0
    is_downbeat: bool = True


@dataclass(frozen=True)
class SectionMarker:
    """Song section marker, for example verse, chorus, break, or outro."""

    name: str
    start_time_seconds: float
    end_time_seconds: float
    occurrence: int = 1
    start_bar: int | None = None
    end_bar: int | None = None
    density: DensityProfile = field(default_factory=DensityProfile)

    def contains(self, time_seconds: float) -> bool:
        return self.start_time_seconds <= time_seconds < self.end_time_seconds


@dataclass(frozen=True)
class TrackProfile:
    """Input contract for one analyzed track."""

    id: str
    title: str
    style: str
    bpm: float
    artist: str | None = None
    key: str | None = None
    duration_seconds: float | None = None
    drum_profile: DrumProfile = field(default_factory=DrumProfile)
    phrase_markers: tuple[PhraseMarker, ...] = field(default_factory=tuple)
    sections: tuple[SectionMarker, ...] = field(default_factory=tuple)
    stem_quality: float | None = None

    def __post_init__(self) -> None:
        if self.bpm <= 0:
            raise ValueError("TrackProfile.bpm must be positive")
        if not self.id:
            raise ValueError("TrackProfile.id is required")
        if not self.style:
            raise ValueError("TrackProfile.style is required")
        object.__setattr__(self, "style", self.style.strip())
        object.__setattr__(self, "phrase_markers", tuple(self.phrase_markers))
        object.__setattr__(self, "sections", tuple(self.sections))


@dataclass(frozen=True)
class PairAnalysis:
    """Optional pair-specific overrides from an external analyzer."""

    drum_overlap: float | None = None
    key_compatible: bool | None = None
    stem_quality: float | None = None


@dataclass(frozen=True)
class ScoringWeights:
    drum_overlap: float = 0.45
    bpm_proximity: float = 0.30
    bpm_trend: float = 0.15
    key_compatibility: float = 0.10


@dataclass(frozen=True)
class TransitionConfig:
    """Tunable DJ rule parameters."""

    mini_set_size: int = 6
    preferred_bpm_diff: float = 5.0
    max_direct_bpm_diff: float = 10.0
    max_bpm_shift_for_ratio: float = 5.0
    bpm_score_window: float = 12.0
    descending_bpm_penalty: float = 0.20
    over_preferred_bpm_penalty: float = 0.05
    drum_low_threshold: float = 0.70
    drum_high_threshold: float = 0.85
    stem_quality_threshold: float = 0.75
    restore_bars: int = 16
    restore_curve: str = "linear"
    auto_max_play_seconds: float = 120.0
    preferred_auto_phrase_bars: tuple[int, ...] = (16, 8)
    manual_phrase_bars: tuple[int, ...] = (4, 8, 16)
    manual_max_wait_bars: int = 8
    manual_safe_risk_threshold: float = 0.40
    dense_section_threshold: float = 0.65
    beats_per_bar: int = 4
    weights: ScoringWeights = field(default_factory=ScoringWeights)


@dataclass(frozen=True)
class BpmCompatibility:
    is_mixable: bool
    relation: TempoRelation
    target_b_bpm: float
    effective_bpm_delta: float
    reason: str


@dataclass(frozen=True)
class BpmAlignmentPlan:
    from_bpm: float
    to_original_bpm: float
    to_entry_bpm: float
    playback_rate: float
    tempo_relation: TempoRelation
    should_align_before_entry: bool
    restore_to_original_bpm: bool
    restore_bars: int
    restore_curve: str
    reason: str


@dataclass(frozen=True)
class CuePoint:
    time_seconds: float
    bar_index: int
    phrase_bars: int
    reason: str
    risk_score: float = 0.0


@dataclass(frozen=True)
class CandidateScore:
    total: float
    drum_overlap: float
    bpm_proximity: float
    bpm_trend: float
    key_compatibility: float
    bpm_delta: float
    penalties: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TransitionPlan:
    from_track_id: str
    to_track_id: str
    method: TransitionMethod
    exit_cue: CuePoint
    bpm_plan: BpmAlignmentPlan
    drum_overlap: float
    key_compatible: bool
    reason: str
    candidate_score: CandidateScore | None = None


@dataclass(frozen=True)
class MiniSetPlan:
    style: str
    tracks: tuple[TrackProfile, ...]
    transitions: tuple[TransitionPlan, ...]


PairAnalysisProvider = Callable[[TrackProfile, TrackProfile], Optional[PairAnalysis]]
PairAnalysisLookup = Mapping[tuple[str, str], PairAnalysis]
