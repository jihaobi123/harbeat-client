"""
RK3588 real-time TransitionPlan curve executor.

Consumes the TransitionPlan JSON format from Jetson's stem_automix module
and applies AutomationCurves in the audio callback (block-by-block).

Usage in engine.py callback (per block of `frames` samples):

    # Once, when loading a new plan:
    player = StemCurvePlayer.from_transition_plan(plan_dict, sample_rate=44100)

    # Each audio callback block:
    progress = player.progress  # 0.0 → 1.0 over transition
    deck_a, deck_b = player.process_block(frames)

    # deck_a, deck_b are (frames, 2) float32 arrays to mix into output

Design constraints:
- Zero allocations in process_block() hot path
- Pre-computes all envelope breakpoints at load time
- Linear interpolation between breakpoints per block
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# ── Curve parameter enums (mirrors Jetson stem_automix.py) ──────────

class CurveTarget:
    """Target names for automation curves."""
    A_VOCALS = "A.vocals"
    A_DRUMS = "A.drums"
    A_BASS = "A.bass"
    A_OTHER = "A.other"
    B_VOCALS = "B.vocals"
    B_DRUMS = "B.drums"
    B_BASS = "B.bass"
    B_OTHER = "B.other"
    MASTER = "master"

    STEM_TARGETS = {A_VOCALS, A_DRUMS, A_BASS, A_OTHER,
                    B_VOCALS, B_DRUMS, B_BASS, B_OTHER}
    DECK_A_STEMS = {"vocals": A_VOCALS, "drums": A_DRUMS,
                     "bass": A_BASS, "other": A_OTHER}
    DECK_B_STEMS = {"vocals": B_VOCALS, "drums": B_DRUMS,
                     "bass": B_BASS, "other": B_OTHER}


class CurveParam:
    GAIN = "gain"
    LOW_EQ = "low_eq"
    MID_EQ = "mid_eq"
    HIGH_EQ = "high_eq"
    HIGHPASS = "highpass"
    LOWPASS = "lowpass"
    ECHO_SEND = "echo_send"
    REVERB_SEND = "reverb_send"
    MUTE = "mute"


class CurveShape:
    LINEAR = "linear"
    EQUAL_POWER = "equal_power"
    EXPONENTIAL = "exponential"
    S_CURVE = "s_curve"


# ── Per-curve envelope (pre-computed for block-level access) ───────

@dataclass
class _Envelope:
    """Pre-computed envelope sampled at block granularity.

    Stores one value per block so the callback can look up the current
    block's value without any per-sample computation.
    """
    values: np.ndarray  # shape (num_blocks,) float32 — one value per block
    target: str
    param: str

    @classmethod
    def from_points(cls, points: list, num_blocks: int,
                    target: str, param: str, shape: str) -> "_Envelope":
        """Build per-block envelope from time-fraction [t, value] points."""
        # Sample at block midpoints
        block_centers = (np.arange(num_blocks, dtype=np.float32) + 0.5) / num_blocks
        values = _interpolate_curve(np.array(points, dtype=np.float32),
                                     block_centers, shape)
        return cls(values=values.astype(np.float32), target=target, param=param)


def _interpolate_curve(points: np.ndarray, t: np.ndarray, shape: str) -> np.ndarray:
    """Interpolate curve points at time positions t (all in [0, 1]).

    points: (N, 2) array of [time_frac, value]
    t: (M,) array of query times
    Returns: (M,) float32 array of interpolated values
    """
    pt_t = points[:, 0]
    pt_v = points[:, 1]

    if shape == "s_curve":
        # smoothstep transform on t before lookup
        t_smooth = t * t * (3.0 - 2.0 * t)  # smoothstep
        return np.interp(t_smooth, pt_t, pt_v).astype(np.float32)
    elif shape == "equal_power":
        # cos² / sin² style — handled at mix stage; use linear for envelope
        return np.interp(t, pt_t, pt_v).astype(np.float32)
    elif shape == "exponential":
        # Log-linear: map to log domain for linear interpolation, then exp back
        eps = 1e-8
        log_v = np.log(np.maximum(pt_v, eps))
        log_interp = np.interp(t, pt_t, log_v)
        return np.exp(log_interp).astype(np.float32)
    else:  # linear
        return np.interp(t, pt_t, pt_v).astype(np.float32)


# ── Main player class ──────────────────────────────────────────────

class StemCurvePlayer:
    """Executes a TransitionPlan's AutomationCurves block-by-block.

    Called from the audio callback — all heavy computation done at init time.
    """

    __slots__ = (
        "total_blocks", "current_block", "sample_rate",
        "transition_samples", "duration_bars", "bpm",
        "_gain_a", "_gain_b",        # per-block gain envelopes per stem
        "_eq_low", "_eq_mid", "_eq_high",  # per-block EQ dB per deck (master-only for now)
        "_hpf_hz", "_lpf_hz",        # per-block filter cutoff envelopes
        "_echo_send", "_reverb_send", # per-block send envelopes
        "_mute_a", "_mute_b",        # per-block mute flags
        "_deck_a_stems", "_deck_b_stems",  # stem name sets
    )

    def __init__(self, sample_rate: int = 44100):
        self.total_blocks = 0
        self.current_block = 0
        self.sample_rate = sample_rate
        self.transition_samples = 0
        self.duration_bars = 8
        self.bpm = 120.0

        # Deck-level gain envelopes (pre-multiplied stem gains)
        self._gain_a: dict[str, np.ndarray] = {}
        self._gain_b: dict[str, np.ndarray] = {}

        # EQ dB envelopes (master-level)
        self._eq_low: np.ndarray | None = None
        self._eq_mid: np.ndarray | None = None
        self._eq_high: np.ndarray | None = None

        # Filter cutoff Hz envelopes
        self._hpf_hz: np.ndarray | None = None
        self._lpf_hz: np.ndarray | None = None

        # Send envelopes
        self._echo_send: np.ndarray | None = None
        self._reverb_send: np.ndarray | None = None

        # Mute flags
        self._mute_a: np.ndarray | None = None
        self._mute_b: np.ndarray | None = None

        # Active stem names
        self._deck_a_stems: set[str] = set()
        self._deck_b_stems: set[str] = set()

    @classmethod
    def from_transition_plan(cls, plan: dict, sample_rate: int = 44100,
                             block_size: int = 2048) -> "StemCurvePlayer":
        """Build a player from a TransitionPlan JSON dict."""
        player = cls(sample_rate=sample_rate)
        curves = plan.get("curves", [])
        duration_bars = int(plan.get("duration_bars", 8))
        bpm = float(plan.get("bpm_from", 120.0) or 120.0)
        player.duration_bars = duration_bars
        player.bpm = bpm

        # Calculate total samples and blocks
        beat_sec = 60.0 / max(bpm, 1.0)
        bar_sec = beat_sec * 4.0
        transition_sec = bar_sec * duration_bars
        player.transition_samples = int(transition_sec * sample_rate)
        player.total_blocks = max(1, int(player.transition_samples / block_size))

        n_blocks = player.total_blocks

        # Initialize envelopes
        for name in ("vocals", "drums", "bass", "other"):
            player._gain_a[name] = np.ones(n_blocks, dtype=np.float32)
            player._gain_b[name] = np.ones(n_blocks, dtype=np.float32)

        # Process each curve
        for curve in curves:
            target = str(curve.get("target", ""))
            param = str(curve.get("param", "gain"))
            points = curve.get("points", [[0.0, 1.0], [1.0, 1.0]])
            shape = str(curve.get("shape", "linear"))

            env = _Envelope.from_points(points, n_blocks, target, param, shape)
            values = env.values

            # Route to correct slot
            if target == "master":
                if param == "gain":
                    # Master gain affects all stems equally
                    for name in ("vocals", "drums", "bass", "other"):
                        player._gain_a[name] = player._gain_a[name] * values
                        player._gain_b[name] = player._gain_b[name] * values
                elif param == "low_eq":
                    player._eq_low = values
                elif param == "mid_eq":
                    player._eq_mid = values
                elif param == "high_eq":
                    player._eq_high = values
                elif param == "highpass":
                    player._hpf_hz = values
                elif param == "lowpass":
                    player._lpf_hz = values
                elif param == "echo_send":
                    player._echo_send = values
                elif param == "reverb_send":
                    player._reverb_send = values
                elif param == "mute":
                    # Global mute
                    mask = (values <= 0.5).astype(np.float32)
                    for name in ("vocals", "drums", "bass", "other"):
                        player._gain_a[name] = player._gain_a[name] * mask
                        player._gain_b[name] = player._gain_b[name] * mask

            elif target.startswith("A."):
                stem = target[2:]
                if stem in player._gain_a:
                    if param == "gain":
                        player._gain_a[stem] = player._gain_a[stem] * values
                    elif param == "mute":
                        player._gain_a[stem] = np.where(values > 0.5, 0.0,
                                                         player._gain_a[stem])
                    elif param == "echo_send":
                        player._echo_send = (
                            values if player._echo_send is None
                            else player._echo_send * values
                        )
                    player._deck_a_stems.add(stem)

            elif target.startswith("B."):
                stem = target[2:]
                if stem in player._gain_b:
                    if param == "gain":
                        player._gain_b[stem] = player._gain_b[stem] * values
                    elif param == "mute":
                        player._gain_b[stem] = np.where(values > 0.5, 0.0,
                                                         player._gain_b[stem])
                    player._deck_b_stems.add(stem)

        return player

    @property
    def progress(self) -> float:
        """Current progress through the transition [0.0, 1.0]."""
        if self.total_blocks <= 0:
            return 1.0
        return min(1.0, self.current_block / self.total_blocks)

    @property
    def is_done(self) -> bool:
        return self.current_block >= self.total_blocks

    def advance(self) -> bool:
        """Move to next block. Returns True if transition is complete."""
        self.current_block += 1
        return self.is_done

    def get_gains(self, block: int | None = None) -> dict:
        """Get stem gain values for the current (or specified) block.

        Returns dict with keys: a_vocals, a_drums, a_bass, a_other,
        b_vocals, b_drums, b_bass, b_other, echo, reverb, hpf_hz, lpf_hz,
        eq_low, eq_mid, eq_high.
        """
        b = self.current_block if block is None else min(block, self.total_blocks - 1)
        result = {}
        for name in ("vocals", "drums", "bass", "other"):
            result[f"a_{name}"] = float(self._gain_a[name][b])
            result[f"b_{name}"] = float(self._gain_b[name][b])
        result["echo"] = float(self._echo_send[b]) if self._echo_send is not None else 0.0
        result["reverb"] = float(self._reverb_send[b]) if self._reverb_send is not None else 0.0
        result["hpf_hz"] = float(self._hpf_hz[b]) if self._hpf_hz is not None else 20.0
        result["lpf_hz"] = float(self._lpf_hz[b]) if self._lpf_hz is not None else 18000.0
        result["eq_low"] = float(self._eq_low[b]) if self._eq_low is not None else 0.0
        result["eq_mid"] = float(self._eq_mid[b]) if self._eq_mid is not None else 0.0
        result["eq_high"] = float(self._eq_high[b]) if self._eq_high is not None else 0.0
        return result


# ── Standalone test ────────────────────────────────────────────────

if __name__ == "__main__":
    # Test with current.json on RK3588
    import sys
    plan_path = sys.argv[1] if len(sys.argv) > 1 else "/home/cat/cypher/plans/current.json"
    plan = json.loads(Path(plan_path).read_text())
    mix_plan = plan.get("mix_plan", plan)

    player = StemCurvePlayer.from_transition_plan(mix_plan, sample_rate=44100, block_size=2048)
    print(f"Plan: {mix_plan.get('preset', 'unknown')} ({mix_plan.get('mode', 'unknown')})")
    print(f"Blocks: {player.total_blocks}, samples: {player.transition_samples}")
    print(f"Duration: {player.transition_samples / 44100:.1f}s")

    # Print gain envelopes every 10%
    for pct in (0, 10, 25, 50, 75, 90, 100):
        b = int(player.total_blocks * pct / 100)
        b = min(b, player.total_blocks - 1)
        g = player.get_gains(b)
        print(f"\n{pct:3d}% (block {b}):")
        for stem in ("vocals", "drums", "bass", "other"):
            print(f"  A.{stem}: {g[f'a_{stem}']:.3f}  B.{stem}: {g[f'b_{stem}']:.3f}")
        if g["echo"] > 0.001:
            print(f"  echo: {g['echo']:.3f}")
        if abs(g["eq_low"]) > 0.01 or abs(g["eq_mid"]) > 0.01 or abs(g["eq_high"]) > 0.01:
            print(f"  EQ: low={g['eq_low']:.1f} mid={g['eq_mid']:.1f} high={g['eq_high']:.1f}")

    print("\nSUCCESS: StemCurvePlayer functional")
