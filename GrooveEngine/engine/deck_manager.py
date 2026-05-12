"""Dual-deck manager for online playback with load balancing.

Deck A and Deck B alternate: while one plays, the other pre-loads the next song.
After each transition the roles swap seamlessly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import soundfile as sf

from core.datatypes import DeckStatus, TrackMetadata, TransitionPlan
from core.enums import DeckState, FXType, TransitionType


class DeckSlot(str, Enum):
    A = "A"
    B = "B"


@dataclass(slots=True)
class LiveDeck:
    """Runtime state for one deck in the online player."""

    slot: DeckSlot
    status: DeckStatus = field(init=False)

    audio: np.ndarray | None = None
    audio_path: str | None = None
    metadata: TrackMetadata | None = None
    sample_rate: int = 44100
    channels: int = 2
    read_frame: int = 0
    playback_rate: float = 1.0

    volume: float = 1.0
    low_eq: float = 1.0
    high_pass: float = 0.0

    def __post_init__(self) -> None:
        self.status = DeckStatus(deck_id=self.slot.value)

    @property
    def loaded(self) -> bool:
        return self.audio is not None

    @property
    def playing(self) -> bool:
        return self.status.state == DeckState.PLAYING

    @property
    def finished(self) -> bool:
        return self.status.state == DeckState.FINISHED

    @property
    def frames_remaining(self) -> int:
        if self.audio is None:
            return 0
        return max(0, len(self.audio) - self.read_frame)

    @property
    def seconds_remaining(self) -> float:
        return self.frames_remaining / float(self.sample_rate) if self.sample_rate > 0 else 0.0

    def load(self, metadata: TrackMetadata, target_bpm: float | None = None) -> None:
        audio, sr = sf.read(metadata.path, always_2d=True, dtype="float32")
        self.audio = audio
        self.sample_rate = int(sr)
        self.channels = audio.shape[1]
        self.read_frame = 0
        self.metadata = metadata
        self.audio_path = metadata.path
        self.playback_rate = 1.0 if not target_bpm else metadata.beatgrid.bpm / max(target_bpm, 1.0)
        self.status.track_path = type(self.status.track_path) if self.status.track_path else None
        self.status.bpm = metadata.beatgrid.bpm
        self.status.state = DeckState.PAUSED
        self.status.playhead_seconds = 0.0
        self.status.playhead_beats = 0.0
        self.volume = 1.0
        self.low_eq = 1.0
        self.high_pass = 0.0

    def play(self) -> None:
        if self.audio is not None:
            self.status.state = DeckState.PLAYING

    def pause(self) -> None:
        if self.status.state == DeckState.PLAYING:
            self.status.state = DeckState.PAUSED

    def stop(self) -> None:
        self.read_frame = 0
        self.status.playhead_seconds = 0.0
        self.status.playhead_beats = 0.0
        self.status.state = DeckState.STOPPED

    def seek_bar(self, bar: int) -> None:
        if self.metadata is None:
            return
        for beat in self.metadata.beatgrid.beats:
            if beat.bar == bar and beat.beat_in_bar == 1:
                self.read_frame = int(beat.time * self.sample_rate)
                self.status.playhead_seconds = beat.time
                return

    def read_frames(self, frames: int) -> np.ndarray:
        if self.audio is None or self.status.state != DeckState.PLAYING:
            return np.zeros((frames, self.channels), dtype=np.float32)

        end = min(self.read_frame + frames, len(self.audio))
        block = self.audio[self.read_frame:end].astype(np.float32, copy=False)
        self.read_frame = end

        if len(block) < frames:
            pad = np.zeros((frames - len(block), self.channels), dtype=np.float32)
            block = np.vstack([block, pad])
            self.status.state = DeckState.FINISHED

        self.status.playhead_seconds = self.read_frame / float(self.sample_rate)
        if self.status.bpm:
            self.status.playhead_beats = self.status.playhead_seconds * (self.status.bpm / 60.0)

        return block


@dataclass(slots=True)
class DeckManager:
    """Orchestrates A/B deck switching for seamless continuous playback."""

    sample_rate: int = 44100
    block_size: int = 1024

    deck_a: LiveDeck = field(default_factory=lambda: LiveDeck(slot=DeckSlot.A))
    deck_b: LiveDeck = field(default_factory=lambda: LiveDeck(slot=DeckSlot.B))
    _active: DeckSlot = DeckSlot.A
    _idle: DeckSlot = DeckSlot.B

    @property
    def active_deck(self) -> LiveDeck:
        return self.deck_a if self._active == DeckSlot.A else self.deck_b

    @property
    def idle_deck(self) -> LiveDeck:
        return self.deck_a if self._idle == DeckSlot.A else self.deck_b

    def swap(self) -> None:
        """Swap active/idle roles after a transition completes."""
        self._active, self._idle = self._idle, self._active

    def load_idle(self, metadata: TrackMetadata, target_bpm: float | None = None) -> None:
        self.idle_deck.load(metadata, target_bpm=target_bpm)

    def both_loaded(self) -> bool:
        return self.deck_a.loaded and self.deck_b.loaded

    def play_both(self) -> None:
        if self.deck_a.loaded:
            self.deck_a.play()
        if self.deck_b.loaded:
            self.deck_b.play()

    def pause_both(self) -> None:
        self.deck_a.pause()
        self.deck_b.pause()

    def stop_all(self) -> None:
        self.deck_a.stop()
        self.deck_b.stop()

    def read_frames(self, frames: int) -> tuple[np.ndarray, np.ndarray]:
        """Read one block from each deck simultaneously."""
        return self.deck_a.read_frames(frames), self.deck_b.read_frames(frames)
