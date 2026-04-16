"""Deck abstraction for buffered audio playback and tempo adjustment."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from core.datatypes import DeckStatus, TrackMetadata
from core.enums import DeckState


@dataclass(slots=True)
class AudioDeck:
    """Single deck playback state with block-based reads."""

    deck_id: str
    status: DeckStatus = field(init=False)
    audio: np.ndarray | None = field(default=None, init=False)
    sample_rate: int = field(default=44100, init=False)
    channels: int = field(default=2, init=False)
    read_index: int = field(default=0, init=False)
    playback_rate: float = field(default=1.0, init=False)

    def __post_init__(self) -> None:
        self.status = DeckStatus(deck_id=self.deck_id)

    def load(self, metadata: TrackMetadata, target_bpm: float | None = None) -> None:
        """Load audio data for playback and prepare tempo adjustment."""

        audio, sample_rate = sf.read(metadata.path, always_2d=True, dtype="float32")
        self.audio = audio
        self.sample_rate = sample_rate
        self.channels = audio.shape[1]
        self.read_index = 0
        self.playback_rate = 1.0 if not target_bpm else metadata.beatgrid.bpm / target_bpm
        self.status.track_path = Path(metadata.path)
        self.status.bpm = metadata.beatgrid.bpm
        self.status.state = DeckState.PAUSED
        self.status.playhead_seconds = 0.0
        self.status.playhead_beats = 0.0

    def play(self) -> None:
        """Start playback."""

        if self.audio is not None:
            self.status.state = DeckState.PLAYING

    def pause(self) -> None:
        """Pause playback."""

        if self.status.state == DeckState.PLAYING:
            self.status.state = DeckState.PAUSED

    def stop(self) -> None:
        """Stop playback and reset playhead."""

        self.read_index = 0
        self.status.playhead_seconds = 0.0
        self.status.playhead_beats = 0.0
        self.status.state = DeckState.STOPPED

    def read_frames(self, frames: int) -> np.ndarray:
        """Return the next block of audio frames.

        The implementation is intentionally simple and replaceable. For tempo changes,
        a stretch step is applied to the outgoing block rather than mutating source data.
        """

        if self.audio is None or self.status.state != DeckState.PLAYING:
            return np.zeros((frames, self.channels), dtype=np.float32)

        end_index = min(self.read_index + frames, len(self.audio))
        block = self.audio[self.read_index:end_index]
        self.read_index = end_index

        if len(block) < frames:
            pad = np.zeros((frames - len(block), self.channels), dtype=np.float32)
            block = np.vstack([block, pad])
            self.status.state = DeckState.FINISHED

        if abs(self.playback_rate - 1.0) > 0.01:
            block = self._time_stretch_block(block, self.playback_rate)
            if len(block) < frames:
                block = np.vstack([block, np.zeros((frames - len(block), self.channels), dtype=np.float32)])
            block = block[:frames]

        self.status.playhead_seconds = self.read_index / float(self.sample_rate)
        beats_per_second = self.status.bpm / 60.0 if self.status.bpm else 0.0
        self.status.playhead_beats = self.status.playhead_seconds * beats_per_second
        return block.astype(np.float32, copy=False)

    def _time_stretch_block(self, block: np.ndarray, rate: float) -> np.ndarray:
        """Apply a lightweight per-block time stretch using librosa."""

        if self.channels == 1:
            stretched = librosa.effects.time_stretch(block[:, 0], rate=rate)
            return stretched[:, np.newaxis].astype(np.float32)
        channels: list[np.ndarray] = []
        for channel in range(self.channels):
            stretched = librosa.effects.time_stretch(block[:, channel], rate=rate)
            channels.append(stretched.astype(np.float32))
        min_len = min(len(channel) for channel in channels)
        return np.stack([channel[:min_len] for channel in channels], axis=1)
