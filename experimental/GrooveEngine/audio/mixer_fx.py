"""Pedalboard-based FX chains and automation evaluation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
from pedalboard import Delay, HighpassFilter, LowShelfFilter, Pedalboard, Reverb

from core.datatypes import AutomationLane, AutomationPoint
from core.enums import FXType


@dataclass(slots=True)
class AutomationState:
    """Current automation values by deck and parameter."""

    values: dict[str, dict[FXType, float]] = field(default_factory=lambda: defaultdict(dict))


class MixerFX:
    """Evaluates automation points and applies FX chains to audio blocks."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = sample_rate
        self.automation_state = AutomationState()
        self.deck_boards = {
            "A": Pedalboard([LowShelfFilter(cutoff_frequency_hz=180.0, gain_db=0.0), HighpassFilter(cutoff_frequency_hz=20.0), Delay(delay_seconds=0.25, feedback=0.2, mix=0.0), Reverb(room_size=0.2, wet_level=0.0)]),
            "B": Pedalboard([LowShelfFilter(cutoff_frequency_hz=180.0, gain_db=0.0), HighpassFilter(cutoff_frequency_hz=20.0), Delay(delay_seconds=0.25, feedback=0.2, mix=0.0), Reverb(room_size=0.2, wet_level=0.0)]),
        }

    def apply_automation(self, lanes: list[AutomationLane], beat_position: float) -> None:
        """Update the current automation state based on playhead beat position."""

        for lane in lanes:
            for point in sorted(lane.points, key=lambda item: item.beat_offset):
                if beat_position >= point.beat_offset:
                    self.automation_state.values[point.deck][point.fx_type] = point.value

    def process_deck(self, deck_id: str, audio: np.ndarray) -> np.ndarray:
        """Apply current deck automation to an audio block."""

        if audio.size == 0:
            return audio

        state = self.automation_state.values.get(deck_id, {})
        gain = float(state.get(FXType.VOLUME, 1.0))
        low_eq = float(state.get(FXType.LOW_EQ, 1.0))
        high_pass = float(state.get(FXType.HIGH_PASS, 0.0))
        delay_mix = float(state.get(FXType.DELAY_MIX, 0.0))
        delay_feedback = float(state.get(FXType.DELAY_FEEDBACK, 0.2))
        reverb_mix = float(state.get(FXType.REVERB_MIX, 0.0))

        board = self.deck_boards[deck_id]
        low_shelf = board[0]
        high_pass_filter = board[1]
        delay = board[2]
        reverb = board[3]

        low_shelf.gain_db = (low_eq - 1.0) * 18.0
        high_pass_filter.cutoff_frequency_hz = 20.0 + (high_pass * 4000.0)
        delay.mix = delay_mix
        delay.feedback = delay_feedback
        reverb.wet_level = reverb_mix

        processed = board(audio.T, self.sample_rate).T
        return (processed * gain).astype(np.float32, copy=False)

    def mix(self, deck_a: np.ndarray, deck_b: np.ndarray, master_noise_level: float = 0.0) -> np.ndarray:
        """Combine deck outputs and optional riser noise layer."""

        output = deck_a + deck_b
        if master_noise_level > 0.0:
            noise = np.random.normal(0.0, 0.025 * master_noise_level, size=output.shape).astype(np.float32)
            output = output + noise
        return np.clip(output, -1.0, 1.0)

    def master_noise_level(self) -> float:
        """Return current master noise automation value."""

        return float(self.automation_state.values.get("master", {}).get(FXType.NOISE_LEVEL, 0.0))
