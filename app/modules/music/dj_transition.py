"""
DJ Transition Engine (DJ.studio-inspired)
==========================================

Professional transition automation with EQ, filter, and FX curves.
Produces per-stem automation curves at 10Hz for frontend playback.

Transition presets:
  smooth     — EQ crossfade: A's low fades first, then mids, then highs
  power      — Equal-power gain crossfade (clean, no EQ tricks)
  bass_swap  — Classic DJ bass exchange at midpoint
  echo_out   — Echo/delay tail on A, clean B fade-in
  filter     — Hi-pass sweep on A + lo-pass ramp on B
  cut        — Hard instant switch
  slam       — Quick high-energy 2-beat burst transition

Reference: DJ.studio timeline automation system
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class TransitionAutomation:
    """
    Per-stem automation for a single A→B transition overlap.
    All arrays are sampled at `sample_rate` Hz (default 10Hz).
    Values are gain multipliers 0.0 - 1.0.
    """
    total_duration_sec: float
    sample_rate: float = 10.0

    # A track stems
    a_drums: list[float] = field(default_factory=list)
    a_bass: list[float] = field(default_factory=list)
    a_vocals: list[float] = field(default_factory=list)
    a_other: list[float] = field(default_factory=list)

    # B track stems
    b_drums: list[float] = field(default_factory=list)
    b_bass: list[float] = field(default_factory=list)
    b_vocals: list[float] = field(default_factory=list)
    b_other: list[float] = field(default_factory=list)

    # Master volume (applied on top of stem gains)
    a_volume: list[float] = field(default_factory=list)
    b_volume: list[float] = field(default_factory=list)

    # Echo/reverb tail on A (0=dry, 1=full wet)
    a_echo: list[float] = field(default_factory=list)


TRANSITION_STYLES = [
    "smooth", "power", "bass_swap", "echo_out", "filter", "cut", "slam",
]


def generate_transition_automation(
    overlap_sec: float,
    overlap_bars: int,
    bpm: float,
    style: str = "smooth",
) -> TransitionAutomation:
    """
    Generate DJ.studio-style per-stem transition automation curves.
    """
    if overlap_sec <= 0:
        overlap_sec = 8.0

    sr = 10.0
    n = max(1, int(overlap_sec * sr))

    auto = TransitionAutomation(
        total_duration_sec=overlap_sec,
        sample_rate=sr,
    )

    builder = _BUILDERS.get(style, _build_smooth)
    builder(auto, n, overlap_sec, bpm)

    return auto


# ── Smooth: EQ crossfade (low fades first) ─────────────────────────────────

def _build_smooth(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    """
    DJ.studio-style smooth EQ crossfade.
    A fades out: bass goes first (0→33%), then vocals/other (33→66%), then drums last (66→100%).
    B fades in: drums first (0→33%), then vocals/other (33→66%), then bass last (66→100%).
    This creates a "sweep" effect without frequency clashing.
    """
    for i in range(n):
        t = i / max(n - 1, 1)  # 0→1

        # A fading out: staggered EQ departure
        a_bass    = _r(_smooth_fade(t, 0.0, 0.4))    # bass exits first
        a_vocals  = _r(_smooth_fade(t, 0.15, 0.6))   # vocals follow
        a_other   = _r(_smooth_fade(t, 0.2, 0.7))    # mids/highs follow
        a_drums   = _r(_smooth_fade(t, 0.3, 0.85))   # drums leave last
        a_vol     = _r(1.0 - _ease_in(t) * 0.4)      # gentle master dip

        # B fading in: staggered EQ entry
        b_drums   = _r(_smooth_entry(t, 0.0, 0.5))   # drums arrive first
        b_other   = _r(_smooth_entry(t, 0.15, 0.65))  # mids/highs follow
        b_vocals  = _r(_smooth_entry(t, 0.3, 0.8))   # vocals after
        b_bass    = _r(_smooth_entry(t, 0.4, 0.9))   # bass arrives last
        b_vol     = _r(_ease_in(t * 0.7 + 0.3))

        auto.a_drums.append(a_drums); auto.a_bass.append(a_bass)
        auto.a_vocals.append(a_vocals); auto.a_other.append(a_other)
        auto.a_volume.append(a_vol); auto.a_echo.append(_r(t * 0.3))

        auto.b_drums.append(b_drums); auto.b_bass.append(b_bass)
        auto.b_vocals.append(b_vocals); auto.b_other.append(b_other)
        auto.b_volume.append(b_vol)


def _smooth_fade(t: float, start: float, end: float) -> float:
    """Fade out from 1→0 between start and end timestamps (0-1 range)."""
    if t <= start:
        return 1.0
    if t >= end:
        return 0.0
    p = (t - start) / (end - start)
    return 1.0 - _ease_in_out(p)


def _smooth_entry(t: float, start: float, end: float) -> float:
    """Fade in from 0→1 between start and end timestamps (0-1 range)."""
    if t <= start:
        return 0.0
    if t >= end:
        return 1.0
    p = (t - start) / (end - start)
    return _ease_in_out(p)


# ── Power: equal-power crossfade ───────────────────────────────────────────

def _build_power(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    """Classic equal-power crossfade. Clean and simple."""
    for i in range(n):
        t = i / max(n - 1, 1)
        a_vol = math.cos(t * math.pi / 2)
        b_vol = math.sin(t * math.pi / 2)

        auto.a_drums.append(_r(a_vol)); auto.a_bass.append(_r(a_vol))
        auto.a_vocals.append(_r(a_vol)); auto.a_other.append(_r(a_vol))
        auto.a_volume.append(_r(a_vol)); auto.a_echo.append(0.0)

        auto.b_drums.append(_r(b_vol)); auto.b_bass.append(_r(b_vol))
        auto.b_vocals.append(_r(b_vol)); auto.b_other.append(_r(b_vol))
        auto.b_volume.append(_r(b_vol))


# ── Bass Swap: classic DJ bass exchange ────────────────────────────────────

def _build_bass_swap(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    """
    Classic bass swap at midpoint:
    Phase 1 (0→swap): A full, B enters without bass/vocals
    Swap: A bass cuts, B bass restores
    Phase 2 (swap→end): A fades out with echo, B takes over
    """
    swap = n // 2

    for i in range(n):
        if i < swap:
            p = i / max(swap, 1)
            auto.a_drums.append(1.0); auto.a_bass.append(1.0)
            auto.a_vocals.append(1.0); auto.a_other.append(1.0)
            auto.a_volume.append(1.0); auto.a_echo.append(0.0)

            auto.b_drums.append(_r(_ease_in(p) * 0.7))
            auto.b_bass.append(0.0)
            auto.b_vocals.append(0.0)
            auto.b_other.append(_r(_ease_in(p) * 0.6))
            auto.b_volume.append(_r(_ease_in(p) * 0.7))
        else:
            remaining = n - swap
            p = (i - swap) / max(remaining, 1)

            auto.a_drums.append(_r(_ease_out(1 - p) * 0.8))
            auto.a_bass.append(0.0)
            auto.a_vocals.append(_r(_ease_out(1 - p) * 0.7))
            auto.a_other.append(_r(_ease_out(1 - p) * 0.6))
            auto.a_volume.append(_r(_ease_out(1 - p)))
            auto.a_echo.append(_r(_ease_in(p) * 0.8))

            auto.b_drums.append(_r(0.7 + 0.3 * _ease_in(p)))
            auto.b_bass.append(1.0)
            auto.b_vocals.append(_r(_ease_in(p)))
            auto.b_other.append(_r(0.6 + 0.4 * _ease_in(p)))
            auto.b_volume.append(_r(0.7 + 0.3 * _ease_in(p)))


# ── Echo Out: reverb tail on A ─────────────────────────────────────────────

def _build_echo_out(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    """
    A builds up echo/reverb as it fades, B clean fade-in.
    Echo ramps strongly on A creating a spacious tail.
    """
    for i in range(n):
        t = i / max(n - 1, 1)

        # A: fade out with heavy echo
        a_vol = _r(1.0 - _ease_in(t))
        echo = _r(_ease_in(t) * 0.9)
        auto.a_drums.append(_r(1.0 - t * 0.6))
        auto.a_bass.append(_r(1.0 - _ease_in(t) * 0.8))
        auto.a_vocals.append(_r(1.0 - t * 0.5))
        auto.a_other.append(_r(1.0 - t * 0.4))
        auto.a_volume.append(a_vol)
        auto.a_echo.append(echo)

        # B: clean entry, drums first
        b_p = max(0, (t - 0.15) / 0.85)
        auto.b_drums.append(_r(_ease_in(b_p)))
        auto.b_bass.append(_r(_ease_in(max(0, (t - 0.3) / 0.7))))
        auto.b_vocals.append(_r(_ease_in(max(0, (t - 0.4) / 0.6))))
        auto.b_other.append(_r(_ease_in(max(0, (t - 0.2) / 0.8))))
        auto.b_volume.append(_r(_ease_in(b_p)))


# ── Filter: hi-pass sweep A + lo-pass ramp B ──────────────────────────────

def _build_filter(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    """
    Simulates hi-pass filter sweep on A (kill bass → kill mids → thin highs)
    and lo-pass opening on B (muffled → full).
    """
    for i in range(n):
        t = i / max(n - 1, 1)

        # A: hi-pass sweep effect (lose bass first, then mids)
        auto.a_bass.append(_r(1.0 - _ease_in(min(t * 2, 1.0))))
        auto.a_drums.append(_r(1.0 - _ease_in(min(t * 1.5, 1.0)) * 0.7))
        auto.a_vocals.append(_r(1.0 - _ease_in(t) * 0.5))
        auto.a_other.append(_r(1.0 - _ease_in(t) * 0.3))
        auto.a_volume.append(_r(1.0 - t * 0.3))
        auto.a_echo.append(_r(t * 0.4))

        # B: lo-pass opening (drums/bass enter late, highs first)
        auto.b_other.append(_r(_ease_in(min(t * 1.5, 1.0))))
        auto.b_vocals.append(_r(_ease_in(max(0, (t - 0.2) / 0.8))))
        auto.b_drums.append(_r(_ease_in(max(0, (t - 0.3) / 0.7))))
        auto.b_bass.append(_r(_ease_in(max(0, (t - 0.5) / 0.5))))
        auto.b_volume.append(_r(_ease_in(min(t * 1.2, 1.0))))


# ── Cut: hard instant switch ───────────────────────────────────────────────

def _build_cut(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    """Hard cut at midpoint — minimal mixing time."""
    mid = n // 2
    for i in range(n):
        if i < mid:
            auto.a_drums.append(1.0); auto.a_bass.append(1.0)
            auto.a_vocals.append(1.0); auto.a_other.append(1.0)
            auto.a_volume.append(1.0); auto.a_echo.append(0.0)
            auto.b_drums.append(0.0); auto.b_bass.append(0.0)
            auto.b_vocals.append(0.0); auto.b_other.append(0.0)
            auto.b_volume.append(0.0)
        else:
            auto.a_drums.append(0.0); auto.a_bass.append(0.0)
            auto.a_vocals.append(0.0); auto.a_other.append(0.0)
            auto.a_volume.append(0.0); auto.a_echo.append(0.5)
            auto.b_drums.append(1.0); auto.b_bass.append(1.0)
            auto.b_vocals.append(1.0); auto.b_other.append(1.0)
            auto.b_volume.append(1.0)


# ── Slam: quick high-energy burst ─────────────────────────────────────────

def _build_slam(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    """
    Quick slam transition:
    1. Brief silence/filter sweep (builds tension)
    2. B hits hard at the drop
    Creates an energy burst effect popular in EDM/dance sets.
    """
    # Tension builds in first 40%, "drop" at 40%, then B dominates
    drop_point = int(n * 0.4)

    for i in range(n):
        if i < drop_point:
            # Build tension: A fades, everything quiets down
            p = i / max(drop_point, 1)
            auto.a_drums.append(_r(1.0 - _ease_in(p) * 0.9))
            auto.a_bass.append(_r(1.0 - _ease_in(p)))
            auto.a_vocals.append(_r(1.0 - _ease_in(p) * 0.7))
            auto.a_other.append(_r(1.0 - p * 0.5))
            auto.a_volume.append(_r(1.0 - _ease_in(p) * 0.7))
            auto.a_echo.append(_r(_ease_in(p) * 0.6))

            auto.b_drums.append(0.0); auto.b_bass.append(0.0)
            auto.b_vocals.append(0.0); auto.b_other.append(0.0)
            auto.b_volume.append(0.0)
        else:
            # Drop: B slams in at full energy
            remaining = n - drop_point
            p = (i - drop_point) / max(remaining, 1)

            auto.a_drums.append(0.0); auto.a_bass.append(0.0)
            auto.a_vocals.append(0.0); auto.a_other.append(0.0)
            auto.a_volume.append(0.0)
            auto.a_echo.append(_r(0.6 * (1 - p)))

            # B enters at ~90% immediately, then quickly to 100%
            entry = min(1.0, 0.9 + 0.1 * p)
            auto.b_drums.append(_r(entry))
            auto.b_bass.append(_r(entry))
            auto.b_vocals.append(_r(0.7 + 0.3 * _ease_in(p)))
            auto.b_other.append(_r(entry))
            auto.b_volume.append(_r(entry))


# ── Builder registry ───────────────────────────────────────────────────────

_BUILDERS = {
    "smooth": _build_smooth,
    "power": _build_power,
    "bass_swap": _build_bass_swap,
    "echo_out": _build_echo_out,
    "filter": _build_filter,
    "cut": _build_cut,
    "slam": _build_slam,
}


# ── Easing functions ───────────────────────────────────────────────────────

def _ease_in(t: float) -> float:
    return t * t

def _ease_out(t: float) -> float:
    return 1 - (1 - t) * (1 - t)

def _ease_in_out(t: float) -> float:
    if t < 0.5:
        return 2 * t * t
    return 1 - (-2 * t + 2) ** 2 / 2

def _r(v: float) -> float:
    return round(max(0.0, min(1.0, v)), 4)
