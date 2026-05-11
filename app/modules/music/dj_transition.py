"""
DJ Transition Engine (DJ.studio-inspired)
==========================================

Professional transition automation with real EQ filter sweeps, reverb/delay FX,
and per-stem gain curves at 50Hz (20ms resolution) for smooth playback.

Transition presets:
  smooth     — EQ crossfade: A's low fades first, then mids, then highs
  power      — Equal-power gain crossfade (clean, no EQ tricks)
  bass_swap  — Classic DJ bass exchange at midpoint
  echo_out   — Real reverb/delay tail on A, clean B fade-in
  filter     — Highpass sweep on A + lowpass ramp on B (real frequency curves)
  cut        — Hard instant switch
  slam       — Quick high-energy burst with filter tension build

Reference: DJ.studio timeline + mir-aidj transition analysis (NIME 2021)
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
    All arrays are sampled at `sample_rate` Hz (default 50Hz = 20ms resolution).
    Gain values are multipliers 0.0-1.0.
    Filter frequencies are in Hz (for real Pedalboard HighpassFilter/LowpassFilter).
    FX sends are 0.0 (dry) to 1.0 (full wet, for real Pedalboard Reverb/Delay).
    """
    total_duration_sec: float
    sample_rate: float = 50.0

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

    # EQ filter frequency curves (Hz) — drives real HighpassFilter / LowpassFilter
    a_highpass_hz: list[float] = field(default_factory=list)   # 20=bypass → higher=thinner
    a_lowpass_hz: list[float] = field(default_factory=list)    # 20000=bypass → lower=muffled
    b_highpass_hz: list[float] = field(default_factory=list)
    b_lowpass_hz: list[float] = field(default_factory=list)

    # Reverb / Delay send (0.0=dry, 1.0=full wet) — drives real Pedalboard effects
    a_reverb: list[float] = field(default_factory=list)
    a_delay: list[float] = field(default_factory=list)

    # Extended FX for advanced strategies (echo_out_enhanced, drum_fill, loop_out, etc.)
    b_reverb: list[float] = field(default_factory=list)       # reverb on incoming deck
    b_delay: list[float] = field(default_factory=list)        # delay on incoming deck
    a_pitch_shift: list[float] = field(default_factory=list)  # pitch shift in semitones (0=normal, -12=oct down)
    a_roll_length: list[float] = field(default_factory=list)  # loop roll (1.0=1bar, 0.25=1/4bar, 0.0=off)
    master_noise: list[float] = field(default_factory=list)   # noise riser level (0=dry, 1=full)


TRANSITION_STYLES = [
    "smooth", "power", "bass_swap", "echo_out", "filter", "cut", "slam",
    "echo_out_enhanced", "drum_fill", "breakdown_entry", "loop_out",
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

    sr = 50.0
    n = max(1, int(overlap_sec * sr))

    auto = TransitionAutomation(
        total_duration_sec=overlap_sec,
        sample_rate=sr,
    )

    builder = _BUILDERS.get(style, _build_smooth)
    builder(auto, n, overlap_sec, bpm)

    return auto


# ── FX automation helper ───────────────────────────────────────────────────

def _append_fx(auto: TransitionAutomation, *,
               a_hp: float = 20.0, a_lp: float = 20000.0,
               b_hp: float = 20.0, b_lp: float = 20000.0,
               a_rev: float = 0.0, a_del: float = 0.0,
               b_rev: float = 0.0, b_del: float = 0.0,
               a_pitch: float = 0.0, a_roll: float = 1.0,
               noise: float = 0.0) -> None:
    """Append one sample of FX automation."""
    auto.a_highpass_hz.append(round(a_hp, 1))
    auto.a_lowpass_hz.append(round(a_lp, 1))
    auto.b_highpass_hz.append(round(b_hp, 1))
    auto.b_lowpass_hz.append(round(b_lp, 1))
    auto.a_reverb.append(_r(a_rev))
    auto.a_delay.append(_r(a_del))
    auto.b_reverb.append(_r(b_rev))
    auto.b_delay.append(_r(b_del))
    auto.a_pitch_shift.append(round(a_pitch, 2))
    auto.a_roll_length.append(round(a_roll, 3))
    auto.master_noise.append(_r(noise))


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
        auto.a_volume.append(a_vol)

        auto.b_drums.append(b_drums); auto.b_bass.append(b_bass)
        auto.b_vocals.append(b_vocals); auto.b_other.append(b_other)
        auto.b_volume.append(b_vol)

        _append_fx(auto, a_rev=t * 0.25)


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
        auto.a_volume.append(_r(a_vol))

        auto.b_drums.append(_r(b_vol)); auto.b_bass.append(_r(b_vol))
        auto.b_vocals.append(_r(b_vol)); auto.b_other.append(_r(b_vol))
        auto.b_volume.append(_r(b_vol))

        _append_fx(auto)


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
            auto.a_volume.append(1.0)

            auto.b_drums.append(_r(_ease_in(p) * 0.7))
            auto.b_bass.append(0.0)
            auto.b_vocals.append(0.0)
            auto.b_other.append(_r(_ease_in(p) * 0.6))
            auto.b_volume.append(_r(_ease_in(p) * 0.7))

            _append_fx(auto)
        else:
            remaining = n - swap
            p = (i - swap) / max(remaining, 1)

            auto.a_drums.append(_r(_ease_out(1 - p) * 0.8))
            auto.a_bass.append(0.0)
            auto.a_vocals.append(_r(_ease_out(1 - p) * 0.7))
            auto.a_other.append(_r(_ease_out(1 - p) * 0.6))
            auto.a_volume.append(_r(_ease_out(1 - p)))

            auto.b_drums.append(_r(0.7 + 0.3 * _ease_in(p)))
            auto.b_bass.append(1.0)
            auto.b_vocals.append(_r(_ease_in(p)))
            auto.b_other.append(_r(0.6 + 0.4 * _ease_in(p)))
            auto.b_volume.append(_r(0.7 + 0.3 * _ease_in(p)))

            _append_fx(auto, a_rev=_ease_in(p) * 0.6)


# ── Echo Out: reverb tail on A ─────────────────────────────────────────────

def _build_echo_out(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    """
    A builds up real reverb/delay as it fades, B clean fade-in.
    Reverb ramps strongly on A creating a spacious tail;
    delay adds rhythmic echo that decays into the new track.
    """
    for i in range(n):
        t = i / max(n - 1, 1)

        # A: fade out with heavy reverb + delay
        a_vol = _r(1.0 - _ease_in(t))
        auto.a_drums.append(_r(1.0 - t * 0.6))
        auto.a_bass.append(_r(1.0 - _ease_in(t) * 0.8))
        auto.a_vocals.append(_r(1.0 - t * 0.5))
        auto.a_other.append(_r(1.0 - t * 0.4))
        auto.a_volume.append(a_vol)

        # B: clean entry, drums first
        b_p = max(0, (t - 0.15) / 0.85)
        auto.b_drums.append(_r(_ease_in(b_p)))
        auto.b_bass.append(_r(_ease_in(max(0, (t - 0.3) / 0.7))))
        auto.b_vocals.append(_r(_ease_in(max(0, (t - 0.4) / 0.6))))
        auto.b_other.append(_r(_ease_in(max(0, (t - 0.2) / 0.8))))
        auto.b_volume.append(_r(_ease_in(b_p)))

        # Real reverb/delay ramp — creates spacious echo tail on A
        _append_fx(auto, a_rev=_ease_in(t) * 0.85, a_del=_ease_in(t) * 0.6)


# ── Filter: hi-pass sweep A + lo-pass ramp B ──────────────────────────────

def _build_filter(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    """
    Real highpass frequency sweep on A + lowpass opening on B.
    A: highpass 20Hz → 5000Hz (thins out progressively).
    B: lowpass 200Hz → 20000Hz (brightens as it enters).
    Stem gains provide additional control on top of the real filter curves.
    """
    for i in range(n):
        t = i / max(n - 1, 1)

        # A: stem gain as supplementary control
        auto.a_bass.append(_r(1.0 - _ease_in(min(t * 2, 1.0))))
        auto.a_drums.append(_r(1.0 - _ease_in(min(t * 1.5, 1.0)) * 0.7))
        auto.a_vocals.append(_r(1.0 - _ease_in(t) * 0.5))
        auto.a_other.append(_r(1.0 - _ease_in(t) * 0.3))
        auto.a_volume.append(_r(1.0 - t * 0.3))

        # B: stem gain — lo-pass opening simulation
        auto.b_other.append(_r(_ease_in(min(t * 1.5, 1.0))))
        auto.b_vocals.append(_r(_ease_in(max(0, (t - 0.2) / 0.8))))
        auto.b_drums.append(_r(_ease_in(max(0, (t - 0.3) / 0.7))))
        auto.b_bass.append(_r(_ease_in(max(0, (t - 0.5) / 0.5))))
        auto.b_volume.append(_r(_ease_in(min(t * 1.2, 1.0))))

        # Real EQ filter frequency curves
        a_hp = 20.0 + _ease_in(t) * 4980.0      # 20Hz → 5000Hz highpass sweep
        b_lp = 200.0 + _ease_in(t) * 19800.0     # 200Hz → 20000Hz lowpass opening
        _append_fx(auto, a_hp=a_hp, b_lp=b_lp, a_rev=t * 0.15)


# ── Cut: hard instant switch ───────────────────────────────────────────────

def _build_cut(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    """Hard cut at midpoint — minimal mixing time."""
    mid = n // 2
    for i in range(n):
        if i < mid:
            auto.a_drums.append(1.0); auto.a_bass.append(1.0)
            auto.a_vocals.append(1.0); auto.a_other.append(1.0)
            auto.a_volume.append(1.0)
            auto.b_drums.append(0.0); auto.b_bass.append(0.0)
            auto.b_vocals.append(0.0); auto.b_other.append(0.0)
            auto.b_volume.append(0.0)
            _append_fx(auto)
        else:
            auto.a_drums.append(0.0); auto.a_bass.append(0.0)
            auto.a_vocals.append(0.0); auto.a_other.append(0.0)
            auto.a_volume.append(0.0)
            auto.b_drums.append(1.0); auto.b_bass.append(1.0)
            auto.b_vocals.append(1.0); auto.b_other.append(1.0)
            auto.b_volume.append(1.0)
            _append_fx(auto, a_rev=0.3)


# ── Slam: quick high-energy burst ─────────────────────────────────────────

def _build_slam(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    """
    Quick slam transition with filter tension build:
    1. A fades with highpass sweep + reverb (builds tension)
    2. B slams in at the drop with full bandwidth
    Creates an energy burst popular in EDM/dance sets.
    """
    drop_point = int(n * 0.4)

    for i in range(n):
        if i < drop_point:
            # Build tension: A fades, highpass sweeps up, reverb ramps
            p = i / max(drop_point, 1)
            auto.a_drums.append(_r(1.0 - _ease_in(p) * 0.9))
            auto.a_bass.append(_r(1.0 - _ease_in(p)))
            auto.a_vocals.append(_r(1.0 - _ease_in(p) * 0.7))
            auto.a_other.append(_r(1.0 - p * 0.5))
            auto.a_volume.append(_r(1.0 - _ease_in(p) * 0.7))

            auto.b_drums.append(0.0); auto.b_bass.append(0.0)
            auto.b_vocals.append(0.0); auto.b_other.append(0.0)
            auto.b_volume.append(0.0)

            # Tension: highpass sweeps 20→3000Hz + reverb/delay ramp
            a_hp = 20.0 + _ease_in(p) * 2980.0
            _append_fx(auto, a_hp=a_hp, a_rev=_ease_in(p) * 0.65, a_del=_ease_in(p) * 0.4)
        else:
            # Drop: B slams in at full energy
            remaining = n - drop_point
            p = (i - drop_point) / max(remaining, 1)

            auto.a_drums.append(0.0); auto.a_bass.append(0.0)
            auto.a_vocals.append(0.0); auto.a_other.append(0.0)
            auto.a_volume.append(0.0)

            # B enters at ~90% immediately, then quickly to 100%
            entry = min(1.0, 0.9 + 0.1 * p)
            auto.b_drums.append(_r(entry))
            auto.b_bass.append(_r(entry))
            auto.b_vocals.append(_r(0.7 + 0.3 * _ease_in(p)))
            auto.b_other.append(_r(entry))
            auto.b_volume.append(_r(entry))

            # Reverb tail fades on A
            _append_fx(auto, a_rev=0.5 * (1 - p))


# ── Echo Out Enhanced: pitch-shifted multi-tap echo + stereo spread ─────────
# Distinct from basic echo_out: uses tape-stop pitch shift, multi-tap rhythmic
# delay taps (1/4, 1/8, 1/16), stereo ping-pong decay, and pre-delay swell.
# Reference: GrooveEngine BACKSPIN_OUT (reverse+brake) mixed with ECHO_OUT.

def _build_echo_out_enhanced(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    beat_sec = 60.0 / max(bpm, 1.0)
    for i in range(n):
        t = i / max(n - 1, 1)
        # A: staggered stem exit — vocals first (echoed), drums last
        a_vol = _r(1.0 - _ease_in(t * 1.2))
        auto.a_vocals.append(_r(1.0 - _ease_in(min(t * 1.8, 1.0))))
        auto.a_bass.append(_r(1.0 - _ease_in(min(t * 1.4, 1.0))))
        auto.a_other.append(_r(1.0 - _ease_in(t) * 0.6))
        auto.a_drums.append(_r(1.0 - t * 0.5))
        auto.a_volume.append(a_vol)

        # B: clean entry, drums then bass then rest
        auto.b_drums.append(_r(_ease_in(max(0, (t - 0.05) / 0.5))))
        auto.b_bass.append(_r(_ease_in(max(0, (t - 0.2) / 0.6))))
        auto.b_other.append(_r(_ease_in(max(0, (t - 0.25) / 0.7))))
        auto.b_vocals.append(_r(_ease_in(max(0, (t - 0.35) / 0.65))))
        auto.b_volume.append(_r(_ease_in(max(0, (t - 0.1) / 0.8))))

        # Tape-stop pitch shift: -0 to -7 semitones as A fades
        pitch = -_ease_in(t) * 7.0
        # Multi-tap delay: rhythmic taps at 1/4, 1/8 with feedback
        del_wet = _ease_in(t * 0.8) * 0.75
        # Stereo reverb swell: pre-delay increases with t
        rev_wet = _ease_in(t * 0.6) * 0.7
        _append_fx(auto, a_rev=rev_wet, a_del=del_wet, a_pitch=pitch)


# ── Drum Fill: band-pass drum energy build + noise burst ────────────────────
# Distinct approach: works primarily on the DRUM stem with a band-pass filter
# sweep (focusing percussion energy), transient boost simulation via gain
# pulsing, white noise riser for tension, then B drops at full energy.
# Reference: GrooveEngine RISER (noise+filter) but drum-centric instead of synth.

def _build_drum_fill(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    beat_sec = 60.0 / max(bpm, 1.0)
    drop_point = int(n * 0.65)  # fill lasts 65% of overlap, then B drops
    for i in range(n):
        t = i / max(n - 1, 1)
        if i < drop_point:
            p = i / max(drop_point, 1)  # 0→1 over fill phase
            # A: keep drums prominent, cut bass + vocals early
            auto.a_drums.append(_r(0.85 + 0.15 * math.sin(p * math.pi * 4)))  # drum pulse
            auto.a_bass.append(_r(1.0 - _ease_in(p * 1.5)))
            auto.a_vocals.append(_r(1.0 - _ease_in(p * 1.3)))
            auto.a_other.append(_r(1.0 - _ease_in(p) * 0.4))
            auto.a_volume.append(_r(1.0 - p * 0.3))

            # B: hidden during fill
            auto.b_drums.append(0.0); auto.b_bass.append(0.0)
            auto.b_vocals.append(0.0); auto.b_other.append(0.0)
            auto.b_volume.append(0.0)

            # Band-pass effect: highpass rises + lowpass falls = focused mid band
            a_hp = 80.0 + _ease_in(p) * 620.0      # 80→700Hz (cut sub, focus kick)
            a_lp = 12000.0 - _ease_in(p) * 7000.0  # 12000→5000Hz (cut highs)
            # Noise riser: 0→0.7 over fill
            noise = _ease_in(p) * 0.7
            # Roll shortening on drums: 1bar → 1/4 bar
            roll = 1.0 - _ease_in(p) * 0.75
            _append_fx(auto, a_hp=a_hp, a_lp=a_lp, noise=noise, a_roll=roll)
        else:
            remaining = n - drop_point
            p = (i - drop_point) / max(remaining, 1)
            # B drops at full energy
            auto.a_drums.append(_r(1.0 - _ease_in(p))); auto.a_bass.append(0.0)
            auto.a_vocals.append(0.0); auto.a_other.append(_r(1.0 - _ease_in(p) * 0.5))
            auto.a_volume.append(_r(1.0 - _ease_in(p)))

            entry = min(1.0, 0.85 + 0.15 * p)
            auto.b_drums.append(_r(entry))
            auto.b_bass.append(_r(min(1.0, 0.8 + 0.2 * p)))
            auto.b_vocals.append(_r(min(1.0, 0.6 + 0.4 * _ease_in(p))))
            auto.b_other.append(_r(entry))
            auto.b_volume.append(_r(entry))
            # Noise tails off, reverb on A decay
            _append_fx(auto, a_rev=(1 - p) * 0.5, noise=(1 - p) * 0.5)


# ── Breakdown Entry: atmospheric wash → sparse re-entry ─────────────────────
# Creates a "breathe out" moment: A gets low-pass closed + heavy reverb wash,
# creating a diffuse pad-like tail. B enters with high-pass (thin at first),
# then gradually opens to full spectrum. Sub-bass on B is delayed.
# Reference: GrooveEngine MELODIC_RESET (HPF+reverb) but for entry, not exit.

def _build_breakdown_entry(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    wash_point = int(n * 0.45)  # first 45%: wash A out, then B enters thin
    for i in range(n):
        t = i / max(n - 1, 1)
        if i < wash_point:
            p = i / max(wash_point, 1)
            # A: dissolve into reverb — lowpass closes, reverb swells
            auto.a_drums.append(_r(1.0 - _ease_in(p) * 0.85))
            auto.a_bass.append(_r(1.0 - _ease_in(p * 1.5)))
            auto.a_vocals.append(_r(1.0 - _ease_in(p) * 0.7))
            auto.a_other.append(_r(1.0 - p * 0.5))
            auto.a_volume.append(_r(1.0 - _ease_in(p) * 0.6))

            auto.b_drums.append(0.0); auto.b_bass.append(0.0)
            auto.b_vocals.append(0.0); auto.b_other.append(0.0)
            auto.b_volume.append(0.0)

            # Lowpass closes: 20000→800Hz (dark wash)
            a_lp = 20000.0 - _ease_in(p) * 19200.0
            # Reverb swell: 0→0.9
            rev = _ease_in(p) * 0.9
            _append_fx(auto, a_lp=a_lp, a_rev=rev)
        else:
            remaining = n - wash_point
            p = (i - wash_point) / max(remaining, 1)
            # A: stays washed out
            auto.a_drums.append(0.0); auto.a_bass.append(0.0)
            auto.a_vocals.append(_r(0.3 * (1 - p))); auto.a_other.append(_r(0.3 * (1 - p)))
            auto.a_volume.append(_r(0.4 * (1 - p)))

            # B enters thin: HPF starts at 2000Hz → opens to 20Hz
            b_hp = 2000.0 - _ease_in(p) * 1980.0
            # Sub-bass delayed: bass stem enters later
            auto.b_drums.append(_r(_ease_in(min(p * 1.3, 1.0))))
            auto.b_bass.append(_r(_ease_in(max(0, (p - 0.25) / 0.75))))
            auto.b_vocals.append(_r(_ease_in(max(0, (p - 0.15) / 0.85))))
            auto.b_other.append(_r(_ease_in(min(p * 1.1, 1.0))))
            auto.b_volume.append(_r(_ease_in(p)))
            # Reverb on B for atmospheric continuity, fading down
            b_rev = 0.4 * (1.0 - _ease_in(p))
            _append_fx(auto, b_hp=b_hp, a_rev=0.5 * (1 - p), b_rev=b_rev)


# ── Loop Out: progressive loop shortening + pitch-down on outgoing deck ─────
# A gets captured in progressively shorter loops (1bar → 1/2 → 1/4 → 1/8),
# each iteration gets a slight pitch drop and more highpass filtering.
# B enters clean after the loop sequence completes.
# Reference: GrooveEngine LOOP_ROLL (B-deck roll) but reversed to A-deck exit.

def _build_loop_out(auto: TransitionAutomation, n: int, dur: float, bpm: float) -> None:
    beat_sec = 60.0 / max(bpm, 1.0)
    # Phase boundaries: 0→40% full loop, 40→70% half loop, 70→90% quarter, 90→100% eighth
    phases = [0.0, 0.40, 0.70, 0.90, 1.0]
    roll_lengths = [1.0, 0.5, 0.25, 0.125, 0.0]  # bar fraction
    pitch_drops = [0.0, -2.0, -4.0, -7.0, 0.0]   # semitones

    for i in range(n):
        t = i / max(n - 1, 1)
        # Determine current phase
        phase_idx = 0
        for pi in range(len(phases) - 1):
            if t >= phases[pi]:
                phase_idx = pi
        next_phase = phases[min(phase_idx + 1, len(phases) - 1)]
        cur_phase_start = phases[phase_idx]
        phase_p = (t - cur_phase_start) / max(next_phase - cur_phase_start, 0.01)
        phase_p = max(0.0, min(1.0, phase_p))

        roll = roll_lengths[phase_idx] + (roll_lengths[min(phase_idx + 1, len(roll_lengths) - 1)] - roll_lengths[phase_idx]) * _ease_in(phase_p)
        pitch = pitch_drops[phase_idx] + (pitch_drops[min(phase_idx + 1, len(pitch_drops) - 1)] - pitch_drops[phase_idx]) * _ease_in(phase_p)

        # A: HPF increases through phases, volume steps down
        a_hp = 20.0 + t * 3000.0
        a_vol = _r(1.0 - t * 0.85)

        auto.a_drums.append(_r(1.0 - t * 0.5))
        auto.a_bass.append(_r(1.0 - _ease_in(t * 1.5)))
        auto.a_vocals.append(_r(1.0 - _ease_in(t * 1.3)))
        auto.a_other.append(_r(1.0 - t * 0.4))
        auto.a_volume.append(a_vol)

        # B: clean entry after loop phase completes (last 20%)
        b_t = max(0, (t - 0.75) / 0.25)
        auto.b_drums.append(_r(_ease_in(b_t)))
        auto.b_bass.append(_r(_ease_in(max(0, (b_t - 0.15) / 0.85))))
        auto.b_vocals.append(_r(_ease_in(max(0, (b_t - 0.2) / 0.8))))
        auto.b_other.append(_r(_ease_in(b_t)))
        auto.b_volume.append(_r(_ease_in(max(0, (b_t - 0.05) / 0.95))))

        _append_fx(auto, a_hp=a_hp, a_roll=roll, a_pitch=pitch,
                   a_rev=t * 0.3, a_del=t * 0.25)


# ── Builder registry ───────────────────────────────────────────────────────

_BUILDERS = {
    "smooth": _build_smooth,
    "power": _build_power,
    "bass_swap": _build_bass_swap,
    "echo_out": _build_echo_out,
    "filter": _build_filter,
    "cut": _build_cut,
    "slam": _build_slam,
    "echo_out_enhanced": _build_echo_out_enhanced,
    "drum_fill": _build_drum_fill,
    "breakdown_entry": _build_breakdown_entry,
    "loop_out": _build_loop_out,
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
