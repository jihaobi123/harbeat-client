"""Phase 3.2 — Stem envelope curves.

Each function takes progress p ∈ [0, 1] and returns a gain ∈ [0, 1].
The audio-engine evaluates these once per callback for each (deck, stem)
that has a curve in tr.stem_curves; the result is used as the per-stem mix gain.

Curves are designed so the SUM of paired prev+next on the same stem
stays close to 1.0 across [0, 1] — preventing perceived volume dips during
the crossfade. Pure linear pairs (linear_out + linear_in) sum to 1.0.
The break pairs (out_at_break + in_at_break) hand the stem off in a single
hard step at p=0.5, also summing to 1.0.

The engine falls back to {linear_out, linear_in} for any unknown name, so
forward-compatible curves like in_late / kick_then_in (Phase 3.3) won't crash
on a 3.2 engine — they'll just sound like a normal linear fade.
"""
from __future__ import annotations

import math


def _clip(p: float) -> float:
    return 0.0 if p < 0.0 else (1.0 if p > 1.0 else p)


def hold(p: float) -> float:
    return 1.0


def linear_out(p: float) -> float:
    return 1.0 - _clip(p)


def linear_in(p: float) -> float:
    return _clip(p)


def out_at_break(p: float) -> float:
    """1.0 until p=0.5, then 0.0. Used for prev bass on stem-swap rules."""
    return 1.0 if _clip(p) < 0.5 else 0.0


def in_at_break(p: float) -> float:
    """0.0 until p=0.5, then 1.0. Used for next bass on stem-swap rules."""
    return 0.0 if _clip(p) < 0.5 else 1.0


def equal_power_out(p: float) -> float:
    return math.cos(_clip(p) * math.pi / 2.0)


def equal_power_in(p: float) -> float:
    return math.sin(_clip(p) * math.pi / 2.0)


# Forward-compat names from Phase 3.3 — all alias to linear for now so the
# spec-side schema can land without engine changes. Phase 3.3 will replace
# these stubs with real shapes.
def in_late(p: float) -> float:
    """Phase 3.3 — vocal handoff. Stub: late linear ramp from p=0.4."""
    p = _clip(p)
    if p < 0.4:
        return 0.0
    return (p - 0.4) / 0.6


def hold_then_out(p: float) -> float:
    """Hold to p=0.5, then linear out — for drum-bridge rules."""
    p = _clip(p)
    if p < 0.5:
        return 1.0
    return 1.0 - (p - 0.5) / 0.5


_CURVES = {
    "hold": hold,
    "linear_out": linear_out,
    "linear_in": linear_in,
    "out_at_break": out_at_break,
    "in_at_break": in_at_break,
    "equal_power_out": equal_power_out,
    "equal_power_in": equal_power_in,
    "in_late": in_late,
    "hold_then_out": hold_then_out,
    # Phase 3.3 stubs — alias to linear until the real envelopes ship.
    "swell_then_out": linear_out,
    "kick_then_in": linear_in,
    "duck_then_in": linear_in,
    "pump": linear_in,
}


def evaluate(name: str, progress: float, *, fallback_in: bool = False) -> float:
    """Evaluate a curve by name, falling back to linear if unknown.

    fallback_in: when True the unknown-curve fallback is linear_in (use for
    next deck), else linear_out (prev deck).
    """
    fn = _CURVES.get(name)
    if fn is None:
        return linear_in(progress) if fallback_in else linear_out(progress)
    return float(fn(progress))
