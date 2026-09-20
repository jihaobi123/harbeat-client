"""Stem-aware Automix: transition plan data structures, curve engine, and presets.

Architecture:
  1. TransitionPlan is the universal output format consumed by RK3588.
  2. Presets generate lists of AutomationCurve grouped by target/param.
  3. The scoring system evaluates each preset for a track pair.
  4. Decision rules pick the best preset based on scores.
  5. Non-stem fallbacks always exist — stem_aware is a superset.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

import numpy as np


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Enums & Constants
# ═══════════════════════════════════════════════════════════════════════════════

class TransitionMode(str, Enum):
    non_stem = "non_stem"
    stem_aware = "stem_aware"


class TransitionPreset(str, Enum):
    # ── djay Basic ──
    fade = "fade"                         # → Fade (simple A↓ B↑)
    filter_sweep = "filter_sweep"         # → Filter (HPF/LPF sweep)
    eq_bass_swap = "eq_bass_swap"         # → EQ (bass swap focus)
    echo_freeze = "echo_freeze"           # → Echo (echo-out A, B enters)
    # ── djay Creative ──
    dissolve = "dissolve"                 # → Dissolve (granular/gating fragments)
    melt = "melt"                         # → Melt (Spotify: ultra-smooth blend + reverb)
    wave = "wave"                         # → Wave (Spotify: rhythmic LFO filter pulse)
    tremolo = "tremolo"                   # → Tremolo (volume modulation)
    lunar_echo = "lunar_echo"             # → Lunar Echo (spatial echo + reverb)
    riser = "riser"                       # → Riser (build-up → drop)
    sweep = "sweep"                       # → Sweep (filter/noise sweep)
    hydrant = "hydrant"                   # → Hydrant (combo: echo+reverb+flanger)
    # ── djay Neural Mix (stem-aware) ──→
    neural_fade = "neural_fade"           # → Neural Mix Fade (per-stem fade)
    neural_echo_out = "neural_echo_out"   # → Neural Mix Echo Out (stem-specific)
    harmonic_sustain = "harmonic_sustain" # → Harmonic Sustain (hold A harmony)
    # ── Structural ──
    hard_cut = "hard_cut"                 # → direct cut
    breakdown_drop = "breakdown_drop"     # → structural break entry
    loop_bridge = "loop_bridge"           # → loop-based bridge
    # ── Legacy (kept as aliases) ──
    bass_swap = "bass_swap"               # → alias: eq_bass_swap
    vocal_handoff = "vocal_handoff"       # → alias: neural_fade
    drum_bridge = "drum_bridge"           # → part of neural_fade
    acapella_overlay = "acapella_overlay" # → part of harmonic_sustain
    instrumental_under_vocal = "instrumental_under_vocal"  # → part of harmonic_sustain
    fallback_crossfade = "fallback_crossfade"  # → alias: fade


class TempoStrategy(str, Enum):
    none = "none"
    sync_to_from = "sync_to_from"
    sync_to_to = "sync_to_to"
    tempo_blend = "tempo_blend"


class CurveTarget(str, Enum):
    A_vocals = "A.vocals"
    A_drums = "A.drums"
    A_bass = "A.bass"
    A_other = "A.other"
    B_vocals = "B.vocals"
    B_drums = "B.drums"
    B_bass = "B.bass"
    B_other = "B.other"
    master = "master"


class CurveParam(str, Enum):
    gain = "gain"
    low_eq = "low_eq"
    mid_eq = "mid_eq"
    high_eq = "high_eq"
    highpass = "highpass"
    lowpass = "lowpass"
    echo_send = "echo_send"
    reverb_send = "reverb_send"
    mute = "mute"


class CurveShape(str, Enum):
    linear = "linear"
    equal_power = "equal_power"
    exponential = "exponential"
    s_curve = "s_curve"


STEM_NAMES = ("vocals", "drums", "bass", "other")
_A_STEMS = (CurveTarget.A_vocals, CurveTarget.A_drums, CurveTarget.A_bass, CurveTarget.A_other)
_B_STEMS = (CurveTarget.B_vocals, CurveTarget.B_drums, CurveTarget.B_bass, CurveTarget.B_other)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Data Models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AutomationCurve:
    """One automated parameter curve for a transition.

    points: list of [time_frac, value] — time_frac ∈ [0.0, 1.0] over the transition window.
    shape: interpolation method between points.
    """
    target: CurveTarget
    param: CurveParam
    points: list[tuple[float, float]]
    shape: CurveShape = CurveShape.equal_power

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.value,
            "param": self.param.value,
            "points": self.points,
            "shape": self.shape.value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AutomationCurve":
        return cls(
            target=CurveTarget(d["target"]),
            param=CurveParam(d["param"]),
            points=[(float(p[0]), float(p[1])) for p in d["points"]],
            shape=CurveShape(d.get("shape", "equal_power")),
        )


@dataclass
class TransitionPlan:
    """Universal transition blueprint — consumed by both Jetson renderer and RK3588 engine.

    All timing is in bars (not raw seconds), enabling tempo-independent execution.
    """
    from_song_id: str | int
    to_song_id: str | int
    mode: TransitionMode
    preset: TransitionPreset
    start_bar: int = 0
    duration_bars: int = 8
    bpm_from: float = 120.0
    bpm_to: float = 120.0
    tempo_strategy: TempoStrategy = TempoStrategy.none
    curves: list[AutomationCurve] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_song_id": self.from_song_id,
            "to_song_id": self.to_song_id,
            "mode": self.mode.value,
            "preset": self.preset.value,
            "start_bar": self.start_bar,
            "duration_bars": self.duration_bars,
            "bpm_from": self.bpm_from,
            "bpm_to": self.bpm_to,
            "tempo_strategy": self.tempo_strategy.value,
            "curves": [c.to_dict() for c in self.curves],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TransitionPlan":
        return cls(
            from_song_id=d["from_song_id"],
            to_song_id=d["to_song_id"],
            mode=TransitionMode(d["mode"]),
            preset=TransitionPreset(d["preset"]),
            start_bar=int(d.get("start_bar", 0)),
            duration_bars=int(d.get("duration_bars", 8)),
            bpm_from=float(d.get("bpm_from", 120)),
            bpm_to=float(d.get("bpm_to", 120)),
            tempo_strategy=TempoStrategy(d.get("tempo_strategy", "none")),
            curves=[AutomationCurve.from_dict(c) for c in d.get("curves", [])],
        )


@dataclass
class TrackContext:
    """All known metadata about a track for transition planning."""
    song_id: str | int
    bpm: float | None = None
    camelot_key: str | None = None
    key_name: str | None = None
    energy: str | None = None           # "low" | "medium" | "high"
    duration_sec: float = 0.0
    beat_points: list[float] = field(default_factory=list)
    downbeats: list[float] = field(default_factory=list)
    phrase_map: list[dict] = field(default_factory=list)
    cue_points: list[dict] = field(default_factory=list)
    has_stems: bool = False
    stem_quality_score: float = 0.0     # 0..1, low = artifacts
    vocal_density: float = 0.5           # 0..1, how much vocal content
    bass_energy: float = 0.5             # 0..1, how much bass energy
    intro_is_clean: bool = False
    outro_is_clean: bool = False
    has_drum_loop: bool = False

    @property
    def beat_interval_sec(self) -> float:
        if self.bpm and self.bpm > 0:
            return 60.0 / self.bpm
        return 0.5

    @property
    def bars_to_sec(self) -> float:
        """4 beats per bar."""
        return self.beat_interval_sec * 4


@dataclass
class TransitionScore:
    """Scoring for one transition candidate (pair of songs)."""
    bpm_distance: float = 0.0
    beatgrid_confidence: float = 0.0
    downbeat_confidence: float = 0.0
    key_distance: int = 12              # Camelot steps, 0=same, 1=relative/neighbor
    phrase_match_score: float = 0.0
    energy_delta: float = 1.0           # 0=same, 1=opposite
    vocal_overlap_risk: float = 0.5      # 0=none, 1=certain clash
    bass_conflict_risk: float = 0.5      # 0=compatible, 1=certain clash
    drum_bridge_score: float = 0.0       # 0=can't bridge, 1=perfect bridge
    stem_quality_score: float = 0.0      # 0=no stems, 1=perfect separation
    separation_artifact_risk: float = 0.5 # 0=clean, 1=heavy artifacts
    intro_outro_cleanliness: float = 0.0 # 0=dirty, 1=clean break sections
    transition_confidence: float = 0.0   # overall confidence in this transition

    def to_dict(self) -> dict[str, float]:
        return {
            "bpm_distance": self.bpm_distance,
            "beatgrid_confidence": self.beatgrid_confidence,
            "downbeat_confidence": self.downbeat_confidence,
            "key_distance": self.key_distance,
            "phrase_match_score": self.phrase_match_score,
            "energy_delta": self.energy_delta,
            "vocal_overlap_risk": self.vocal_overlap_risk,
            "bass_conflict_risk": self.bass_conflict_risk,
            "drum_bridge_score": self.drum_bridge_score,
            "stem_quality_score": self.stem_quality_score,
            "separation_artifact_risk": self.separation_artifact_risk,
            "intro_outro_cleanliness": self.intro_outro_cleanliness,
            "transition_confidence": self.transition_confidence,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Curve Engine
# ═══════════════════════════════════════════════════════════════════════════════

def _interp_linear(t: np.ndarray, pts: list[tuple[float, float]]) -> np.ndarray:
    """Linear interpolation through control points."""
    tx = np.array([p[0] for p in pts], dtype=np.float32)
    ty = np.array([p[1] for p in pts], dtype=np.float32)
    return np.interp(t, tx, ty).astype(np.float32)


def _interp_s_curve(t: np.ndarray, pts: list[tuple[float, float]]) -> np.ndarray:
    """Smooth S-curve: first interpolate linearly, then apply smoothstep per segment."""
    raw = _interp_linear(t, pts)
    # Apply smoothstep to the overall envelope for natural feel
    s = 3.0 * raw ** 2 - 2.0 * raw ** 3
    return s.astype(np.float32)


def _interp_equal_power(t: np.ndarray, pts: list[tuple[float, float]]) -> np.ndarray:
    """Equal-power interpolation between first and last point values.

    Points beyond the first/last are used for timing, but the curve maintains
    constant power: cos² + sin² = 1 for stereo-like crossfades.
    """
    if len(pts) < 2:
        return np.full_like(t, pts[0][1] if pts else 0.0, dtype=np.float32)
    v0 = pts[0][1]
    v1 = pts[-1][1]
    # Map t through the points' time range
    t0, t1 = pts[0][0], pts[-1][0]
    span = max(t1 - t0, 1e-8)
    x = np.clip((t - t0) / span, 0.0, 1.0)
    # Equal-power blend
    cos_fade = np.cos(x * np.pi / 2.0)
    sin_fade = np.sin(x * np.pi / 2.0)
    return (v0 * cos_fade + v1 * sin_fade).astype(np.float32)


def _interp_exponential(t: np.ndarray, pts: list[tuple[float, float]]) -> np.ndarray:
    """Exponential interpolation — log-scaled between points."""
    if len(pts) < 2:
        return np.full_like(t, pts[0][1] if pts else 0.0, dtype=np.float32)
    tx = np.array([p[0] for p in pts], dtype=np.float32)
    ty = np.array([max(p[1], 1e-6) for p in pts], dtype=np.float32)  # avoid log(0)
    log_ty = np.log(ty)
    log_raw = np.interp(t, tx, log_ty).astype(np.float32)
    raw = np.exp(log_raw)
    # Re-apply zero at boundaries if explicitly set
    for pt in pts:
        if pt[1] <= 0.0:
            raw[t <= pt[0] + 1e-6] = 0.0
            raw[t >= pt[0] - 1e-6] = 0.0
    return raw.astype(np.float32)


def build_curve(curve: AutomationCurve, num_samples: int, sample_rate: float = 44100.0) -> np.ndarray:
    """Render an AutomationCurve to a sample-level numpy array.

    Args:
        curve: The automation curve specification.
        num_samples: Number of output samples (duration in samples).
        sample_rate: Sample rate (unused currently, for future time-based curves).

    Returns:
        Float32 array of length num_samples with interpolated values.
    """
    if num_samples <= 0:
        return np.zeros(0, dtype=np.float32)

    t = np.linspace(0.0, 1.0, num=num_samples, endpoint=True, dtype=np.float32)
    shape = curve.shape

    if shape == CurveShape.linear:
        return _interp_linear(t, curve.points)
    elif shape == CurveShape.equal_power:
        return _interp_equal_power(t, curve.points)
    elif shape == CurveShape.exponential:
        return _interp_exponential(t, curve.points)
    elif shape == CurveShape.s_curve:
        return _interp_s_curve(t, curve.points)
    else:
        return _interp_linear(t, curve.points)


def build_stereo_curve(curve: AutomationCurve, num_samples: int) -> np.ndarray:
    """Render curve as stereo-compatible (N, 2) array for direct multiplication."""
    mono = build_curve(curve, num_samples)
    return np.column_stack([mono, mono]).astype(np.float32)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Presets — stem-aware transitions
# ═══════════════════════════════════════════════════════════════════════════════
#
# Each preset returns a list[AutomationCurve] that fully describes the transition.
# Time ∈ [0.0, 1.0] where 0.0 = transition start, 1.0 = transition end.
#
# Design invariant: every preset has a non-stem fallback that works with
# full-track audio only (curves targeting "master").

def _bass_swap_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """A drums keep rhythm; A bass exits early; B bass enters late; B drums fade in.

    Never let A.bass and B.bass overlap at full level.
    """
    xf_point = 0.5
    return [
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (xf_point - 0.1, 0.6), (xf_point, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (xf_point, 0.0), (xf_point + 0.1, 0.55), (0.85, 1.0), (1.0, 1.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.55, 0.5), (1.0, 0.0)],
                        CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.25, 0.65), (0.6, 1.0), (1.0, 1.0)],
                        CurveShape.equal_power),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.3, 0.55), (0.65, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (0.55, 0.0), (0.75, 0.6), (1.0, 1.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (0.65, 0.0), (1.0, 0.0)],
                        CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_other, CurveParam.gain,
                        [(0.0, 0.0), (0.2, 0.6), (0.6, 1.0), (1.0, 1.0)],
                        CurveShape.equal_power),
        # Bass swap EQ: A bass duck via highpass, B bass stays clean
        AutomationCurve(CurveTarget.A_bass, CurveParam.highpass,
                        [(0.0, 25.0), (0.3, 60.0), (xf_point, 200.0), (1.0, 200.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.B_bass, CurveParam.lowpass,
                        [(0.0, 120.0), (xf_point, 250.0), (0.75, 16000.0), (1.0, 18000.0)],
                        CurveShape.exponential),
    ]


def _bass_swap_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem bass_swap: EQ-only low-frequency crossover on full tracks."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (1.0, 0.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.master, CurveParam.low_eq,
                        [(0.0, 0.0), (0.3, -4.0), (0.5, -8.0), (1.0, -8.0)],
                        CurveShape.s_curve),
    ]


def _vocal_handoff_curves(duration_bars: int, bpm_from: float, bpm_to: float, **kwargs) -> list[AutomationCurve]:
    """Avoid dual vocal clash: A vocals echo out at phrase boundary, B vocals enter late."""
    exit_point = float(kwargs.get("vocal_exit_point", 0.35))
    entry_point = float(kwargs.get("vocal_entry_point", 0.60))
    return [
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (exit_point, 0.8), (0.5, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.echo_send,
                        [(0.0, 0.0), (exit_point, 0.0), (exit_point + 0.02, 0.55), (0.55, 0.15), (1.0, 0.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (entry_point, 0.0), (entry_point + 0.05, 0.3), (0.8, 0.85), (1.0, 1.0)],
                        CurveShape.s_curve),
        # Remaining stems follow bass_swap pattern
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.3, 0.3), (0.5, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.5, 0.0), (0.6, 0.5), (1.0, 1.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.6, 0.4), (1.0, 0.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.35, 0.6), (0.7, 1.0), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (0.55, 0.0), (1.0, 0.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_other, CurveParam.gain,
                        [(0.0, 0.0), (0.3, 0.5), (0.7, 1.0), (1.0, 1.0)], CurveShape.equal_power),
    ]


def _vocal_handoff_fallback(duration_bars: int, bpm_from: float, bpm_to: float, **kwargs) -> list[AutomationCurve]:
    """Non-stem vocal_handoff: fast crossfade with echo on outgoing deck."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.5, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.master, CurveParam.echo_send,
                        [(0.0, 0.0), (0.4, 0.35), (0.55, 0.15), (1.0, 0.0)], CurveShape.exponential),
    ]


def _drum_bridge_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """A drums sustain rhythm while B bass/melody enter; A drums exit when B drums land."""
    return [
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.5, 0.85), (0.75, 0.25), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.5, 0.0), (0.55, 0.45), (0.8, 1.0), (1.0, 1.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.3, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.2, 0.35), (0.5, 0.8), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.25, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (0.55, 0.0), (0.7, 0.6), (1.0, 1.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_other, CurveParam.gain,
                        [(0.0, 0.0), (0.15, 0.4), (0.5, 0.9), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (0.5, 0.0), (1.0, 0.0)], CurveShape.equal_power),
    ]


def _drum_bridge_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem drum_bridge: extended crossfade favoring B low/mid entry."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.65, 0.5), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.master, CurveParam.highpass,
                        [(0.0, 30.0), (0.4, 80.0), (1.0, 120.0)], CurveShape.exponential),
    ]


def _acapella_overlay_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """A vocals over B instrumental. Requires key_distance <= 1 Camelot step."""
    return [
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.6, 0.85), (0.85, 0.25), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.echo_send,
                        [(0.0, 0.0), (0.7, 0.0), (0.8, 0.5), (0.95, 0.3), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.25, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.2, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (0.3, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.1, 0.7), (0.4, 1.0), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.15, 0.6), (0.4, 1.0), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_other, CurveParam.gain,
                        [(0.0, 0.0), (0.1, 0.5), (0.35, 1.0), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (0.75, 0.0), (0.85, 0.4), (1.0, 1.0)], CurveShape.s_curve),
    ]


def _acapella_overlay_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem acapella_overlay: B enters under A, then A fades out."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.55, 0.7), (1.0, 0.0)], CurveShape.s_curve),
    ]


def _instrumental_under_vocal_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """B instrumental enters under A vocals, A vocals echo out at phrase end."""
    return [
        AutomationCurve(CurveTarget.B_other, CurveParam.gain,
                        [(0.0, 0.0), (0.15, 0.4), (0.5, 0.85), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.2, 0.35), (0.55, 0.85), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.4, 0.0), (0.55, 0.5), (0.85, 1.0), (1.0, 1.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.mute,
                        [(0.0, 1.0), (0.85, 1.0), (0.85, 0.0), (1.0, 0.0)], CurveShape.linear),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.55, 0.9), (0.65, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.echo_send,
                        [(0.0, 0.0), (0.55, 0.0), (0.6, 0.5), (0.75, 0.2), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.35, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.45, 0.3), (0.65, 0.0), (1.0, 0.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (0.35, 0.4), (0.65, 0.0), (1.0, 0.0)], CurveShape.equal_power),
    ]


def _instrumental_under_vocal_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem: B enters at low level, A fades with echo."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.6, 0.55), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.master, CurveParam.echo_send,
                        [(0.0, 0.0), (0.55, 0.35), (0.7, 0.15), (1.0, 0.0)], CurveShape.exponential),
    ]


def _breakdown_drop_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Build tension with FX, drop into B on downbeat. Master limiter prevents overload."""
    drop_point = 0.7
    return [
        # Tension: reduce A
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.25, 0.3), (drop_point, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.3, 0.5), (drop_point - 0.05, 0.1), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (0.2, 0.4), (drop_point, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.2, 0.6), (drop_point, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        # Highpass sweep on A for riser effect
        AutomationCurve(CurveTarget.A_other, CurveParam.highpass,
                        [(0.0, 30.0), (drop_point - 0.1, 120.0), (drop_point, 400.0), (1.0, 400.0)],
                        CurveShape.exponential),
        # Echo on A for tension
        AutomationCurve(CurveTarget.A_vocals, CurveParam.echo_send,
                        [(0.0, 0.0), (0.4, 0.15), (drop_point - 0.05, 0.7), (drop_point, 0.0), (1.0, 0.0)],
                        CurveShape.exponential),
        # Drop: B full stems at drop downbeat
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (drop_point - 0.02, 0.0), (drop_point, 1.0), (1.0, 1.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (drop_point - 0.02, 0.0), (drop_point, 1.0), (1.0, 1.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.B_other, CurveParam.gain,
                        [(0.0, 0.0), (drop_point - 0.02, 0.0), (drop_point, 1.0), (1.0, 1.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (drop_point - 0.02, 0.0), (drop_point + 0.05, 0.0),
                         (drop_point + 0.15, 0.6), (1.0, 1.0)], CurveShape.s_curve),
        # Master headroom: -6dB safety
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 0.5), (drop_point - 0.05, 0.5), (drop_point, 0.71), (0.85, 0.85), (1.0, 1.0)],
                        CurveShape.s_curve),
    ]


def _breakdown_drop_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem breakdown_drop: filter sweep + cut to B."""
    drop_point = 0.7
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (drop_point - 0.05, 1.0), (drop_point, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.master, CurveParam.highpass,
                        [(0.0, 30.0), (drop_point - 0.1, 200.0), (drop_point, 500.0), (1.0, 500.0)],
                        CurveShape.exponential),
    ]


def _loop_bridge_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Loop A drums for a bridge, gradually introduce B, exit loop at phrase boundary."""
    loop_exit = 0.7
    return [
        # A drums stay present through the loop
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.5, 0.9), (loop_exit, 0.6), (loop_exit + 0.1, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
        # A everything else ducks out early
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.15, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.1, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (0.15, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        # B fades in during loop
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.2, 0.35), (0.5, 0.75), (loop_exit, 1.0), (1.0, 1.0)],
                        CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_other, CurveParam.gain,
                        [(0.0, 0.0), (0.15, 0.3), (0.5, 0.8), (loop_exit, 1.0), (1.0, 1.0)],
                        CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.4, 0.0), (loop_exit, 0.0), (loop_exit + 0.05, 0.7), (1.0, 1.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (loop_exit + 0.1, 0.0), (loop_exit + 0.2, 0.6), (1.0, 1.0)],
                        CurveShape.s_curve),
    ]


def _loop_bridge_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem loop_bridge: extended overlap with B low entry."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.65, 0.55), (1.0, 0.0)], CurveShape.s_curve),
    ]


def _echo_freeze_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Short transition: echo/freeze A vocals, B enters at next downbeat.

    Typically 1-4 bars. No long overlap — clean break with echo tail.
    """
    freeze_point = 0.25
    return [
        # A: quick fade with heavy echo for freeze effect
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (freeze_point, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.echo_send,
                        [(0.0, 0.0), (freeze_point - 0.02, 0.0), (freeze_point, 1.0), (0.6, 0.7), (1.0, 0.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.A_drums, CurveParam.echo_send,
                        [(0.0, 0.0), (freeze_point, 0.0), (freeze_point + 0.01, 0.5), (0.5, 0.3), (1.0, 0.0)],
                        CurveShape.exponential),
        # A everything else cuts
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (freeze_point, 0.0), (1.0, 0.0)], CurveShape.linear),
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (freeze_point - 0.05, 0.0), (1.0, 0.0)], CurveShape.linear),
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (freeze_point, 0.0), (1.0, 0.0)], CurveShape.linear),
        # B enters at downbeat after freeze
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (freeze_point + 0.02, 0.0), (freeze_point + 0.05, 0.85), (1.0, 1.0)],
                        CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (freeze_point + 0.02, 0.0), (freeze_point + 0.05, 0.8), (1.0, 1.0)],
                        CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_other, CurveParam.gain,
                        [(0.0, 0.0), (freeze_point + 0.02, 0.0), (freeze_point + 0.05, 0.7), (1.0, 1.0)],
                        CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (freeze_point + 0.1, 0.0), (freeze_point + 0.2, 0.5), (1.0, 1.0)],
                        CurveShape.s_curve),
    ]


def _echo_freeze_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem echo_freeze: short crossfade with heavy echo."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.25, 0.0), (1.0, 0.0)], CurveShape.linear),
        AutomationCurve(CurveTarget.master, CurveParam.echo_send,
                        [(0.0, 0.0), (0.2, 0.8), (0.5, 0.5), (1.0, 0.0)], CurveShape.exponential),
    ]


def _hard_cut_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Instant switch at phrase boundary. Optional 1-beat echo tail on A drums/vocals."""
    cut_point = 0.5
    return [
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (cut_point - 0.01, 1.0), (cut_point, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (cut_point - 0.01, 1.0), (cut_point, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (cut_point - 0.01, 1.0), (cut_point, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (cut_point - 0.01, 1.0), (cut_point, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        # 1-beat echo tail on A to soften the cut
        AutomationCurve(CurveTarget.A_vocals, CurveParam.echo_send,
                        [(0.0, 0.0), (cut_point - 0.02, 0.0), (cut_point, 0.6), (cut_point + 0.1, 0.15), (1.0, 0.0)],
                        CurveShape.linear),
        # B enters instantly
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (cut_point - 0.01, 0.0), (cut_point, 1.0), (1.0, 1.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (cut_point - 0.01, 0.0), (cut_point, 1.0), (1.0, 1.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.B_other, CurveParam.gain,
                        [(0.0, 0.0), (cut_point - 0.01, 0.0), (cut_point, 1.0), (1.0, 1.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (cut_point - 0.01, 0.0), (cut_point, 1.0), (1.0, 1.0)],
                        CurveShape.linear),
    ]


def _hard_cut_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem hard_cut: instant switch with optional tail."""
    cut_point = 0.5
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (cut_point - 0.01, 1.0), (cut_point, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.master, CurveParam.echo_send,
                        [(0.0, 0.0), (cut_point, 0.5), (cut_point + 0.08, 0.1), (1.0, 0.0)],
                        CurveShape.linear),
    ]


def _fallback_crossfade_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Pure equal-power crossfade on full tracks. Never fails."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (1.0, 0.0)], CurveShape.equal_power),
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Preset Registry
# ═══════════════════════════════════════════════════════════════════════════════

# Maps each preset to (stem_aware_curves_fn, fallback_curves_fn, stem_required_bool)
# ═══════════════════════════════════════════════════════════════════════════════
# 5c. UPDATED Preset Registry — all 18+ presets (new + legacy aliases)
# PRESET_REGISTRY moved to end of file (after all curve function definitions)
# See section 7 at the bottom.

def _compute_vocal_handoff_timing(
    from_ctx: TrackContext,
    to_ctx: TrackContext,
    duration_bars: int,
    bpm_from: float,
) -> dict[str, float]:
    """Compute exit_point and entry_point from track context data.

    exit_point: where in the transition window (0..1) A vocals start fading.
    entry_point: where in the transition window B vocals start entering.

    Uses beat grid, vocal density, intro/outro cleanliness from TrackContext.
    Falls back to original hardcoded values (0.35 / 0.60) when context data is sparse.
    """
    exit_point: float = 0.35
    entry_point: float = 0.60
    bpm = max(bpm_from, 1.0)
    transition_duration_sec = duration_bars * 4.0 * (60.0 / bpm)

    # ---- exit_point: when A vocals start fading ----
    if from_ctx.outro_is_clean:
        exit_point = 0.25
    elif from_ctx.vocal_density > 0.7:
        exit_point = 0.40
    elif from_ctx.vocal_density < 0.3:
        exit_point = 0.28

    # Snap to nearest phrase boundary from beat grid
    if from_ctx.beat_points and bpm > 0:
        beat_interval = from_ctx.beat_interval_sec
        phrase_beats = 32 if bpm >= 96 else 16
        target_sec = exit_point * transition_duration_sec
        target_beat = int(target_sec / beat_interval) if beat_interval > 0 else 0
        snapped_beat = round(target_beat / phrase_beats) * phrase_beats
        snapped_sec = snapped_beat * beat_interval
        if 0 < snapped_sec < transition_duration_sec * 0.8:
            exit_point = round(snapped_sec / transition_duration_sec, 3)

    # ---- entry_point: when B vocals start entering ----
    if to_ctx.intro_is_clean:
        entry_point = 0.70
    elif to_ctx.vocal_density > 0.7:
        entry_point = 0.50
    elif to_ctx.vocal_density < 0.3:
        entry_point = 0.55

    # Snap to nearest phrase boundary
    if to_ctx.beat_points and (to_ctx.bpm or 120) > 0:
        to_bpm = max(to_ctx.bpm or 120, 1.0)
        beat_interval = to_ctx.beat_interval_sec
        phrase_beats = 32 if to_bpm >= 96 else 16
        target_sec = entry_point * transition_duration_sec
        target_beat = int(target_sec / beat_interval) if beat_interval > 0 else 0
        snapped_beat = round(target_beat / phrase_beats) * phrase_beats
        snapped_sec = snapped_beat * beat_interval
        if transition_duration_sec * 0.2 < snapped_sec < transition_duration_sec * 0.95:
            entry_point = round(snapped_sec / transition_duration_sec, 3)

    # Safety: ensure gap between A-vocal exit and B-vocal entry
    if entry_point - exit_point < 0.15:
        entry_point = min(exit_point + 0.20, 0.90)

    return {
        "vocal_exit_point": round(exit_point, 3),
        "vocal_entry_point": round(entry_point, 3),
    }



def generate_plan(
    from_ctx: TrackContext,
    to_ctx: TrackContext,
    preset: TransitionPreset,
    duration_bars: int = 8,
    tempo_strategy: TempoStrategy = TempoStrategy.none,
) -> TransitionPlan:
    """Generate a TransitionPlan for a given preset and track pair."""
    has_stems = from_ctx.has_stems and to_ctx.has_stems
    stem_ok = has_stems and min(from_ctx.stem_quality_score, to_ctx.stem_quality_score) >= 0.4
    stem_fn, fallback_fn, stem_required = PRESET_REGISTRY[preset]

    # Build preset-specific parameters
    preset_kwargs: dict[str, Any] = {}
    if preset == TransitionPreset.vocal_handoff:
        preset_kwargs = _compute_vocal_handoff_timing(from_ctx, to_ctx, duration_bars, from_ctx.bpm or 120.0)  # type: ignore[dict-item]

    if stem_ok and stem_required:
        curves = stem_fn(duration_bars, from_ctx.bpm or 120.0, to_ctx.bpm or 120.0, **preset_kwargs)
        mode = TransitionMode.stem_aware
    else:
        curves = fallback_fn(duration_bars, from_ctx.bpm or 120.0, to_ctx.bpm or 120.0, **preset_kwargs)
        mode = TransitionMode.non_stem

    # In non-stem mode, all A.* and B.* targets must be replaced by "master"
    if mode == TransitionMode.non_stem:
        curves = _non_stem_curves(curves, duration_bars, from_ctx.bpm or 120.0, to_ctx.bpm or 120.0)

    return TransitionPlan(
        from_song_id=from_ctx.song_id,
        to_song_id=to_ctx.song_id,
        mode=mode,
        preset=preset,
        duration_bars=duration_bars,
        bpm_from=from_ctx.bpm or 120.0,
        bpm_to=to_ctx.bpm or 120.0,
        tempo_strategy=tempo_strategy,
        curves=curves,
    )


def _non_stem_curves(
    stem_curves: list[AutomationCurve],
    duration_bars: int,
    bpm_from: float,
    bpm_to: float,
) -> list[AutomationCurve]:
    """Extract non-stem fallback curves. When stems aren't available,
    use the fallback_fn directly instead of trying to convert stem curves."""
    preset = TransitionPreset.fallback_crossfade
    _, fallback_fn, _ = PRESET_REGISTRY[preset]
    return fallback_fn(duration_bars, bpm_from, bpm_to)


# ═══════════════════════════════════════════════════════════════════════════════
# 5b. NEW PRESETS — djay-aligned transition library
# ═══════════════════════════════════════════════════════════════════════════════

# ── Fade (djay: Fade) ────────────────────────────────────────────────────────

def _fade_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Simple A↓ B↑ crossfade — djay Fade equivalent."""
    return [
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.4, 0.7), (1.0, 0.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.5, 0.5), (1.0, 0.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.35, 0.55), (1.0, 0.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (0.45, 0.6), (1.0, 0.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (0.3, 0.4), (0.7, 0.85), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.25, 0.35), (0.6, 0.9), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.35, 0.3), (0.7, 0.85), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_other, CurveParam.gain,
                        [(0.0, 0.0), (0.3, 0.45), (0.65, 0.9), (1.0, 1.0)], CurveShape.equal_power),
    ]


def _fade_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem fade: master crossfade."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.35, 0.65), (0.7, 0.25), (1.0, 0.0)], CurveShape.equal_power),
    ]


# ── Filter Sweep (djay: Filter) ──────────────────────────────────────────────

def _filter_sweep_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """HPF sweep on A → LPF release on B — classic DJ filter transition."""
    return [
        # A: gradually high-pass out (lose bass → lose mids → gone)
        AutomationCurve(CurveTarget.A_drums, CurveParam.highpass,
                        [(0.0, 25.0), (0.3, 80.0), (0.55, 300.0), (0.8, 2000.0), (1.0, 8000.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.A_bass, CurveParam.highpass,
                        [(0.0, 25.0), (0.25, 100.0), (0.5, 400.0), (1.0, 2000.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.highpass,
                        [(0.0, 80.0), (0.5, 250.0), (0.75, 1000.0), (1.0, 4000.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.A_other, CurveParam.highpass,
                        [(0.0, 40.0), (0.4, 200.0), (0.7, 1500.0), (1.0, 6000.0)],
                        CurveShape.exponential),
        # B: enter with lowpass opening up (bass first → full spectrum)
        AutomationCurve(CurveTarget.B_drums, CurveParam.lowpass,
                        [(0.0, 120.0), (0.3, 250.0), (0.6, 2000.0), (0.85, 12000.0), (1.0, 18000.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.B_bass, CurveParam.lowpass,
                        [(0.0, 90.0), (0.2, 180.0), (0.5, 800.0), (1.0, 18000.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.lowpass,
                        [(0.0, 200.0), (0.4, 600.0), (0.7, 4000.0), (1.0, 18000.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.B_other, CurveParam.lowpass,
                        [(0.0, 150.0), (0.35, 500.0), (0.65, 3000.0), (1.0, 18000.0)],
                        CurveShape.exponential),
        # Gain curves
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.6, 0.55), (1.0, 0.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.2, 0.5), (0.5, 0.95), (1.0, 1.0)], CurveShape.equal_power),
    ]


def _filter_sweep_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem filter: master HPF sweep → B enters."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.highpass,
                        [(0.0, 30.0), (0.3, 100.0), (0.6, 600.0), (1.0, 4000.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.5, 0.55), (1.0, 0.0)], CurveShape.s_curve),
    ]


# ── Dissolve (djay: Dissolve) ────────────────────────────────────────────────
# Simulates granular/gating fragmentation via rapid gain tremolo + reverb wash.

def _dissolve_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """A fragments into sparse slices; B fades in. Uses rapid gain + reverb."""
    beat_sec = 60.0 / max(bpm_from, 1.0)
    return [
        # A: rapid tremolo-like gating (simulated via stepped gain points)
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.15, 0.8), (0.16, 0.2), (0.3, 0.6), (0.31, 0.1),
                         (0.45, 0.4), (0.46, 0.05), (0.55, 0.2), (0.56, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.2, 0.7), (0.21, 0.15), (0.35, 0.5), (0.36, 0.1),
                         (0.5, 0.25), (0.51, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.25, 0.05), (1.0, 0.0)], CurveShape.s_curve),
        # Wash with reverb
        AutomationCurve(CurveTarget.A_other, CurveParam.reverb_send,
                        [(0.0, 0.0), (0.2, 0.3), (0.5, 0.65), (0.7, 0.3), (1.0, 0.0)],
                        CurveShape.s_curve),
        # B enters smoothly
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.4, 0.3), (0.65, 0.8), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (0.5, 0.25), (0.75, 0.8), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.55, 0.3), (0.8, 0.9), (1.0, 1.0)], CurveShape.s_curve),
    ]


def _dissolve_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem dissolve: fast tremolo fade + reverb on master."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.15, 0.7), (0.16, 0.15), (0.3, 0.5), (0.31, 0.1),
                         (0.45, 0.3), (0.46, 0.05), (0.55, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.master, CurveParam.reverb_send,
                        [(0.0, 0.0), (0.25, 0.4), (0.55, 0.55), (0.75, 0.2), (1.0, 0.0)],
                        CurveShape.s_curve),
    ]


# ── Melt (Spotify: ultra-smooth blend) ──────────────────────────────────────
# Extremely gradual 16-24 bar transition where A "melts" into reverb while
# B enters almost imperceptibly. Designed for same-genre, close-BPM tracks.

def _melt_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Ultra-smooth melt: A slowly dissolves into reverb, B fades in underneath."""
    return [
        # A: very slow gain decay with reverb wash
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.3, 0.95), (0.5, 0.8), (0.7, 0.45), (0.85, 0.15), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.25, 0.95), (0.5, 0.75), (0.75, 0.35), (0.9, 0.1), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.35, 0.85), (0.6, 0.4), (0.8, 0.1), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (0.4, 0.9), (0.65, 0.55), (0.85, 0.2), (1.0, 0.0)],
                        CurveShape.s_curve),
        # Reverb: slowly build then fade — the "melt" effect
        AutomationCurve(CurveTarget.A_vocals, CurveParam.reverb_send,
                        [(0.0, 0.0), (0.15, 0.15), (0.4, 0.45), (0.6, 0.55), (0.8, 0.35), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_other, CurveParam.reverb_send,
                        [(0.0, 0.0), (0.2, 0.2), (0.45, 0.5), (0.65, 0.5), (0.85, 0.25), (1.0, 0.0)],
                        CurveShape.s_curve),
        # B: enters very gradually, almost imperceptibly
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.2, 0.1), (0.4, 0.35), (0.6, 0.65), (0.8, 0.9), (1.0, 1.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (0.3, 0.05), (0.5, 0.3), (0.7, 0.6), (0.85, 0.85), (1.0, 1.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.25, 0.08), (0.45, 0.35), (0.65, 0.7), (0.85, 0.95), (1.0, 1.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_other, CurveParam.gain,
                        [(0.0, 0.0), (0.2, 0.12), (0.45, 0.4), (0.7, 0.75), (0.9, 0.95), (1.0, 1.0)],
                        CurveShape.s_curve),
    ]


def _melt_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem melt: ultra-slow master crossfade with heavy reverb wash."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.3, 0.9), (0.55, 0.65), (0.8, 0.25), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.master, CurveParam.reverb_send,
                        [(0.0, 0.0), (0.15, 0.25), (0.4, 0.5), (0.65, 0.5), (0.85, 0.2), (1.0, 0.0)],
                        CurveShape.s_curve),
    ]


# ── Wave (Spotify: rhythmic flowing transition) ──────────────────────────────
# LFO-like filter modulation synced to beat, creating a "breathing" pulse
# during the transition. Feels like the energy is surging rhythmically.

def _wave_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Wave: rhythmic LFO-modulated filter sweep with volume pulses."""
    beat_sec = 60.0 / max(bpm_from, 1.0)
    # Create 8 rhythmic pulses over the transition (synced to 2-bar intervals)
    return [
        # A: lowpass filter pulses — rhythmic "breathing out"
        AutomationCurve(CurveTarget.A_drums, CurveParam.lowpass,
                        [(0.0, 18000.0),
                         (0.08, 3000.0), (0.12, 12000.0),  # pulse 1
                         (0.2, 2000.0), (0.24, 9000.0),     # pulse 2
                         (0.32, 1500.0), (0.36, 6000.0),    # pulse 3
                         (0.44, 800.0), (0.48, 3500.0),     # pulse 4
                         (0.56, 400.0), (0.6, 2000.0),      # pulse 5
                         (0.68, 200.0), (0.72, 1000.0),     # pulse 6
                         (0.8, 100.0), (0.84, 500.0),       # pulse 7
                         (0.9, 50.0), (1.0, 50.0)],         # final close
                        CurveShape.exponential),
        # A: volume pulses synced with filter
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0),
                         (0.08, 0.75), (0.12, 0.95),
                         (0.2, 0.6), (0.24, 0.85),
                         (0.32, 0.45), (0.36, 0.7),
                         (0.44, 0.3), (0.48, 0.55),
                         (0.56, 0.15), (0.6, 0.35),
                         (0.68, 0.05), (0.72, 0.2),
                         (0.8, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        # A vocals: more aggressive pulsing out
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0),
                         (0.1, 0.6), (0.14, 0.85),
                         (0.24, 0.35), (0.28, 0.6),
                         (0.38, 0.15), (0.42, 0.35),
                         (0.52, 0.05), (0.56, 0.15),
                         (0.65, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        # B: inverse filter pulse — "breathing in"
        AutomationCurve(CurveTarget.B_drums, CurveParam.highpass,
                        [(0.0, 8000.0),
                         (0.08, 5000.0), (0.12, 800.0),
                         (0.2, 4000.0), (0.24, 400.0),
                         (0.32, 2500.0), (0.36, 200.0),
                         (0.44, 1500.0), (0.48, 100.0),
                         (0.56, 800.0), (0.6, 50.0),
                         (0.68, 300.0), (0.72, 30.0),
                         (0.8, 100.0), (0.9, 25.0), (1.0, 25.0)],
                        CurveShape.exponential),
        # B: volume pulses in
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0),
                         (0.08, 0.15), (0.12, 0.35),
                         (0.2, 0.25), (0.24, 0.5),
                         (0.32, 0.35), (0.36, 0.6),
                         (0.44, 0.5), (0.48, 0.75),
                         (0.56, 0.65), (0.6, 0.85),
                         (0.68, 0.8), (0.72, 0.95),
                         (0.8, 0.9), (0.9, 1.0), (1.0, 1.0)],
                        CurveShape.linear),
        # B bass: smooth entry under the wave pulses
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.3, 0.0), (0.45, 0.3), (0.6, 0.55), (0.8, 0.85), (1.0, 1.0)],
                        CurveShape.s_curve),
    ]


def _wave_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem wave: master-level rhythmic filter pulses + volume modulation."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.lowpass,
                        [(0.0, 18000.0),
                         (0.08, 3000.0), (0.12, 10000.0),
                         (0.2, 2000.0), (0.24, 7000.0),
                         (0.32, 1200.0), (0.36, 4500.0),
                         (0.44, 600.0), (0.48, 2500.0),
                         (0.56, 250.0), (0.6, 1200.0),
                         (0.68, 100.0), (0.72, 500.0),
                         (0.8, 50.0), (1.0, 50.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0),
                         (0.08, 0.75), (0.12, 0.9),
                         (0.2, 0.55), (0.24, 0.8),
                         (0.32, 0.35), (0.36, 0.6),
                         (0.44, 0.2), (0.48, 0.45),
                         (0.56, 0.08), (0.6, 0.25),
                         (0.68, 0.02), (0.72, 0.12),
                         (0.8, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
    ]


# ── Tremolo (djay: Tremolo) ──────────────────────────────────────────────────

def _tremolo_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Periodic volume modulation on A's outgoing stems."""
    beat_sec = 60.0 / max(bpm_from, 1.0)
    return [
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.1, 0.7), (0.11, 0.95), (0.2, 0.55), (0.21, 0.85),
                         (0.3, 0.35), (0.31, 0.7), (0.4, 0.15), (0.41, 0.5),
                         (0.5, 0.05), (0.51, 0.25), (0.6, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.12, 0.6), (0.13, 0.9), (0.25, 0.4), (0.26, 0.75),
                         (0.38, 0.2), (0.39, 0.55), (0.5, 0.05), (0.51, 0.25), (0.6, 0.0), (1.0, 0.0)],
                        CurveShape.linear),
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.3, 0.15), (0.55, 0.6), (0.8, 1.0), (1.0, 1.0)],
                        CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (0.4, 0.2), (0.65, 0.7), (0.85, 1.0), (1.0, 1.0)],
                        CurveShape.equal_power),
    ]


def _tremolo_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem tremolo: periodic master gain modulation."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.1, 0.65), (0.11, 0.9), (0.2, 0.45), (0.21, 0.75),
                         (0.3, 0.25), (0.31, 0.55), (0.4, 0.1), (0.41, 0.35),
                         (0.5, 0.0), (1.0, 0.0)], CurveShape.linear),
    ]


# ── Lunar Echo (djay: Lunar Echo) ────────────────────────────────────────────

def _lunar_echo_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Spatial echo with long reverb tail — djay Lunar Echo."""
    return [
        # A: long echo send with spatial character
        AutomationCurve(CurveTarget.A_vocals, CurveParam.echo_send,
                        [(0.0, 0.0), (0.1, 0.0), (0.15, 0.45), (0.4, 0.65), (0.6, 0.45), (0.85, 0.2), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_drums, CurveParam.echo_send,
                        [(0.0, 0.0), (0.2, 0.35), (0.45, 0.5), (0.65, 0.3), (0.85, 0.1), (1.0, 0.0)],
                        CurveShape.s_curve),
        # Reverb for spatial depth
        AutomationCurve(CurveTarget.A_other, CurveParam.reverb_send,
                        [(0.0, 0.0), (0.1, 0.25), (0.35, 0.55), (0.6, 0.4), (0.8, 0.2), (1.0, 0.0)],
                        CurveShape.s_curve),
        # A gain fades after echo peak
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.2, 0.85), (0.35, 0.45), (0.55, 0.1), (0.7, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.25, 0.7), (0.4, 0.3), (0.6, 0.0), (1.0, 0.0)],
                        CurveShape.equal_power),
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.15, 0.5), (0.3, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
        # B enters under the echo tail
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.3, 0.15), (0.5, 0.6), (0.75, 0.95), (1.0, 1.0)],
                        CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (0.45, 0.15), (0.65, 0.55), (0.85, 0.95), (1.0, 1.0)],
                        CurveShape.s_curve),
    ]


def _lunar_echo_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem lunar echo: echo + reverb on master → B crossfade."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.echo_send,
                        [(0.0, 0.0), (0.12, 0.4), (0.35, 0.6), (0.55, 0.4), (0.8, 0.15), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.master, CurveParam.reverb_send,
                        [(0.0, 0.0), (0.15, 0.35), (0.4, 0.5), (0.65, 0.3), (0.85, 0.1), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.3, 0.85), (0.5, 0.35), (0.7, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
    ]


# ── Riser (djay: Riser) ──────────────────────────────────────────────────────

def _riser_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Energy build-up: A pitch/energy rises → B drop."""
    return [
        # A: rising highpass (frequency sweep up → tension build)
        AutomationCurve(CurveTarget.A_drums, CurveParam.highpass,
                        [(0.0, 30.0), (0.3, 100.0), (0.6, 400.0), (0.85, 2000.0), (1.0, 8000.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.A_bass, CurveParam.highpass,
                        [(0.0, 25.0), (0.35, 150.0), (0.7, 600.0), (1.0, 3000.0)],
                        CurveShape.exponential),
        # A: gain pushed up slightly then cut
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.4, 1.15), (0.7, 1.1), (0.85, 0.5), (1.0, 0.0)],
                        CurveShape.s_curve),
        # A: reverb swell for tension
        AutomationCurve(CurveTarget.A_other, CurveParam.reverb_send,
                        [(0.0, 0.0), (0.3, 0.2), (0.6, 0.5), (0.8, 0.7), (0.9, 0.4), (1.0, 0.0)],
                        CurveShape.s_curve),
        # B: full impact entry at the drop point
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.8, 0.0), (0.85, 0.7), (0.95, 1.0), (1.0, 1.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.8, 0.0), (0.85, 0.6), (0.95, 1.0), (1.0, 1.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (0.82, 0.0), (0.88, 0.5), (0.95, 1.0), (1.0, 1.0)],
                        CurveShape.s_curve),
    ]


def _riser_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem riser: HPF sweep on master → hard cut → B enter."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.highpass,
                        [(0.0, 30.0), (0.25, 120.0), (0.55, 500.0), (0.8, 3000.0), (1.0, 10000.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.7, 1.1), (0.85, 0.4), (1.0, 0.0)], CurveShape.s_curve),
    ]


# ── Sweep (djay: Sweep) ──────────────────────────────────────────────────────

def _sweep_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Sweeping filter across full spectrum — A pushed out, B pulled in."""
    return [
        # A: sweeping band-reject → full kill
        AutomationCurve(CurveTarget.A_drums, CurveParam.lowpass,
                        [(0.0, 18000.0), (0.2, 8000.0), (0.5, 1500.0), (0.7, 200.0), (1.0, 50.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.lowpass,
                        [(0.0, 18000.0), (0.15, 10000.0), (0.4, 2500.0), (0.65, 500.0), (1.0, 80.0)],
                        CurveShape.exponential),
        # B: sweeping lowpass opening
        AutomationCurve(CurveTarget.B_drums, CurveParam.lowpass,
                        [(0.0, 80.0), (0.3, 300.0), (0.55, 2500.0), (0.8, 12000.0), (1.0, 18000.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.lowpass,
                        [(0.0, 100.0), (0.25, 400.0), (0.5, 3000.0), (0.75, 10000.0), (1.0, 18000.0)],
                        CurveShape.exponential),
        # Gain crossfade synced with sweep
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.4, 0.7), (0.7, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.3, 0.3), (0.6, 0.85), (1.0, 1.0)], CurveShape.s_curve),
    ]


def _sweep_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem sweep: master lowpass sweep → crossfade."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.lowpass,
                        [(0.0, 18000.0), (0.25, 5000.0), (0.55, 800.0), (0.75, 120.0), (1.0, 40.0)],
                        CurveShape.exponential),
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.5, 0.55), (1.0, 0.0)], CurveShape.s_curve),
    ]


# ── Hydrant (djay: Hydrant) ──────────────────────────────────────────────────

def _hydrant_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Combo macro: echo + reverb + flanger wash → dramatic landing → B takeover."""
    return [
        # A: echo swell
        AutomationCurve(CurveTarget.A_vocals, CurveParam.echo_send,
                        [(0.0, 0.0), (0.1, 0.3), (0.3, 0.6), (0.5, 0.75), (0.65, 0.45), (0.8, 0.2), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_drums, CurveParam.echo_send,
                        [(0.0, 0.0), (0.15, 0.25), (0.35, 0.5), (0.55, 0.6), (0.7, 0.35), (0.85, 0.15), (1.0, 0.0)],
                        CurveShape.s_curve),
        # A: reverb wash
        AutomationCurve(CurveTarget.A_other, CurveParam.reverb_send,
                        [(0.0, 0.0), (0.1, 0.35), (0.3, 0.6), (0.5, 0.7), (0.7, 0.45), (0.85, 0.2), (1.0, 0.0)],
                        CurveShape.s_curve),
        # A: highpass sweep out
        AutomationCurve(CurveTarget.A_bass, CurveParam.highpass,
                        [(0.0, 25.0), (0.2, 80.0), (0.45, 250.0), (0.7, 800.0), (1.0, 3000.0)],
                        CurveShape.exponential),
        # A gain: pushed then dropped
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.3, 1.1), (0.5, 1.0), (0.65, 0.5), (0.8, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.2, 1.05), (0.4, 0.85), (0.6, 0.3), (0.8, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
        # B: dramatic entry
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.75, 0.0), (0.82, 0.7), (0.92, 1.0), (1.0, 1.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.75, 0.0), (0.85, 0.8), (0.95, 1.0), (1.0, 1.0)],
                        CurveShape.s_curve),
    ]


def _hydrant_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem hydrant: echo + reverb on master → hard cut → B enter."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.echo_send,
                        [(0.0, 0.0), (0.1, 0.4), (0.3, 0.65), (0.5, 0.7), (0.7, 0.35), (0.85, 0.1), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.master, CurveParam.reverb_send,
                        [(0.0, 0.0), (0.15, 0.45), (0.35, 0.6), (0.55, 0.55), (0.75, 0.25), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.4, 1.1), (0.6, 0.65), (0.8, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
    ]


# ── Neural Mix Fade (djay: Neural Mix Fade) ──────────────────────────────────

def _neural_fade_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Per-stem staggered fade: avoid vocal+low overlap. djay Neural Mix Fade."""
    return [
        # Phase 1 (0-30%): A bass out, B drums in (rhythm anchor)
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.2, 0.3), (0.35, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.05, 0.25), (0.25, 0.7), (0.5, 1.0), (1.0, 1.0)], CurveShape.equal_power),
        # Phase 2 (25-55%): A vocals out, B bass in
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.3, 0.7), (0.5, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.35, 0.0), (0.45, 0.5), (0.65, 1.0), (1.0, 1.0)], CurveShape.s_curve),
        # Phase 3 (45-100%): A drums out, B vocals + other in
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.5, 0.6), (0.75, 0.0), (1.0, 0.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (0.55, 0.0), (0.65, 0.4), (0.85, 1.0), (1.0, 1.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (0.4, 0.5), (0.7, 0.0), (1.0, 0.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_other, CurveParam.gain,
                        [(0.0, 0.0), (0.3, 0.2), (0.6, 0.7), (0.85, 1.0), (1.0, 1.0)], CurveShape.equal_power),
    ]


def _neural_fade_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem neural fade: extended crossfade with EQ mid-low swap."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.4, 0.7), (0.7, 0.25), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.master, CurveParam.low_eq,
                        [(0.0, 0.0), (0.2, -3.0), (0.45, -6.0), (0.65, -3.0), (0.85, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
    ]


# ── Neural Mix Echo Out (djay: Neural Mix Echo Out) ──────────────────────────

def _neural_echo_out_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Stem-specific echo out: vocals/melody echo, rhythm stays → then exits."""
    return [
        # Vocals: echo out (the main effect)
        AutomationCurve(CurveTarget.A_vocals, CurveParam.echo_send,
                        [(0.0, 0.0), (0.15, 0.3), (0.35, 0.6), (0.55, 0.5), (0.75, 0.25), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.2, 0.65), (0.4, 0.15), (0.55, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
        # Other (harmony/melody): lighter echo
        AutomationCurve(CurveTarget.A_other, CurveParam.echo_send,
                        [(0.0, 0.0), (0.2, 0.25), (0.4, 0.4), (0.6, 0.3), (0.8, 0.1), (1.0, 0.0)],
                        CurveShape.s_curve),
        # Drums: hold rhythm longer, then exit
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.4, 0.9), (0.6, 0.4), (0.8, 0.0), (1.0, 0.0)],
                        CurveShape.equal_power),
        # Bass: quick exit to make room
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.15, 0.5), (0.35, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        # B: drums anchor early, vocals enter after A vocal echo fades
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.2, 0.35), (0.45, 0.8), (0.7, 1.0), (1.0, 1.0)], CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (0.5, 0.0), (0.6, 0.3), (0.8, 0.85), (1.0, 1.0)], CurveShape.s_curve),
    ]


def _neural_echo_out_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem neural echo: master echo out + fast crossfade."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.echo_send,
                        [(0.0, 0.0), (0.15, 0.4), (0.35, 0.55), (0.55, 0.4), (0.75, 0.15), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.25, 0.65), (0.5, 0.15), (0.65, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
    ]


# ── Harmonic Sustain (djay: Harmonic Sustain / 和声持续) ─────────────────────

def _harmonic_sustain_curves(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Hold A's harmony/melody while B's rhythm enters. djay Harmonic Sustain."""
    return [
        # A: keep other (harmony/pads) and vocals, drop bass + drums early
        AutomationCurve(CurveTarget.A_bass, CurveParam.gain,
                        [(0.0, 1.0), (0.15, 0.3), (0.3, 0.0), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_drums, CurveParam.gain,
                        [(0.0, 1.0), (0.3, 0.6), (0.55, 0.0), (1.0, 0.0)], CurveShape.equal_power),
        # A: harmony + vocals sustain with slight reverb
        AutomationCurve(CurveTarget.A_other, CurveParam.gain,
                        [(0.0, 1.0), (0.5, 0.7), (0.75, 0.2), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_other, CurveParam.reverb_send,
                        [(0.0, 0.0), (0.3, 0.2), (0.55, 0.45), (0.75, 0.3), (1.0, 0.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.A_vocals, CurveParam.gain,
                        [(0.0, 1.0), (0.4, 0.8), (0.65, 0.3), (0.85, 0.0), (1.0, 0.0)],
                        CurveShape.s_curve),
        # B: rhythm enters under the sustained harmony
        AutomationCurve(CurveTarget.B_drums, CurveParam.gain,
                        [(0.0, 0.0), (0.1, 0.4), (0.35, 0.85), (0.6, 1.0), (1.0, 1.0)],
                        CurveShape.equal_power),
        AutomationCurve(CurveTarget.B_bass, CurveParam.gain,
                        [(0.0, 0.0), (0.25, 0.3), (0.5, 0.8), (0.75, 1.0), (1.0, 1.0)],
                        CurveShape.s_curve),
        AutomationCurve(CurveTarget.B_vocals, CurveParam.gain,
                        [(0.0, 0.0), (0.55, 0.0), (0.7, 0.35), (0.9, 0.85), (1.0, 1.0)],
                        CurveShape.s_curve),
    ]


def _harmonic_sustain_fallback(duration_bars: int, bpm_from: float, bpm_to: float) -> list[AutomationCurve]:
    """Non-stem harmonic sustain: B enters under A with EQ shaping."""
    return [
        AutomationCurve(CurveTarget.master, CurveParam.gain,
                        [(0.0, 1.0), (0.4, 0.8), (0.7, 0.35), (1.0, 0.0)], CurveShape.s_curve),
        AutomationCurve(CurveTarget.master, CurveParam.highpass,
                        [(0.0, 30.0), (0.35, 100.0), (0.65, 250.0), (1.0, 500.0)],
                        CurveShape.exponential),
    ]
# ═══════════════════════════════════════════════════════════════════════════════

def _camelot_distance(a: str | None, b: str | None) -> int:
    """Camelot wheel distance: 0=same, 1=relative/neighbor, 2+=clash."""
    if not a or not b:
        return 6  # unknown
    a, b = a.strip().upper(), b.strip().upper()
    if a == b:
        return 0
    try:
        na, ma = int(a[:-1]), a[-1]
        nb, mb = int(b[:-1]), b[-1]
    except (ValueError, IndexError):
        return 6
    if na == nb and ma != mb:
        return 1  # relative
    if ma == mb and ((na % 12) + 1 == nb or (nb % 12) + 1 == na):
        return 1  # neighbor
    # Ring distance
    ring_dist = min(abs(na - nb), 12 - abs(na - nb))
    return ring_dist


def score_transition_candidates(
    from_ctx: TrackContext,
    to_ctx: TrackContext,
) -> TransitionScore:
    """Score a track-to-track transition across all dimensions.

    All scores ∈ [0, 1] unless otherwise noted.
    """
    s = TransitionScore()

    # -- BPM distance (0 = same BPM) --
    if from_ctx.bpm and to_ctx.bpm and from_ctx.bpm > 0 and to_ctx.bpm > 0:
        ratio = to_ctx.bpm / from_ctx.bpm
        candidates = [ratio, ratio / 2.0, ratio * 2.0]
        best = min(candidates, key=lambda x: abs(1.0 - x))
        s.bpm_distance = min(1.0, abs(1.0 - best) / 0.08)
    else:
        s.bpm_distance = 0.5

    # -- Beatgrid confidence --
    a_beats_ok = len(from_ctx.beat_points) >= 8
    b_beats_ok = len(to_ctx.beat_points) >= 8
    s.beatgrid_confidence = (0.5 if a_beats_ok else 0.1) * (0.5 if b_beats_ok else 0.1) * 4.0

    # -- Downbeat confidence --
    a_db_ok = len(from_ctx.downbeats) >= 4
    b_db_ok = len(to_ctx.downbeats) >= 4
    s.downbeat_confidence = (0.5 if a_db_ok else 0.1) * (0.5 if b_db_ok else 0.1) * 4.0

    # -- Key distance --
    s.key_distance = _camelot_distance(from_ctx.camelot_key, to_ctx.camelot_key)

    # -- Phrase match --
    a_phrases = len(from_ctx.phrase_map)
    b_phrases = len(to_ctx.phrase_map)
    if a_phrases >= 2 and b_phrases >= 2:
        s.phrase_match_score = 0.85
    elif a_phrases >= 1 or b_phrases >= 1:
        s.phrase_match_score = 0.5
    else:
        s.phrase_match_score = 0.15

    # -- Energy delta --
    energy_map = {"low": 0, "medium": 1, "high": 2}
    ea = energy_map.get((from_ctx.energy or "").lower(), 1)
    eb = energy_map.get((to_ctx.energy or "").lower(), 1)
    s.energy_delta = abs(ea - eb) / 2.0

    # -- Vocal overlap risk --
    s.vocal_overlap_risk = min(1.0, from_ctx.vocal_density * to_ctx.vocal_density * 1.5)

    # -- Bass conflict risk --
    s.bass_conflict_risk = min(1.0, from_ctx.bass_energy * to_ctx.bass_energy * 1.4)

    # -- Drum bridge score --
    # Good drum bridge when A drums are stable and B intro is clean
    if from_ctx.has_drum_loop and to_ctx.intro_is_clean:
        s.drum_bridge_score = 0.85
    elif from_ctx.has_drum_loop:
        s.drum_bridge_score = 0.55
    elif to_ctx.intro_is_clean:
        s.drum_bridge_score = 0.4
    else:
        s.drum_bridge_score = 0.15

    # -- Stem quality --
    if from_ctx.has_stems and to_ctx.has_stems:
        s.stem_quality_score = min(from_ctx.stem_quality_score, to_ctx.stem_quality_score)
    else:
        s.stem_quality_score = 0.0

    # -- Separation artifact risk --
    if s.stem_quality_score > 0:
        s.separation_artifact_risk = 1.0 - s.stem_quality_score
    else:
        s.separation_artifact_risk = 1.0

    # -- Intro/outro cleanliness --
    s.intro_outro_cleanliness = (
        0.7 if to_ctx.intro_is_clean else 0.3
    ) * (
        0.7 if from_ctx.outro_is_clean else 0.3
    ) / 0.49  # normalize

    # -- Overall confidence (weighted) --
    s.transition_confidence = (
        0.20 * (1.0 - s.bpm_distance)
        + 0.15 * s.beatgrid_confidence
        + 0.10 * s.downbeat_confidence
        + 0.15 * (1.0 - s.key_distance / 12.0)
        + 0.10 * s.phrase_match_score
        + 0.10 * (1.0 - s.energy_delta)
        + 0.05 * (1.0 - s.separation_artifact_risk)
        + 0.05 * s.drum_bridge_score
        + 0.05 * s.intro_outro_cleanliness
        + 0.05 * min(1.0, s.stem_quality_score * 2.0)
    )
    s.transition_confidence = min(1.0, max(0.0, s.transition_confidence))

    return s


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Decision Engine — select best preset per transition
# ═══════════════════════════════════════════════════════════════════════════════

def select_best_preset(
    from_ctx: TrackContext,
    to_ctx: TrackContext,
    scores: TransitionScore | None = None,
) -> tuple[TransitionPreset, TransitionMode, TransitionScore]:
    """Choose the best transition preset for a track pair.

    Design philosophy:
      Stem-aware presets (vocal_handoff, bass_swap, drum_bridge, echo_freeze,
      loop_bridge, breakdown_drop) are intentionally NOT penalized for BPM/key
      distance — they are designed to handle those mismatches by isolating stems:
        * vocal_handoff: no vocal overlap → key clash irrelevant
        * bass_swap: bass frequencies isolated → BPM/key impact minimized
        * drum_bridge: drums are unpitched → key irrelevant; drums carry rhythm
        * echo_freeze: echo blurs pitch, short window avoids alignment issues

      Only presets that layer pitched material (acapella_overlay,
      instrumental_under_vocal) are gated by key compatibility (key_distance <= 2).
      The global confidence safety net (confidence < 0.25 → hard_cut) still applies.

    Decision rules (in priority order):
    1. Very low confidence (< 0.25) → hard_cut
    2. No stems or low stem quality → only non-stem presets
    3. Dual vocal high density → vocal_handoff or echo_freeze
    4. Dual bass high energy → bass_swap mandatory
    5. Clean breakdown/drop → breakdown_drop
    6. Weak B intro + stable A drums → drum_bridge
    7. Key-compatible → acapella_overlay or instrumental_under_vocal (only if key ok)

    Returns (best_preset, mode, scores).
    """
    if scores is None:
        scores = score_transition_candidates(from_ctx, to_ctx)

    has_stems = from_ctx.has_stems and to_ctx.has_stems
    stem_ok = has_stems and scores.stem_quality_score >= 0.4
    key_ok = scores.key_distance <= 2
    confidence = scores.transition_confidence

    # Rule 7: Very low confidence → shortest safe transition
    if confidence < 0.25:
        return TransitionPreset.hard_cut, TransitionMode.non_stem, scores

    # Rule 1: No stems → only non-stem presets
    if not stem_ok:
        # Select best non-stem preset
        candidates: list[tuple[float, TransitionPreset]] = []

        if scores.bass_conflict_risk > 0.5:
            candidates.append((0.7, TransitionPreset.bass_swap))  # EQ-based fallback, no BPM/key gate
        if scores.vocal_overlap_risk > 0.6:
            candidates.append((0.75, TransitionPreset.echo_freeze))
            candidates.append((0.65, TransitionPreset.vocal_handoff))  # becomes blend fallback
        if scores.drum_bridge_score > 0.4:
            candidates.append((0.6, TransitionPreset.drum_bridge))
        if confidence < 0.4:
            candidates.append((0.7, TransitionPreset.hard_cut))

        # Default fallback
        candidates.append((0.5, TransitionPreset.fallback_crossfade))

        candidates.sort(key=lambda x: x[0], reverse=True)
        best = candidates[0][1]
        return best, TransitionMode.non_stem, scores

    # Stem-aware decision logic
    candidates: list[tuple[float, TransitionPreset]] = []

    # Rule 4: Bass conflict → bass_swap
    if scores.bass_conflict_risk > 0.5:
        candidates.append((0.8, TransitionPreset.bass_swap))

    # Rule 3: Dual vocal → vocal_handoff or echo_freeze
    if scores.vocal_overlap_risk > 0.55:
        candidates.append((0.85, TransitionPreset.vocal_handoff))
        candidates.append((0.7, TransitionPreset.echo_freeze))

    # Rule 6: Clean breakdown → breakdown_drop
    if scores.intro_outro_cleanliness > 0.6 and scores.energy_delta > 0.3:
        candidates.append((0.82, TransitionPreset.breakdown_drop))

    # Rule 5: Drum bridge
    if scores.drum_bridge_score > 0.35:
        candidates.append((0.65, TransitionPreset.drum_bridge))

    # Rule 2: Key-compatible acapella_overlay
    if key_ok and scores.vocal_overlap_risk < 0.5 and scores.stem_quality_score > 0.6:
        candidates.append((0.78, TransitionPreset.acapella_overlay))

    # Instrumental under vocal
    if key_ok and from_ctx.vocal_density > 0.4 and to_ctx.intro_is_clean:
        candidates.append((0.72, TransitionPreset.instrumental_under_vocal))

    # Loop bridge
    if from_ctx.has_drum_loop or to_ctx.has_drum_loop:
        candidates.append((0.6, TransitionPreset.loop_bridge))

    # Rule 7: Low confidence → short echo/cut
    if confidence < 0.35:
        candidates.append((0.75, TransitionPreset.echo_freeze))
        candidates.append((0.7, TransitionPreset.hard_cut))

    # Always available
    candidates.append((0.45, TransitionPreset.bass_swap))
    candidates.append((0.35, TransitionPreset.fallback_crossfade))

    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0][1]
    return best, TransitionMode.stem_aware, scores


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Offline Renderer — renders TransitionPlan to audio
# ═══════════════════════════════════════════════════════════════════════════════

def _load_stem(stem_name: str, stem_paths: dict[str, str] | None,
               cache: dict[str, np.ndarray], sample_rate: int) -> np.ndarray | None:
    import os
    if not stem_paths:
        return None
    path = stem_paths.get(stem_name)
    if not path or not os.path.isfile(path):
        return None
    try:
        import librosa
        audio, _ = librosa.load(path, sr=sample_rate, mono=True)
        return audio.astype(np.float32)
    except Exception:
        return None


def render_transition_plan(
    plan: TransitionPlan,
    from_audio_path: str,
    to_audio_path: str,
    from_stems: dict[str, str] | None,
    to_stems: dict[str, str] | None,
    sample_rate: int = 44100,
    from_at_sec: float = 0.0,
    to_at_sec: float = 0.0,
) -> np.ndarray:
    """Render a TransitionPlan to a stereo numpy array.

    Args:
        plan: The transition plan (from generate_plan or hand-crafted).
        from_audio_path: Path to the A track's original audio.
        to_audio_path: Path to the B track's original audio.
        from_stems: Dict of stem_name → path for A.
        to_stems: Dict of stem_name → path for B.
        sample_rate: Output sample rate.
        from_at_sec: Where in A to start the transition.
        to_at_sec: Where in B to start.

    Returns:
        Stereo float32 numpy array of shape (N, 2).
    """
    import os
    try:
        import librosa
    except ImportError:
        raise RuntimeError("librosa required for offline rendering")

    # Load audio
    from_audio, _ = librosa.load(from_audio_path, sr=sample_rate, mono=False)
    to_audio, _ = librosa.load(to_audio_path, sr=sample_rate, mono=False)
    if from_audio.ndim == 1:
        from_audio = np.column_stack([from_audio, from_audio])
    if to_audio.ndim == 1:
        to_audio = np.column_stack([to_audio, to_audio])
    if from_audio.shape[1] > 2:
        from_audio = from_audio[:, :2]
    if to_audio.shape[1] > 2:
        to_audio = to_audio[:, :2]

    from_audio = from_audio.astype(np.float32)
    to_audio = to_audio.astype(np.float32)

    # Load stems
    stems_a: dict[str, np.ndarray] = {}
    stems_b: dict[str, np.ndarray] = {}
    cache: dict[str, np.ndarray] = {}

    if plan.mode == TransitionMode.stem_aware:
        for name in STEM_NAMES:
            s = _load_stem(name, from_stems, cache, sample_rate)
            if s is not None:
                stems_a[name] = s
            s = _load_stem(name, to_stems, cache, sample_rate)
            if s is not None:
                stems_b[name] = s

    # Duration in samples
    duration_sec = plan.duration_bars * 4.0 * (60.0 / plan.bpm_from)
    num_samples = int(duration_sec * sample_rate)

    # Slice from/to at the transition point
    from_start = int(max(0, from_at_sec) * sample_rate)
    to_start = int(max(0, to_at_sec) * sample_rate)

    def _slice(audio: np.ndarray, start: int, nsamples: int) -> np.ndarray:
        end = start + nsamples
        if start >= audio.shape[0]:
            return np.zeros((nsamples, audio.shape[1]), dtype=np.float32)
        chunk = audio[start:min(end, audio.shape[0])]
        if chunk.shape[0] < nsamples:
            pad = np.zeros((nsamples - chunk.shape[0], audio.shape[1]), dtype=np.float32)
            chunk = np.vstack([chunk, pad])
        return chunk.astype(np.float32)

    from_chunk = _slice(from_audio, from_start, num_samples)
    to_chunk = _slice(to_audio, to_start, num_samples)

    stem_chunks_a: dict[str, np.ndarray] = {}
    stem_chunks_b: dict[str, np.ndarray] = {}
    for name, audio in stems_a.items():
        stem_chunks_a[name] = _slice(audio.reshape(-1, 1), from_start, num_samples)
    for name, audio in stems_b.items():
        stem_chunks_b[name] = _slice(audio.reshape(-1, 1), to_start, num_samples)

    # Apply each curve
    output = np.zeros((num_samples, 2), dtype=np.float32)

    for curve in plan.curves:
        # Build stereo gain envelope
        gain_mono = build_curve(curve, num_samples, sample_rate)
        gain_stereo = np.column_stack([gain_mono, gain_mono]).astype(np.float32)

        target = curve.target
        param = curve.param

        if param == CurveParam.mute:
            # Mute means multiply by (1 - gain) essentially, but we handle it as gain=0
            # For mute curves, the points represent mute state: 1.0=fully muted, 0.0=unmuted
            gain_stereo = 1.0 - gain_stereo

        if param in (CurveParam.gain, CurveParam.mute):
            multiplier = gain_stereo
        elif param == CurveParam.echo_send:
            # Echo send: mix in delayed copy scaled by gain
            # Simplified: just pass the gain through for now
            # Full echo implementation would need a delay line
            multiplier = gain_stereo
        else:
            # EQ/filter params are applied per-sample by RK3588 audio engine
            # For offline rendering, we skip EQ curves (they need biquad)
            if param in (CurveParam.low_eq, CurveParam.mid_eq, CurveParam.high_eq,
                         CurveParam.highpass, CurveParam.lowpass, CurveParam.reverb_send):
                continue
            multiplier = gain_stereo

        # Map curve target to audio chunk
        if target == CurveTarget.master:
            output += from_chunk * (1.0 - gain_stereo) + to_chunk * gain_stereo
        elif target in _A_STEMS:
            stem_name = target.value.split(".")[1]
            if stem_name in stem_chunks_a:
                output += stem_chunks_a[stem_name] * multiplier
            elif stem_name in _A_STEMS:
                # Fallback: use full A audio
                pass
        elif target in _B_STEMS:
            stem_name = target.value.split(".")[1]
            if stem_name in stem_chunks_b:
                output += stem_chunks_b[stem_name] * multiplier

    # If no curves targeted master nor stems, fall back to simple crossfade
    rms_out = float(np.sqrt(np.mean(np.square(output))) if output.size else 0.0)
    if rms_out < 1e-6:
        t = np.linspace(0.0, 1.0, num_samples, dtype=np.float32)
        cos_fade = np.cos(t * np.pi / 2.0).astype(np.float32)
        sin_fade = np.sin(t * np.pi / 2.0).astype(np.float32)
        output = (from_chunk * cos_fade[:, None] + to_chunk * sin_fade[:, None]).astype(np.float32)

    # Headroom safety: -6dBFS
    peak = float(np.max(np.abs(output))) if output.size else 0.0
    if peak > 0.5:
        output = output / peak * 0.5

    return output


# ═══════════════════════════════════════════════════════════════════════════════
# 9. High-level API — build a full transition plan with auto-preset selection
# ═══════════════════════════════════════════════════════════════════════════════

def build_automix_transition(
    from_ctx: TrackContext,
    to_ctx: TrackContext,
    duration_bars: int = 8,
    tempo_strategy: TempoStrategy | None = None,
    force_preset: TransitionPreset | None = None,
) -> TransitionPlan:
    """Build a complete TransitionPlan with auto-preset selection.

    Args:
        from_ctx: Source track context.
        to_ctx: Destination track context.
        duration_bars: Transition duration in bars (4-beat bars).
        tempo_strategy: If None, auto-selected based on BPM difference.
        force_preset: If set, skip scoring and use this preset directly.

    Returns:
        A TransitionPlan ready for rendering or RK3588 execution.
    """
    # Score the transition
    scores = score_transition_candidates(from_ctx, to_ctx)

    # Select preset
    if force_preset:
        preset = force_preset
        mode = TransitionMode.stem_aware if (
            from_ctx.has_stems and to_ctx.has_stems and scores.stem_quality_score >= 0.4
        ) else TransitionMode.non_stem
    else:
        preset, mode, scores = select_best_preset(from_ctx, to_ctx, scores)

    # Auto tempo strategy
    if tempo_strategy is None:
        # bpm_distance is normalized so 1.0 means an 8% tempo shift.
        raw_bpm_distance = scores.bpm_distance * 0.08
        if raw_bpm_distance < 0.001:
            tempo_strategy = TempoStrategy.none
        elif raw_bpm_distance < 0.06:
            tempo_strategy = TempoStrategy.sync_to_from
        elif raw_bpm_distance < 0.08:
            tempo_strategy = TempoStrategy.tempo_blend
        else:
            tempo_strategy = TempoStrategy.none

    # Generate the plan
    has_stems = from_ctx.has_stems and to_ctx.has_stems
    stem_fn, fallback_fn, _ = PRESET_REGISTRY[preset]

    if mode == TransitionMode.stem_aware and has_stems:
        curves = stem_fn(duration_bars, from_ctx.bpm or 120.0, to_ctx.bpm or 120.0)
    else:
        curves = fallback_fn(duration_bars, from_ctx.bpm or 120.0, to_ctx.bpm or 120.0)
        mode = TransitionMode.non_stem

    if mode == TransitionMode.non_stem:
        curves = _non_stem_curves(curves, duration_bars, from_ctx.bpm or 120.0, to_ctx.bpm or 120.0)

    return TransitionPlan(
        from_song_id=from_ctx.song_id,
        to_song_id=to_ctx.song_id,
        mode=mode,
        preset=preset,
        duration_bars=duration_bars,
        bpm_from=from_ctx.bpm or 120.0,
        bpm_to=to_ctx.bpm or 120.0,
        tempo_strategy=tempo_strategy,
        curves=curves,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 7. AUTO SELECTOR — djay "自动" mode
# ═══════════════════════════════════════════════════════════════════════════════

def auto_select_preset(
    from_ctx: TrackContext,
    to_ctx: TrackContext,
    *,
    intent: str | None = None,
) -> TransitionPreset:
    """Automatically select the best transition preset for a track pair."""
    has_stems_a = bool(from_ctx.stem_activity.get("vocals", 0) > 0 if from_ctx.stem_activity else False)
    has_stems_b = bool(to_ctx.stem_activity.get("vocals", 0) > 0 if to_ctx.stem_activity else False)
    stems_ok = has_stems_a and has_stems_b

    bpm_a = from_ctx.bpm or 120.0
    bpm_b = to_ctx.bpm or 120.0
    ratio = max(bpm_a, bpm_b) / min(bpm_a, bpm_b)

    key_dist = _camelot_distance(from_ctx.camelot_key, to_ctx.camelot_key)
    e_diff = (to_ctx.energy or 0.5) - (from_ctx.energy or 0.5)

    v_a = float(from_ctx.stem_activity.get("vocals", 0)) if from_ctx.stem_activity else 0
    v_b = float(to_ctx.stem_activity.get("vocals", 0)) if to_ctx.stem_activity else 0
    b_a = float(from_ctx.stem_activity.get("bass", 0)) if from_ctx.stem_activity else 0
    b_b = float(to_ctx.stem_activity.get("bass", 0)) if to_ctx.stem_activity else 0

    if ratio > 1.12:
        return TransitionPreset.neural_echo_out if stems_ok else TransitionPreset.hydrant
    if ratio > 1.06:
        return TransitionPreset.lunar_echo if stems_ok else TransitionPreset.echo_freeze
    if intent == "energy_up" and e_diff > 0.15 and bpm_b > 120:
        return TransitionPreset.riser
    if key_dist <= 1 and stems_ok and abs(e_diff) < 0.25:
        return TransitionPreset.harmonic_sustain
    if v_a > 0.5 and v_b > 0.5:
        return TransitionPreset.neural_fade if stems_ok else TransitionPreset.echo_freeze
    if b_a > 0.5 and b_b > 0.5:
        return TransitionPreset.eq_bass_swap if stems_ok else TransitionPreset.filter_sweep
    if e_diff > 0.3 and bpm_b > 125:
        return TransitionPreset.riser
    if (from_ctx.energy or 0.5) < 0.35 and (to_ctx.energy or 0.5) < 0.35:
        return TransitionPreset.dissolve
    return TransitionPreset.neural_fade if stems_ok else TransitionPreset.fade


DJAY_MENU: dict[str, TransitionPreset | None] = {
    "auto": None, "fade": TransitionPreset.fade, "filter": TransitionPreset.filter_sweep,
    "eq": TransitionPreset.eq_bass_swap, "echo": TransitionPreset.echo_freeze,
    "dissolve": TransitionPreset.dissolve, "melt": TransitionPreset.melt,
    "wave": TransitionPreset.wave, "tremolo": TransitionPreset.tremolo,
    "lunar_echo": TransitionPreset.lunar_echo, "riser": TransitionPreset.riser,
    "sweep": TransitionPreset.sweep, "hydrant": TransitionPreset.hydrant,
    "neural_fade": TransitionPreset.neural_fade,
    "neural_echo_out": TransitionPreset.neural_echo_out,
    "harmonic_sustain": TransitionPreset.harmonic_sustain,
    "hard_cut": TransitionPreset.hard_cut,
    "breakdown_drop": TransitionPreset.breakdown_drop,
    "loop_bridge": TransitionPreset.loop_bridge,
}

PRESET_CATEGORIES = {
    "basic": {"label_zh": "基础过渡", "keys": ["auto","fade","filter","eq","echo"]},
    "creative": {"label_zh": "创意效果", "keys": ["dissolve","melt","wave","tremolo","lunar_echo","riser","sweep","hydrant"]},
    "neural_mix": {"label_zh": "Neural Mix", "keys": ["neural_fade","neural_echo_out","harmonic_sustain"], "needs_stems": True},
    "structural": {"label_zh": "结构型", "keys": ["hard_cut","breakdown_drop","loop_bridge"]},
}

PRESET_META = {
    "auto": {"zh": "自动", "desc": "分析A、B后自动选择最佳效果和过渡点"},
    "fade": {"zh": "淡入淡出", "desc": "A音量渐降B渐升，最自然"},
    "filter": {"zh": "过滤器", "desc": "HPF/LPF扫频，经典DJ过渡感"},
    "eq": {"zh": "EQ低频交换", "desc": "先退A bass再入B bass"},
    "echo": {"zh": "回声淡出", "desc": "A加echo尾部，B快速进入"},
    "dissolve": {"zh": "碎片消散", "desc": "A被切碎消散，B进入"},
    "melt":     {"zh": "融合渐变", "desc": "极慢reverb融合，两首歌融化在一起"},
    "wave":     {"zh": "波浪脉动", "desc": "LFO节奏型滤波脉冲，呼吸感过渡"},
    "tremolo": {"zh": "颤音衰减", "desc": "A音量周期性起伏后切换到B"},
    "lunar_echo": {"zh": "太空回声", "desc": "空间感echo+reverb，尾巴更长更飘"},
    "riser": {"zh": "能量爬升", "desc": "逐步提升能量，类似drop前build-up"},
    "sweep": {"zh": "频谱扫过", "desc": "扫频滤过频谱，推走A带出B"},
    "hydrant": {"zh": "消防栓", "desc": "强组合：echo+reverb+flanger"},
    "neural_fade": {"zh": "Neural淡入淡出", "desc": "分轨独立控制，避免人声和低频叠加"},
    "neural_echo_out": {"zh": "Neural回声", "desc": "人声/旋律加echo退出"},
    "harmonic_sustain": {"zh": "和声持续", "desc": "保留A旋律/和声，引入B节奏"},
    "hard_cut": {"zh": "硬切", "desc": "直接切到B"},
    "breakdown_drop": {"zh": "断点切入", "desc": "A breakdown时切入B drop"},
    "loop_bridge": {"zh": "Loop桥接", "desc": "Loop A鼓组过渡到B"},
}


def select_transition(
    from_ctx: TrackContext,
    to_ctx: TrackContext,
    *,
    user_preset: str = "auto",
    intent: str | None = None,
) -> tuple[TransitionPreset, list[AutomationCurve], dict]:
    """C6→C4 bridge: pick preset + generate automation curves."""
    if user_preset and user_preset != "auto":
        preset = DJAY_MENU.get(user_preset, TransitionPreset.fade)
    else:
        preset = auto_select_preset(from_ctx, to_ctx, intent=intent)

    stem_fn, fallback_fn, stem_req = PRESET_REGISTRY[preset]
    has_stems = bool(
        from_ctx.stem_activity and to_ctx.stem_activity and
        from_ctx.stem_activity.get("vocals", 0) > 0
    )
    mode = "stem_aware" if (stem_req and has_stems) else "non_stem"

    bpm_f = from_ctx.bpm or 120.0
    bpm_t = to_ctx.bpm or 120.0
    ratio = max(bpm_f, bpm_t) / min(bpm_f, bpm_t)
    if ratio > 1.12:   dur = 2
    elif ratio > 1.06: dur = 4
    elif preset in (TransitionPreset.riser, TransitionPreset.hydrant): dur = 16
    elif preset in (TransitionPreset.lunar_echo, TransitionPreset.dissolve): dur = 12
    else:               dur = 8

    curves = stem_fn(dur, bpm_f, bpm_t) if mode == "stem_aware" else fallback_fn(dur, bpm_f, bpm_t)

    meta = {
        "mode": mode, "duration_bars": dur,
        "tempo_strategy": "sync_to_from" if ratio < 1.06 else "none",
        "stems_required": stem_req, "stems_available": has_stems,
        "preset_meta": PRESET_META.get(preset.value, {}),
    }
    return preset, curves, meta


# ═══════════════════════════════════════════════════════════════════════════════
# PRESET_REGISTRY — all presets with stem + fallback curve functions
# (Must be after ALL curve function definitions)
# ═══════════════════════════════════════════════════════════════════════════════

PRESET_REGISTRY: dict[
    TransitionPreset,
    tuple[callable, callable, bool],  # (stem_fn, fallback_fn, needs_stems)
] = {
    TransitionPreset.fade:                (_fade_curves,                _fade_fallback,                False),
    TransitionPreset.filter_sweep:        (_filter_sweep_curves,        _filter_sweep_fallback,        False),
    TransitionPreset.eq_bass_swap:        (_bass_swap_curves,           _bass_swap_fallback,           True),
    TransitionPreset.echo_freeze:         (_echo_freeze_curves,         _echo_freeze_fallback,         True),
    TransitionPreset.dissolve:            (_dissolve_curves,            _dissolve_fallback,            False),
    TransitionPreset.melt:                (_melt_curves,                _melt_fallback,                False),
    TransitionPreset.wave:                (_wave_curves,                _wave_fallback,                False),
    TransitionPreset.tremolo:             (_tremolo_curves,             _tremolo_fallback,             False),
    TransitionPreset.lunar_echo:          (_lunar_echo_curves,          _lunar_echo_fallback,          True),
    TransitionPreset.riser:               (_riser_curves,               _riser_fallback,               False),
    TransitionPreset.sweep:               (_sweep_curves,               _sweep_fallback,               False),
    TransitionPreset.hydrant:             (_hydrant_curves,             _hydrant_fallback,             True),
    TransitionPreset.neural_fade:         (_neural_fade_curves,         _neural_fade_fallback,         True),
    TransitionPreset.neural_echo_out:     (_neural_echo_out_curves,     _neural_echo_out_fallback,     True),
    TransitionPreset.harmonic_sustain:    (_harmonic_sustain_curves,    _harmonic_sustain_fallback,    True),
    TransitionPreset.hard_cut:            (_hard_cut_curves,            _hard_cut_fallback,            True),
    TransitionPreset.breakdown_drop:      (_breakdown_drop_curves,      _breakdown_drop_fallback,      True),
    TransitionPreset.loop_bridge:         (_loop_bridge_curves,         _loop_bridge_fallback,         True),
    # Legacy aliases
    TransitionPreset.bass_swap:           (_bass_swap_curves,           _bass_swap_fallback,           True),
    TransitionPreset.vocal_handoff:       (_vocal_handoff_curves,       _vocal_handoff_fallback,       True),
    TransitionPreset.drum_bridge:         (_drum_bridge_curves,         _drum_bridge_fallback,         True),
    TransitionPreset.acapella_overlay:    (_acapella_overlay_curves,    _acapella_overlay_fallback,    True),
    TransitionPreset.instrumental_under_vocal: (_instrumental_under_vocal_curves, _instrumental_under_vocal_fallback, True),
    TransitionPreset.fallback_crossfade:  (_fallback_crossfade_curves,  _fallback_crossfade_curves,    False),
}
