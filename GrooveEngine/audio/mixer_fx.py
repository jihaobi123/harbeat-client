"""Pedalboard-based FX chains and automation evaluation."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

try:
    from pedalboard import Delay, HighpassFilter, LowShelfFilter, Pedalboard, Reverb
    PEDALBOARD_AVAILABLE = True
except ImportError:
    PEDALBOARD_AVAILABLE = False

    class LowShelfFilter:
        def __init__(self, cutoff_frequency_hz: float, gain_db: float = 0.0) -> None:
            self.cutoff_frequency_hz = cutoff_frequency_hz
            self.gain_db = gain_db

    class HighpassFilter:
        def __init__(self, cutoff_frequency_hz: float) -> None:
            self.cutoff_frequency_hz = cutoff_frequency_hz

    class Delay:
        def __init__(self, delay_seconds: float, feedback: float = 0.2, mix: float = 0.0) -> None:
            self.delay_seconds = delay_seconds
            self.feedback = feedback
            self.mix = mix

    class Reverb:
        def __init__(self, room_size: float = 0.2, wet_level: float = 0.0) -> None:
            self.room_size = room_size
            self.wet_level = wet_level

    class Pedalboard(list):
        def __call__(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
            del sample_rate
            return _apply_fallback_effects(audio, self)


from core.datatypes import AutomationLane
from core.enums import FXType


def _apply_fallback_effects(audio: np.ndarray, board: list[object]) -> np.ndarray:
    """Apply a lightweight numpy fallback when pedalboard is unavailable."""

    processed = np.array(audio, dtype=np.float32, copy=True)
    if processed.size == 0:
        return processed

    low_shelf = next((item for item in board if isinstance(item, LowShelfFilter)), None)
    high_pass_filter = next((item for item in board if isinstance(item, HighpassFilter)), None)
    delay = next((item for item in board if isinstance(item, Delay)), None)
    reverb = next((item for item in board if isinstance(item, Reverb)), None)

    if low_shelf is not None and abs(low_shelf.gain_db) > 1e-3:
        low_eq = float(np.clip(10.0 ** (low_shelf.gain_db / 20.0), 0.1, 4.0))
        spectrum = np.fft.rfft(processed, axis=0)
        freqs = np.fft.rfftfreq(len(processed), d=1.0 / 44100.0)
        spectrum[freqs < low_shelf.cutoff_frequency_hz] *= low_eq
        processed = np.fft.irfft(spectrum, n=len(processed), axis=0).astype(np.float32, copy=False)

    if high_pass_filter is not None and high_pass_filter.cutoff_frequency_hz > 25.0:
        alpha = float(np.clip(high_pass_filter.cutoff_frequency_hz / 5000.0, 0.0, 0.98))
        filtered = np.zeros_like(processed)
        filtered[0] = processed[0]
        for idx in range(1, len(processed)):
            filtered[idx] = alpha * (filtered[idx - 1] + processed[idx] - processed[idx - 1])
        processed = filtered

    if delay is not None and delay.mix > 0.0:
        delay_samples = max(1, int(delay.delay_seconds * 44100))
        delayed = np.zeros_like(processed)
        if delay_samples < len(processed):
            delayed[delay_samples:] = processed[:-delay_samples] * float(np.clip(delay.feedback, 0.0, 0.95))
        processed = (processed * (1.0 - delay.mix) + delayed * delay.mix).astype(np.float32, copy=False)

    if reverb is not None and reverb.wet_level > 0.0:
        taps = [0.015, 0.029, 0.043]
        wet = np.zeros_like(processed)
        for tap in taps:
            samples = int(tap * 44100)
            if 0 < samples < len(processed):
                wet[samples:] += processed[:-samples] * 0.18
        processed = (processed * (1.0 - reverb.wet_level) + wet * reverb.wet_level).astype(np.float32, copy=False)

    return np.clip(processed, -1.0, 1.0).astype(np.float32, copy=False)


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
        mid_eq = float(state.get(FXType.MID_EQ, 1.0))
        high_eq = float(state.get(FXType.HIGH_EQ, 1.0))
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

        processed = board(audio.T, self.sample_rate).T.astype(np.float32, copy=False)
        processed = self._apply_band_eq(processed, low_eq=low_eq, mid_eq=mid_eq, high_eq=high_eq)
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

    def _apply_band_eq(self, audio: np.ndarray, low_eq: float, mid_eq: float, high_eq: float) -> np.ndarray:
        """Apply lightweight three-band spectral shaping per block."""

        if audio.size == 0:
            return audio
        if abs(low_eq - 1.0) < 1e-3 and abs(mid_eq - 1.0) < 1e-3 and abs(high_eq - 1.0) < 1e-3:
            return audio

        spectrum = np.fft.rfft(audio, axis=0)
        freqs = np.fft.rfftfreq(len(audio), d=1.0 / self.sample_rate)
        gains = np.ones_like(freqs, dtype=np.float32)
        gains[freqs < 220.0] *= low_eq
        gains[(freqs >= 220.0) & (freqs < 2800.0)] *= mid_eq
        gains[freqs >= 2800.0] *= high_eq
        shaped = np.fft.irfft(spectrum * gains[:, np.newaxis], n=len(audio), axis=0)
        return np.clip(shaped, -1.0, 1.0).astype(np.float32, copy=False)
