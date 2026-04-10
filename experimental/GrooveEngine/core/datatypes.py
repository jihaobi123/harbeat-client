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


class EnergyPoint(BaseModel):
    """Energy information quantized to a bar."""

    model_config = ConfigDict(extra="forbid")

    bar: int = Field(ge=1)
    start_time: float = Field(ge=0.0)
    end_time: float = Field(ge=0.0)
    rms: float = Field(ge=0.0)
    spectral_flux: float = Field(ge=0.0)
    combined: float = Field(ge=0.0)


class PhraseSegment(BaseModel):
    """A phrase segment aligned to bar boundaries."""

    model_config = ConfigDict(extra="forbid")

    phrase_type: PhraseType
    start_time: float = Field(ge=0.0)
    end_time: float = Field(ge=0.0)
    start_bar: int = Field(ge=1)
    end_bar: int = Field(ge=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class BeatGrid(BaseModel):
    """Full beat and bar representation for a track."""

    model_config = ConfigDict(extra="forbid")

    bpm: float = Field(gt=0.0)
    beats: list[BeatPoint]
    bars: int = Field(ge=1)
    downbeats: list[float]


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
    phrases: list[PhraseSegment]
    energy_bars: list[EnergyPoint]
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
    """Scored transition candidate between two windows."""

    model_config = ConfigDict(extra="forbid")

    track_a_exit_bar: int = Field(ge=1)
    track_b_entry_bar: int = Field(ge=1)
    overlap_beats: int = Field(ge=1)
    phrase_score: float = Field(ge=0.0, le=1.0)
    energy_score: float = Field(ge=0.0, le=1.0)
    harmonic_score: float = Field(ge=0.0, le=1.0)
    total_score: float = Field(ge=0.0, le=1.0)
    strategy: TransitionType
    notes: list[str] = Field(default_factory=list)


class TransitionPlan(BaseModel):
    """Mixer-ready transition decision returned by the planner."""

    model_config = ConfigDict(extra="forbid")

    mix_start_time: float = Field(ge=0.0)
    overlap_duration_beats: int = Field(ge=1)
    target_bpm: float = Field(gt=0.0)
    strategy: TransitionType
    track_a_exit_bar: int = Field(ge=1)
    track_b_entry_bar: int = Field(ge=1)
    automation: list[AutomationLane] = Field(default_factory=list)
    score_breakdown: TransitionWindowScore


class PlaylistTransition(BaseModel):
    """Resolved transition between two ordered tracks."""

    model_config = ConfigDict(extra="forbid")

    track_a_id: str
    track_b_id: str
    plan: TransitionPlan


class PlaylistPlan(BaseModel):
    """Ordered multi-track render plan."""

    model_config = ConfigDict(extra="forbid")

    ordered_track_ids: list[str]
    ordered_titles: list[str]
    transitions: list[PlaylistTransition] = Field(default_factory=list)
    average_score: float = Field(ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class MixCommand:
    """Command sent from the main thread to the audio thread."""

    command: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DeckStatus:
    """Runtime state snapshot for a deck."""

    deck_id: str
    state: DeckState = DeckState.STOPPED
    track_path: Path | None = None
    playhead_seconds: float = 0.0
    playhead_beats: float = 0.0
    bpm: float = 0.0
    gain: float = 1.0
