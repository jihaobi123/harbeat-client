"""
DJ Transition Engine - 移植自 harbeat-client
专业的 DJ 风格转场引擎
"""
import math

def ease_in(t: float) -> float:
    return t * t

def ease_out(t: float) -> float:
    return 1 - (1 - t) * (1 - t)

def ease_in_out(t: float) -> float:
    if t < 0.5:
        return 2 * t * t
    return 1 - (-2 * t + 2) ** 2 / 2

def _r(v: float) -> float:
    """Round and clamp to 0-1"""
    return round(max(0.0, min(1.0, v)), 4)

def _smooth_fade(t: float, start: float, end: float) -> float:
    """Fade out from 1→0 between start and end"""
    if t <= start:
        return 1.0
    if t >= end:
        return 0.0
    p = (t - start) / (end - start)
    return 1.0 - ease_in_out(p)

def _smooth_entry(t: float, start: float, end: float) -> float:
    """Fade in from 0→1 between start and end"""
    if t <= start:
        return 0.0
    if t >= end:
        return 1.0
    p = (t - start) / (end - start)
    return ease_in_out(p)

# ── Smooth: EQ crossfade ──
def build_smooth(progress: float) -> tuple[dict, dict]:
    """
    DJ.studio-style smooth EQ crossfade.
    A fades out: bass first, then vocals/other, drums last
    B fades in: drums first, then other/vocals, bass last
    """
    t = max(0.0, min(1.0, progress))

    # A fading out: staggered EQ departure
    a_bass    = _r(_smooth_fade(t, 0.0, 0.4))
    a_vocals  = _r(_smooth_fade(t, 0.15, 0.6))
    a_other   = _r(_smooth_fade(t, 0.2, 0.7))
    a_drums   = _r(_smooth_fade(t, 0.3, 0.85))

    # B fading in: staggered EQ entry
    b_drums   = _r(_smooth_entry(t, 0.0, 0.5))
    b_other   = _r(_smooth_entry(t, 0.15, 0.65))
    b_vocals  = _r(_smooth_entry(t, 0.3, 0.8))
    b_bass    = _r(_smooth_entry(t, 0.4, 0.9))

    return (
        {"vocals": a_vocals, "drums": a_drums, "bass": a_bass, "other": a_other},
        {"vocals": b_vocals, "drums": b_drums, "bass": b_bass, "other": b_other}
    )

# ── Power: equal-power crossfade ──
def build_power(progress: float) -> tuple[dict, dict]:
    """Classic equal-power crossfade"""
    t = max(0.0, min(1.0, progress))
    a_vol = math.cos(t * math.pi / 2)
    b_vol = math.sin(t * math.pi / 2)

    return (
        {"vocals": a_vol, "drums": a_vol, "bass": a_vol, "other": a_vol},
        {"vocals": b_vol, "drums": b_vol, "bass": b_vol, "other": b_vol}
    )

# ── Bass Swap: classic DJ bass exchange ──
def build_bass_swap(progress: float) -> tuple[dict, dict]:
    """
    Classic bass swap at midpoint:
    Phase 1: A full, B enters without bass/vocals
    Swap: A bass cuts, B bass restores
    Phase 2: A fades with echo, B takes over
    """
    t = max(0.0, min(1.0, progress))

    if t < 0.5:
        # Phase 1: before swap
        p = t / 0.5
        return (
            {"vocals": 1.0, "drums": 1.0, "bass": 1.0, "other": 1.0},
            {"vocals": 0.0, "drums": _r(ease_in(p) * 0.7), "bass": 0.0, "other": _r(ease_in(p) * 0.6)}
        )
    else:
        # Phase 2: after swap
        p = (t - 0.5) / 0.5
        return (
            {"vocals": _r(ease_out(1 - p) * 0.7), "drums": _r(ease_out(1 - p) * 0.8), "bass": 0.0, "other": _r(ease_out(1 - p) * 0.6)},
            {"vocals": _r(ease_in(p)), "drums": _r(0.7 + 0.3 * ease_in(p)), "bass": 1.0, "other": _r(0.6 + 0.4 * ease_in(p))}
        )

# ── Echo Out: reverb tail on A ──
def build_echo_out(progress: float) -> tuple[dict, dict]:
    """A builds up echo as it fades, B clean fade-in"""
    t = max(0.0, min(1.0, progress))

    # A: fade out with echo
    a_drums = _r(1.0 - t * 0.6)
    a_bass = _r(1.0 - ease_in(t) * 0.8)
    a_vocals = _r(1.0 - t * 0.5)
    a_other = _r(1.0 - t * 0.4)

    # B: clean entry, drums first
    b_p = max(0, (t - 0.15) / 0.85)
    b_drums = _r(ease_in(b_p))
    b_bass = _r(ease_in(max(0, (t - 0.3) / 0.7)))
    b_vocals = _r(ease_in(max(0, (t - 0.4) / 0.6)))
    b_other = _r(ease_in(max(0, (t - 0.2) / 0.8)))

    return (
        {"vocals": a_vocals, "drums": a_drums, "bass": a_bass, "other": a_other},
        {"vocals": b_vocals, "drums": b_drums, "bass": b_bass, "other": b_other}
    )

# ── Filter: hi-pass sweep A + lo-pass ramp B ──
def build_filter(progress: float) -> tuple[dict, dict]:
    """
    Hi-pass filter sweep on A (kill bass → thin highs)
    Lo-pass opening on B (muffled → full)
    """
    t = max(0.0, min(1.0, progress))

    # A: hi-pass sweep (lose bass first, then mids)
    a_bass = _r(1.0 - ease_in(min(t * 2, 1.0)))
    a_drums = _r(1.0 - ease_in(min(t * 1.5, 1.0)) * 0.7)
    a_vocals = _r(1.0 - ease_in(t) * 0.5)
    a_other = _r(1.0 - ease_in(t) * 0.3)

    # B: lo-pass opening (highs first, bass late)
    b_other = _r(ease_in(min(t * 1.5, 1.0)))
    b_vocals = _r(ease_in(max(0, (t - 0.2) / 0.8)))
    b_drums = _r(ease_in(max(0, (t - 0.3) / 0.7)))
    b_bass = _r(ease_in(max(0, (t - 0.5) / 0.5)))

    return (
        {"vocals": a_vocals, "drums": a_drums, "bass": a_bass, "other": a_other},
        {"vocals": b_vocals, "drums": b_drums, "bass": b_bass, "other": b_other}
    )

# ── Slam: quick high-energy burst ──
def build_slam(progress: float) -> tuple[dict, dict]:
    """
    Quick slam transition:
    1. Brief tension build (0-40%)
    2. B hits hard at drop (40%)
    """
    t = max(0.0, min(1.0, progress))

    if t < 0.4:
        # Build tension: A fades, everything quiets
        p = t / 0.4
        return (
            {"vocals": _r(1.0 - ease_in(p) * 0.7), "drums": _r(1.0 - ease_in(p) * 0.9), "bass": _r(1.0 - ease_in(p)), "other": _r(1.0 - p * 0.5)},
            {"vocals": 0.0, "drums": 0.0, "bass": 0.0, "other": 0.0}
        )
    else:
        # Drop: B slams in at full energy
        p = (t - 0.4) / 0.6
        entry = min(1.0, 0.9 + 0.1 * p)
        return (
            {"vocals": 0.0, "drums": 0.0, "bass": 0.0, "other": 0.0},
            {"vocals": _r(0.7 + 0.3 * ease_in(p)), "drums": _r(entry), "bass": _r(entry), "other": _r(entry)}
        )

# ── Builder registry ──
BUILDERS = {
    "smooth": build_smooth,
    "power": build_power,
    "blend": build_power,  # blend = power
    "bass_swap": build_bass_swap,
    "echo_out": build_echo_out,
    "echo_freeze": build_echo_out,  # echo_freeze = echo_out
    "filter": build_filter,
    "slam": build_slam,
}

def get_transition_envelopes(style: str, progress: float) -> tuple[dict, dict]:
    """
    Get stem envelopes for a transition style at given progress.
    Returns (a_gains, b_gains) where each is {stem: gain}
    """
    builder = BUILDERS.get(style, build_power)
    return builder(progress)
