"""Mixing rules.

Two catalogs of transition recipes:

  ANALYZED_TRANSITIONS  (11): rich rules that use BPM, key, phrase boundaries,
                              downbeats, stems. Picked automatically by the
                              transition planner; can also be forced.

  RAW_TRANSITIONS       (7):  fallback rules for songs with no analysis
                              (no BPM/beats). They rely only on a target
                              cross-fade window and a tail-roll-off / head-fade.

Each rule has:
  key                 unique id
  label_zh            Chinese label for UI
  needs_analysis      bool — whether both songs must be analyzed
  preferred_when      callable(prev_song, next_song) -> float [0..1] — fitness
  apply               callable(prev_song, next_song, cursor_sec) -> TransitionSpec
                      returns the concrete parameters audio-engine will execute.

TransitionSpec is a plain dict (kept serialisable) with:
  type           one of "cross_fade", "cut", "echo_out", "loop_roll", ...
  duration_sec   total transition duration
  start_in_prev  where in prev to start the transition
  start_in_next  where in next the new track enters (may be 0 or a cue)
  eq_curve       optional 3-band EQ automation
  fx             optional list of inline FX (filter sweep, reverb tail, etc.)
"""
from __future__ import annotations

from typing import Callable

from app.modules.dj_control import transition_strategy


def _safe(val, default):
    return val if val is not None else default


def _phrase_boundary_after(song, t: float) -> float | None:
    pm = list(getattr(song, "phrase_map", []) or [])
    for ph in pm:
        boundary = ph.get("start", ph.get("time"))
        if boundary is not None and boundary > t + 1.0:
            return float(boundary)
    return None


def _next_downbeat(song, t: float) -> float | None:
    for db in getattr(song, "downbeats", []) or []:
        if db > t + 0.2:
            return float(db)
    return None


# --------------------------------------------------------------------------- #
# Phase 3.1 — stem_curves dispatch
#
# Each rule attaches a `stem_curves` dict the audio-engine consults when both
# prev and next decks have all 4 stems loaded. Format:
#
#   {"prev": {<stem>: <curve>, ...},
#    "next": {<stem>: <curve>, ...}}
#
# Curve names the engine will implement in Phase 3.2 / 3.3:
#   hold           — full level the whole crossfade (no fade)
#   linear_out     — 1.0 → 0.0 linear over [0, 1]
#   linear_in      — 0.0 → 1.0 linear over [0, 1]
#   out_at_break   — 1.0 hold to 0.5, then 0.0 (hard low cut at midpoint)
#   in_at_break    — 0.0 hold to 0.5, then 1.0 (hard low rise at midpoint)
#
# Curves only used in 3.3 (defined here for forward compatibility — engine
# falls back to linear_in/out if not yet implemented):
#   in_late, hold_then_out, swell_then_out, kick_then_in, duck_then_in, pump
#
# When stems are not loaded, audio-engine ignores stem_curves and follows the
# original style/eq path. This makes 3.1 a zero-risk metadata-only change.
# --------------------------------------------------------------------------- #
_STEM_CURVES: dict[str, dict] = {
    "harmonic_blend": {
        "prev": {"vocals": "linear_out", "drums": "linear_out", "bass": "linear_out", "other": "linear_out"},
        "next": {"vocals": "in_late",    "drums": "linear_in",  "bass": "linear_in",  "other": "linear_in"},
    },
    # bass swap is the headline behaviour: low frequencies switch instantly
    # at the bar midpoint instead of summing two basslines = mud.
    "eq_swap_4bar": {
        "prev": {"vocals": "linear_out", "drums": "linear_out", "bass": "out_at_break", "other": "linear_out"},
        "next": {"vocals": "linear_in",  "drums": "linear_in",  "bass": "in_at_break",  "other": "linear_in"},
    },
    "filter_sweep_high": {
        "prev": {"vocals": "linear_out", "drums": "linear_out", "bass": "linear_out",   "other": "linear_out"},
        "next": {"vocals": "linear_in",  "drums": "linear_in",  "bass": "linear_in",    "other": "linear_in"},
    },
    "drop_swap": {
        "prev": {"vocals": "linear_out", "drums": "linear_out", "bass": "out_at_break", "other": "linear_out"},
        "next": {"vocals": "linear_in",  "drums": "linear_in",  "bass": "in_at_break",  "other": "linear_in"},
    },
    "echo_tail": {
        "prev": {"vocals": "linear_out", "drums": "linear_out",    "bass": "linear_out",   "other": "linear_out"},
        "next": {"vocals": "linear_in",  "drums": "linear_in",     "bass": "linear_in",    "other": "linear_in"},
    },
    "loop_roll": {
        "prev": {"vocals": "linear_out", "drums": "hold_then_out", "bass": "linear_out",   "other": "linear_out"},
        "next": {"vocals": "linear_in",  "drums": "linear_in",     "bass": "linear_in",    "other": "linear_in"},
    },
    "spin_back": {
        "prev": {"vocals": "linear_out", "drums": "linear_out",    "bass": "linear_out",   "other": "linear_out"},
        "next": {"vocals": "linear_in",  "drums": "linear_in",     "bass": "linear_in",    "other": "linear_in"},
    },
    # drum_only_bridge is the second stem-aware highlight: prev's drums hold
    # a bar while everything else exits, then next's drums + bass come in
    # underneath while next's vocal waits.
    "drum_only_bridge": {
        "prev": {"vocals": "linear_out", "drums": "hold",          "bass": "linear_out",   "other": "linear_out"},
        "next": {"vocals": "in_late",    "drums": "linear_in",     "bass": "linear_in",    "other": "linear_in"},
    },
    "key_lift": {
        "prev": {"vocals": "linear_out", "drums": "linear_out",    "bass": "linear_out",   "other": "linear_out"},
        "next": {"vocals": "linear_in",  "drums": "linear_in",     "bass": "linear_in",    "other": "linear_in"},
    },
    "reverb_throw": {
        "prev": {"vocals": "linear_out", "drums": "linear_out",    "bass": "linear_out",   "other": "linear_out"},
        "next": {"vocals": "linear_in",  "drums": "linear_in",     "bass": "linear_in",    "other": "linear_in"},
    },
    # smash cut — hard swap, no real stem fades but populated for completeness.
    "back_to_back_drop": {
        "prev": {"vocals": "linear_out", "drums": "linear_out",    "bass": "out_at_break", "other": "linear_out"},
        "next": {"vocals": "linear_in",  "drums": "linear_in",     "bass": "in_at_break",  "other": "linear_in"},
    },
}


def _stem_curves_for(rule_key: str) -> dict | None:
    return _STEM_CURVES.get(rule_key)


# --------------------------------------------------------------------------- #
# ANALYZED — 11 rules
# --------------------------------------------------------------------------- #
def _harmonic_blend(prev, nxt, cursor):
    """16-bar phrase-aligned blend using EQ swap (low cuts on out, high cuts on in)."""
    boundary = _phrase_boundary_after(prev, cursor) or cursor + 8.0
    return {
        "type": "cross_fade",
        "duration_sec": 16.0,
        "start_in_prev": boundary,
        "start_in_next": 0.0,
        "eq_curve": {"prev_low": [-12, -24], "next_high": [-6, 0]},
    }


def _eq_swap_4bar(prev, nxt, cursor):
    bpm = _safe(getattr(prev, "bpm", None), 100.0)
    bar = 4 * 60.0 / bpm
    return {
        "type": "cross_fade",
        "duration_sec": bar * 4,
        "start_in_prev": _phrase_boundary_after(prev, cursor) or cursor,
        "start_in_next": 0.0,
        "eq_curve": {"swap_lows_at": bar * 2},
    }


def _filter_sweep_high(prev, nxt, cursor):
    return {
        "type": "cross_fade",
        "duration_sec": 8.0,
        "start_in_prev": cursor,
        "start_in_next": 0.0,
        "fx": [{"name": "hipass_sweep", "from": 60, "to": 6000, "on": "prev"}],
    }


def _drop_swap(prev, nxt, cursor):
    """Cut both basslines, drop in on next downbeat."""
    db = _next_downbeat(prev, cursor) or cursor + 1.0
    return {
        "type": "drop_swap",
        "duration_sec": 1.0,
        "start_in_prev": db,
        "start_in_next": 0.0,
        "eq_curve": {"prev_low_at_drop": -48, "next_full": True},
    }


def _echo_tail(prev, nxt, cursor):
    return {
        "type": "echo_out",
        "duration_sec": 4.0,
        "start_in_prev": cursor,
        "start_in_next": 0.0,
        "fx": [{"name": "echo", "feedback": 0.6, "time_div": "1/4"}],
    }


def _loop_roll(prev, nxt, cursor):
    bpm = _safe(getattr(prev, "bpm", None), 100.0)
    bar = 4 * 60.0 / bpm
    return {
        "type": "loop_roll",
        "duration_sec": bar * 2,
        "start_in_prev": cursor,
        "start_in_next": 0.0,
        "fx": [{"name": "beat_roll", "div": "1/8", "bars": 2}],
    }


def _spin_back(prev, nxt, cursor):
    return {
        "type": "spin_back",
        "duration_sec": 1.5,
        "start_in_prev": cursor,
        "start_in_next": 0.0,
        "fx": [{"name": "reverse_decel", "duration": 1.5}],
    }


def _drum_only_bridge(prev, nxt, cursor):
    """Drop prev to drums-only stem, slide in next vocal stem."""
    return {
        "type": "stem_bridge",
        "duration_sec": 8.0,
        "start_in_prev": cursor,
        "start_in_next": 0.0,
        "stems": {"prev": ["drums"], "next": ["vocals", "drums"]},
    }


def _key_lift(prev, nxt, cursor):
    """+1 semitone pitch ride for the last 8 bars of prev → match next key."""
    return {
        "type": "cross_fade",
        "duration_sec": 8.0,
        "start_in_prev": cursor,
        "start_in_next": 0.0,
        "fx": [{"name": "pitch_ride", "from": 0, "to": 1.0}],  # semitones
    }


def _reverb_throw(prev, nxt, cursor):
    return {
        "type": "cross_fade",
        "duration_sec": 4.0,
        "start_in_prev": cursor,
        "start_in_next": 0.0,
        "fx": [{"name": "reverb_throw", "tail": 3.0, "wet": 0.7}],
    }


def _back_to_back_drop(prev, nxt, cursor):
    """Smash cut on next downbeat with a kick-roll lead-in."""
    db = _next_downbeat(prev, cursor) or cursor + 1.0
    return {
        "type": "smash_cut",
        "duration_sec": 0.0,
        "start_in_prev": db,
        "start_in_next": 0.0,
        "fx": [{"name": "kick_roll_lead", "bars": 1}],
    }


ANALYZED_TRANSITIONS: list[dict] = [
    {"key": "harmonic_blend",     "label_zh": "和声层叠",   "apply": _harmonic_blend},
    {"key": "eq_swap_4bar",       "label_zh": "EQ 4小节切换", "apply": _eq_swap_4bar},
    {"key": "filter_sweep_high",  "label_zh": "高通扫频",   "apply": _filter_sweep_high},
    {"key": "drop_swap",          "label_zh": "Drop 互换",  "apply": _drop_swap},
    {"key": "echo_tail",          "label_zh": "回声尾音",   "apply": _echo_tail},
    {"key": "loop_roll",          "label_zh": "Beat Roll", "apply": _loop_roll},
    {"key": "spin_back",          "label_zh": "倒带",       "apply": _spin_back},
    {"key": "drum_only_bridge",   "label_zh": "鼓桥过渡",   "apply": _drum_only_bridge},
    {"key": "key_lift",           "label_zh": "升 Key 衔接","apply": _key_lift},
    {"key": "reverb_throw",       "label_zh": "混响抛尾",   "apply": _reverb_throw},
    {"key": "back_to_back_drop",  "label_zh": "背靠背 Drop","apply": _back_to_back_drop},
]


# --------------------------------------------------------------------------- #
# RAW — 7 rules (no analysis required)
# --------------------------------------------------------------------------- #
def _raw_short_xfade(prev, nxt, cursor, *, dur=3.0):
    return {"type": "cross_fade", "duration_sec": dur, "start_in_prev": cursor, "start_in_next": 0.0}


RAW_TRANSITIONS: list[dict] = [
    {"key": "raw_xfade_3s",   "label_zh": "3秒交叉淡入", "apply": lambda p, n, c: _raw_short_xfade(p, n, c, dur=3.0)},
    {"key": "raw_xfade_6s",   "label_zh": "6秒交叉淡入", "apply": lambda p, n, c: _raw_short_xfade(p, n, c, dur=6.0)},
    {"key": "raw_xfade_10s",  "label_zh": "10秒交叉淡入", "apply": lambda p, n, c: _raw_short_xfade(p, n, c, dur=10.0)},
    {"key": "raw_hard_cut",   "label_zh": "硬切",       "apply": lambda p, n, c: {"type": "cut", "duration_sec": 0.0, "start_in_prev": c, "start_in_next": 0.0}},
    {"key": "raw_fade_out_in","label_zh": "淡出淡入",   "apply": lambda p, n, c: {"type": "fade_out_in", "duration_sec": 5.0, "start_in_prev": c, "start_in_next": 0.0, "silence_gap": 0.4}},
    {"key": "raw_echo_drop",  "label_zh": "回声衔接",   "apply": lambda p, n, c: {"type": "echo_out", "duration_sec": 4.0, "start_in_prev": c, "start_in_next": 0.0, "fx": [{"name": "echo", "feedback": 0.5, "time_div": "1/4"}]}},
    {"key": "raw_lp_swap",    "label_zh": "低通切换",   "apply": lambda p, n, c: {"type": "cross_fade", "duration_sec": 6.0, "start_in_prev": c, "start_in_next": 0.0, "fx": [{"name": "lopass_sweep", "from": 22000, "to": 200, "on": "prev"}]}},
]


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #
def list_transition_rules() -> dict:
    return {
        "analyzed": [{"key": r["key"], "label_zh": r["label_zh"]} for r in ANALYZED_TRANSITIONS],
        "raw":      [{"key": r["key"], "label_zh": r["label_zh"]} for r in RAW_TRANSITIONS],
        "cross_style": [
            {"key": r["key"], "label_zh": r["label_zh"], "rk_style": r["rk_style"]}
            for r in transition_strategy.list_cross_style_strategies()
        ],
    }


def pick_rule(prev_song, next_song, rule_key: str | None = None) -> dict:
    """Find a rule by key, or pick the best-fit rule via fitness scoring.

    Returns a dict with optional `_fit_score` and `_fit_top3` keys for debug.
    """
    both_analyzed = _is_analyzed(prev_song) and _is_analyzed(next_song)
    catalog = ANALYZED_TRANSITIONS if both_analyzed else RAW_TRANSITIONS

    # Caller forced a specific rule.
    if rule_key:
        for r in catalog:
            if r["key"] == rule_key:
                return r
        # Try the other catalog as a fallback (e.g. UI sent an analyzed key
        # but one song lacks analysis — degrade gracefully).
        for r in (RAW_TRANSITIONS if both_analyzed else ANALYZED_TRANSITIONS):
            if r["key"] == rule_key:
                return r

    scored = [(r, _score_rule(r["key"], prev_song, next_song)) for r in catalog]
    scored.sort(key=lambda kv: kv[1], reverse=True)
    best = dict(scored[0][0])  # shallow copy so we don't mutate the catalog
    best["_fit_score"] = round(scored[0][1], 3)
    best["_fit_top3"] = [(r["key"], round(s, 3)) for r, s in scored[:3]]
    return best


def _is_analyzed(song) -> bool:
    return bool(getattr(song, "bpm", None)) and bool(getattr(song, "beat_points", None))


# --------------------------------------------------------------------------- #
# Fitness scoring — chooses the most musically appropriate transition based on
# observable features of the two songs.
#
# Inputs (best-effort, all optional):
#   bpm, camelot_key, energy (0..1), duration, stems (presence)
# Heuristics:
#   * BPM-close + key-compatible            -> harmonic_blend / eq_swap_4bar
#   * BPM medium-diff                        -> filter_sweep_high / key_lift
#   * BPM far apart                          -> drop_swap / spin_back / b2b_drop
#   * Energy step-down                       -> echo_tail / reverb_throw
#   * Energy step-up                         -> drop_swap / back_to_back_drop / key_lift
#   * Both have stems                        -> drum_only_bridge / drop_swap allowed
#   * Same BPM (≤1.0 diff) and short next   -> loop_roll
# --------------------------------------------------------------------------- #
def _f(song, attr, default=0.0):
    v = getattr(song, attr, None)
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _has_stems(song) -> bool:
    s = getattr(song, "stems", None)
    if isinstance(s, dict):
        return all(k in s for k in ("vocals", "drums", "bass", "other"))
    return False


def _camelot_distance(a: str | None, b: str | None) -> int | None:
    """Camelot wheel distance: 0 = identical, 1 = adjacent (energy boost or
    relative minor/major switch), 2 = two steps away. Returns None if either
    key is missing/malformed."""
    if not a or not b:
        return None
    try:
        an, al = int(a[:-1]), a[-1].upper()
        bn, bl = int(b[:-1]), b[-1].upper()
    except (ValueError, IndexError):
        return None
    if al not in "AB" or bl not in "AB":
        return None
    # circular distance on the 1..12 wheel
    num_diff = min((an - bn) % 12, (bn - an) % 12)
    letter_diff = 0 if al == bl else 1
    return num_diff + letter_diff


def _score_rule(key: str, prev, nxt) -> float:
    """Return a fitness score in [0, 1.5] (slightly >1 lets clear winners surface)."""
    prev_bpm = _f(prev, "bpm", 0.0)
    next_bpm = _f(nxt, "bpm", 0.0)
    bpm_diff = abs(prev_bpm - next_bpm) if prev_bpm and next_bpm else 0.0
    bpm_close = bpm_diff <= 2.0
    bpm_medium = 2.0 < bpm_diff <= 8.0
    bpm_far = bpm_diff > 12.0

    prev_e = _f(prev, "energy", 0.5)
    next_e = _f(nxt, "energy", 0.5)
    e_delta = next_e - prev_e
    big_step_up = e_delta > 0.18
    big_step_down = e_delta < -0.18
    flat_e = abs(e_delta) <= 0.05

    cam = _camelot_distance(getattr(prev, "camelot_key", None),
                            getattr(nxt, "camelot_key", None))
    key_compat = cam is not None and cam <= 1
    key_unrelated = cam is not None and cam >= 4

    next_dur = _f(nxt, "duration", 0.0)
    next_short = 0 < next_dur < 150

    stems_ok = _has_stems(prev) and _has_stems(nxt)

    # Base score per rule. Each rule starts ~0.3 baseline; we add/subtract by
    # how well the situation matches its musical intent.
    base = 0.30
    s = base

    if key == "harmonic_blend":
        # 16-bar phrase blend: shines on tight BPM + compatible key.
        if bpm_close: s += 0.45
        elif bpm_medium: s += 0.10
        if key_compat: s += 0.30
        if flat_e: s += 0.10
        if bpm_far: s -= 0.40
        if key_unrelated: s -= 0.20

    elif key == "eq_swap_4bar":
        # Tight-medium BPM, energy similar, key compatible. Slightly snappier
        # than harmonic_blend.
        if bpm_diff <= 6.0: s += 0.35
        if not key_unrelated: s += 0.15
        if 0.0 <= e_delta <= 0.15: s += 0.15
        if bpm_far: s -= 0.30

    elif key == "filter_sweep_high":
        # Medium BPM diff or key clash → filter masks the inharmony.
        if bpm_medium: s += 0.40
        if key_unrelated: s += 0.20
        if abs(e_delta) > 0.10: s += 0.10
        if bpm_close and key_compat: s -= 0.15  # harmonic_blend would do better

    elif key == "drop_swap":
        # Bass-pivoting smash: needs energy step-up and ideally stems.
        if big_step_up: s += 0.40
        if next_e > 0.65: s += 0.20
        if stems_ok: s += 0.20
        if not stems_ok: s -= 0.15
        if bpm_far: s += 0.10  # masks tempo discontinuity
        if big_step_down: s -= 0.35

    elif key == "echo_tail":
        # Soft outro echo; perfect for energy step-down.
        if big_step_down: s += 0.45
        if next_e < 0.55: s += 0.15
        if bpm_far: s += 0.10
        if big_step_up: s -= 0.30

    elif key == "loop_roll":
        # 8th-note beat roll over 2 bars; works when next track is short or
        # tempo identical (the roll buys time before the new song's downbeat).
        if bpm_close: s += 0.30
        if next_short: s += 0.20
        if abs(e_delta) <= 0.10: s += 0.10
        if bpm_far: s -= 0.20

    elif key == "spin_back":
        # Hip-hop spinback: bold genre/tempo break.
        if bpm_far: s += 0.45
        if key_unrelated: s += 0.15
        if bpm_close and key_compat: s -= 0.30

    elif key == "drum_only_bridge":
        # Drums bridge requires stems on both sides.
        if stems_ok: s += 0.35
        else: s -= 0.50  # cannot execute without stems
        if bpm_diff <= 8.0: s += 0.20
        if abs(e_delta) <= 0.15: s += 0.10

    elif key == "key_lift":
        # +1 semitone lift: best for energy-up with similar BPM.
        if e_delta > 0.05: s += 0.30
        if bpm_diff <= 6.0: s += 0.25
        if cam is not None and cam <= 2: s += 0.15
        if bpm_far: s -= 0.25

    elif key == "reverb_throw":
        # Wet reverb tail to soften energy descent.
        if big_step_down: s += 0.35
        if next_e < 0.50: s += 0.15
        if flat_e: s -= 0.10

    elif key == "back_to_back_drop":
        # Smash cut on a downbeat — heavy energy boost moment.
        if big_step_up and next_e > 0.70: s += 0.50
        if bpm_close: s += 0.15
        if bpm_far: s += 0.10  # smash can also rescue mismatched BPM
        if big_step_down: s -= 0.40

    # ---- RAW catalog ---- #
    elif key == "raw_xfade_3s":
        if abs(e_delta) <= 0.10: s += 0.10
        if next_short: s += 0.15
    elif key == "raw_xfade_6s":
        s += 0.10  # versatile default
    elif key == "raw_xfade_10s":
        if flat_e: s += 0.20
    elif key == "raw_hard_cut":
        if big_step_up or big_step_down: s += 0.20
    elif key == "raw_fade_out_in":
        if big_step_down: s += 0.25
    elif key == "raw_echo_drop":
        if big_step_down: s += 0.20
    elif key == "raw_lp_swap":
        if big_step_down or key_unrelated: s += 0.20

    # Tiny deterministic variation (-0.05..+0.05) so back-to-back identical
    # transitions don't always pick the same rule when scores tie. We want
    # variety in a 3-song mix but the bias must be tiny so a clear winner
    # still wins.
    seed_input = f"{key}|{prev_bpm:.1f}|{next_bpm:.1f}|{prev_e:.2f}|{next_e:.2f}"
    h = sum(ord(c) for c in seed_input) % 100
    s += (h - 50) / 1000.0  # ±0.05

    return max(0.0, s)


def _smart_exit_entry(prev_song, next_song, cursor_sec: float, crossfade_sec: float) -> dict:
    """Phase-1 smart points: pick a phrase-aligned exit on prev (preferring
    outro/break/bridge cue points), and an entry on next that skips intro
    silence/build-up and lands on the first downbeat (or first beat).

    Phase-2 beatmatch: also decide a target tempo for the next track so it
    plays at (or near) prev's BPM during the crossfade. RK uses this hint to
    swap in a pre-rendered rubberband-stretched wav.

    Returns:
        {
          "exit_at_sec":    float,  # where to start the xfade in prev
          "entry_at_sec":   float,  # where the next track should begin playing
          "snapped_dur":    float,  # duration snapped to bar boundary at prev bpm
          "exit_section":   str | None,  # cue label at exit_at_sec, if any
          "skipped_intro_sec": float,    # how much head silence/build was skipped
          "target_bpm":     float | None,  # target tempo we want next at
          "tempo_ratio":    float | None,  # prev_bpm / next_bpm, clamped to safe range
          "align_strategy": str,    # "match" | "blend" | "skip"
        }
    """
    try:
        from app.modules.playlists.transition_planner import (
            TrackFeature,
            plan_phrase_transition,
        )
    except Exception:
        return {
            "exit_at_sec": float(cursor_sec),
            "entry_at_sec": 0.0,
            "snapped_dur": float(crossfade_sec),
            "exit_section": None,
            "skipped_intro_sec": 0.0,
            "target_bpm": None,
            "tempo_ratio": None,
            "align_strategy": "skip",
        }

    prev_dur = float(getattr(prev_song, "duration", 0) or 0)
    next_dur = float(getattr(next_song, "duration", 0) or 0)
    prev_bpm = _safe(getattr(prev_song, "bpm", None), 120.0)
    next_bpm = _safe(getattr(next_song, "bpm", None), prev_bpm)
    prev_beats = list(getattr(prev_song, "beat_points", []) or [])
    next_beats = list(getattr(next_song, "beat_points", []) or [])
    next_dbs = list(getattr(next_song, "downbeats", []) or [])
    prev_cues = list(getattr(prev_song, "cue_points", []) or [])
    next_cues = list(getattr(next_song, "cue_points", []) or [])

    plan = plan_phrase_transition(
        from_track=TrackFeature(song_id=0, bpm=prev_bpm, camelot_key=None, duration=prev_dur),
        to_track=TrackFeature(song_id=0, bpm=next_bpm, camelot_key=None, duration=next_dur),
        crossfade_sec=float(crossfade_sec),
        from_beat_points=prev_beats,
        to_beat_points=next_beats,
        from_cue_points=prev_cues,
    )

    exit_at = float(plan.exit_time_sec)
    if exit_at < cursor_sec - 0.5:
        bar = 4 * 60.0 / prev_bpm if prev_bpm > 0 else 2.0
        exit_at = float(min(prev_dur - 0.25, max(cursor_sec, exit_at + bar)))

    # Hard ceiling: exit_at must leave room for the full fade BEFORE the file
    # ends. Many tracks have a quiet outro (fade-out tail or silence padding)
    # that lasts 5-15s — if we let exit_at sit at duration-1, the crossfade
    # plays into dead air and listeners hear silence instead of a transition.
    # Pull exit_at back by (fade + 3s safety margin) — enough to let the tail
    # of the fade finish before the silence kicks in.
    bar_for_safety = 4 * 60.0 / prev_bpm if prev_bpm > 0 else 2.0
    safety_margin = float(crossfade_sec) + 3.0
    if prev_dur > safety_margin + 5.0:  # only apply when track is long enough
        max_exit = prev_dur - safety_margin
        if exit_at > max_exit:
            # Snap the new exit back to a downbeat near max_exit so the fade
            # still lands on a musical boundary.
            new_exit = max_exit
            for db in (getattr(prev_song, "downbeats", []) or []):
                t = float(db)
                if max_exit - bar_for_safety <= t <= max_exit:
                    new_exit = t
            exit_at = float(max(cursor_sec + 0.5, new_exit))

    entry_at = 0.0
    next_intro_skip = _next_intro_skip(next_cues, next_dbs, next_beats)
    if next_intro_skip is not None:
        entry_at = float(next_intro_skip)
    elif plan.entry_time_sec > 0.0:
        entry_at = float(plan.entry_time_sec)

    bar = 4 * 60.0 / prev_bpm if prev_bpm > 0 else 2.0
    bars = max(1, round(crossfade_sec / bar))
    snapped_dur = float(min(30.0, max(2.0, bars * bar)))

    exit_section = _section_at(prev_cues, exit_at)

    # ---- Phase 2 tempo align ----
    # tempo_ratio = prev_bpm / next_bpm. RK applies it to the next track so its
    # tempo matches prev. Clamp to ±6% (rubberband sweet spot, no audible
    # artifacts). 6-12% drifts to "blend" mode (still try, but accept drift).
    # >12% gives up entirely — DJ should pick a dramatic rule (spin_back etc.).
    target_bpm: float | None = None
    tempo_ratio: float | None = None
    align_strategy = "skip"
    if prev_bpm > 0 and next_bpm > 0:
        ratio_raw = prev_bpm / next_bpm
        diff_pct = abs(ratio_raw - 1.0) * 100.0
        if diff_pct < 0.5:
            # Already same tempo — nothing to do.
            align_strategy = "match"
        elif diff_pct <= 6.0:
            # Pull next track all the way to prev's tempo.
            target_bpm = float(prev_bpm)
            tempo_ratio = float(ratio_raw)
            align_strategy = "match"
        elif diff_pct <= 12.0:
            # Meet in the middle so neither track is stretched beyond the
            # safe range. ratio applied to next is sqrt(prev/next).
            mid_bpm = (prev_bpm + next_bpm) / 2.0
            target_bpm = float(mid_bpm)
            tempo_ratio = float(mid_bpm / next_bpm)
            align_strategy = "blend"
        else:
            align_strategy = "skip"

    return {
        "exit_at_sec": exit_at,
        "entry_at_sec": entry_at,
        "snapped_dur": snapped_dur,
        "exit_section": exit_section,
        "skipped_intro_sec": entry_at,
        "target_bpm": target_bpm,
        "tempo_ratio": tempo_ratio,
        "align_strategy": align_strategy,
    }


def _next_intro_skip(cue_points, downbeats, beat_points) -> float | None:
    """Find the first 'real start' of next track: prefer first verse/chorus/drop
    cue, fall back to first downbeat > 1.5s, fall back to first beat > 1.5s."""
    if cue_points:
        for cue in cue_points:
            label = str(cue.get("label") or "").lower()
            if label in {"verse", "chorus", "drop", "hook", "main"}:
                t = float(cue.get("time") or 0.0)
                if t > 0.5:
                    return t
    if downbeats:
        for db in downbeats:
            if float(db) >= 1.5:
                return float(db)
    if beat_points:
        for bp in beat_points:
            if float(bp) >= 1.5:
                return float(bp)
    return None


def _section_at(cue_points, t: float) -> str | None:
    """Return the cue label that contains time t (last cue with time <= t)."""
    if not cue_points:
        return None
    label = None
    for cue in cue_points:
        ct = float(cue.get("time") or 0.0)
        if ct <= t:
            label = str(cue.get("label") or "").lower() or None
        else:
            break
    return label


# --------------------------------------------------------------------------- #
# Phase 2.5 — Beat Reinforcement
#
# Some songs have weak / muddy drums that make every transition sound flat
# even when the rule + tempo align are perfect. A real DJ would either layer
# a backbeat sample on top, or duck the drums and let another track's groove
# carry the bar. We do the simpler version: when one side of a transition
# scores low on beat-strength, schedule snare/kick samples on its beats inside
# the transition window. mobile dispatches /beat_reinforce just before /xfade.
# --------------------------------------------------------------------------- #
_STRONG_GENRE_HINTS = (
    "edm", "house", "techno", "trance", "dnb", "drum", "dance", "funk",
    "disco", "hardstyle", "trap", "future", "electro", "garage", "breaks",
)
_WEAK_GENRE_HINTS = (
    "ballad", "chill", "lofi", "ambient", "acoustic", "jazz", "rnb", "r&b",
    "soul", "indie", "folk", "blues", "country",
)


def compute_beat_strength(song) -> float:
    """Return rhythmic-strength score in [0, 1]. 1 = punchy 4-on-the-floor.

    Heuristic only — no audio analysis. We score on:
      - energy (already estimated upstream; weight 0.45)
      - bpm    (closer to 120-140 = stronger; weight 0.30)
      - genre  (if available, ±0.20 swing on keyword match)
      - beat density (beats per second; weight 0.05)
    """
    energy = _f(song, "energy", 0.5)
    energy_score = max(0.0, min(1.0, energy))

    bpm = _f(song, "bpm", 0.0)
    if bpm <= 0:
        bpm_score = 0.5
    elif 110.0 <= bpm <= 140.0:
        bpm_score = 1.0
    elif 95.0 <= bpm < 110.0:
        bpm_score = 0.7
    elif 140.0 < bpm <= 160.0:
        bpm_score = 0.85
    elif bpm < 95.0:
        bpm_score = max(0.2, bpm / 95.0 * 0.6)
    else:  # >160
        bpm_score = 0.6

    genre = (getattr(song, "genre", None) or "").lower()
    style = (getattr(song, "style", None) or "").lower()
    haystack = f"{genre} {style}"
    genre_swing = 0.0
    if any(k in haystack for k in _STRONG_GENRE_HINTS):
        genre_swing = 0.15
    elif any(k in haystack for k in _WEAK_GENRE_HINTS):
        genre_swing = -0.15

    beats = list(getattr(song, "beat_points", []) or [])
    duration = _f(song, "duration", 0.0)
    if beats and duration > 0:
        bps = len(beats) / duration
        # Typical pop is ~2 bps; below 1.6 reads as sparse.
        density_score = max(0.0, min(1.0, (bps - 1.0) / 1.5))
    else:
        density_score = 0.5

    raw = (
        0.45 * energy_score
        + 0.30 * bpm_score
        + 0.05 * density_score
        + genre_swing
    )
    # Renormalize to [0, 1]: max base contribution is 0.80, plus ±0.15 swing.
    return max(0.0, min(1.0, raw / 0.80))


def _section_drum_energies(song, at_window_sec: float | None) -> tuple[float, float, float] | None:
    """Compute (kick_punch, snare_crack, groove_confidence) for the section that
    contains `at_window_sec`. Returns None if section data unavailable.
    """
    if at_window_sec is None:
        return None
    try:
        from app.modules.dj_set.section_energy import compute_section_energy_map
    except Exception:
        return None
    try:
        sections = compute_section_energy_map(song)
    except Exception:
        return None
    if not sections:
        return None
    sec = None
    for s in sections:
        if s.start <= at_window_sec < s.end:
            sec = s
            break
    if sec is None:
        sec = min(sections, key=lambda s: abs((s.start + s.end) / 2 - at_window_sec))
    groove_conf = float(min(1.0, 0.6 * sec.section_groove_energy + 0.4 * sec.section_impact_energy))
    return float(sec.section_kick_punch), float(sec.section_snare_crack), groove_conf


def beat_reinforcement_need(
    song,
    *,
    at_window_sec: float | None = None,
    transition_context_weight: float = 0.5,
) -> float:
    """Section-aware reinforcement need ∈ [0, 1].

    Formula:
        0.35 * (1 - section_kick_punch)
      + 0.30 * (1 - section_snare_crack)
      + 0.20 * groove_confidence
      + 0.15 * transition_context_weight

    Higher = more help needed (weak drums + groove signal).
    Falls back to whole-track compute_beat_strength when section data missing.
    """
    triple = _section_drum_energies(song, at_window_sec)
    if triple is None:
        # Legacy path — invert beat_strength as a proxy for need.
        return float(min(1.0, max(0.0, (1.0 - compute_beat_strength(song)) * 0.85
                                      + 0.15 * transition_context_weight)))
    kp, sc, groove_conf = triple
    need = (
        0.35 * (1.0 - kp)
        + 0.30 * (1.0 - sc)
        + 0.20 * groove_conf
        + 0.15 * float(max(0.0, min(1.0, transition_context_weight)))
    )
    return float(max(0.0, min(1.0, need)))


def _beats_in_window(beats: list[float], start: float, end: float) -> list[float]:
    return [float(b) for b in beats if start - 0.05 <= float(b) <= end + 0.05]


def _plan_beat_reinforce(
    prev_song,
    next_song,
    exit_at_sec: float,
    entry_at_sec: float,
    duration_sec: float,
) -> dict | None:
    """Return {prev: {...}, next: {...}} or None when no reinforcement helps.

    Decision matrix (prev_s, next_s = beat strength):
      both >= 0.60 → None (groove already obvious on both sides)
      both <  0.35 → reinforce both with backbeat (4 hits per bar feels weak)
      diff >= 0.20 → reinforce only the weaker side
      else         → reinforce the weaker side at low gain
    """
    if duration_sec < 1.0:
        return None
    # Section-aware need (Step 9): each side scored at the seam window.
    # Falls back to whole-track strength when section data missing.
    prev_need = beat_reinforcement_need(prev_song, at_window_sec=float(exit_at_sec),
                                        transition_context_weight=0.6)
    next_need = beat_reinforcement_need(next_song, at_window_sec=float(entry_at_sec),
                                        transition_context_weight=0.6)
    # Convert "need" back to "strength" so the existing thresholds keep meaning:
    #   need 0.0 -> strength 1.0   (no help needed)
    #   need 1.0 -> strength 0.0   (full help needed)
    prev_s = float(max(0.0, min(1.0, 1.0 - prev_need)))
    next_s = float(max(0.0, min(1.0, 1.0 - next_need)))
    sides: dict[str, dict] = {}

    def _entry(song, start: float, end: float, gain: float, pattern: str, key: int) -> dict | None:
        beats = _beats_in_window(list(getattr(song, "beat_points", []) or []), start, end)
        if len(beats) < 2:
            return None
        return {
            "start_sec": round(start, 3),
            "end_sec": round(end, 3),
            "beats": [round(b, 4) for b in beats],
            "sample_key": int(key),
            "gain": round(gain, 3),
            "pattern": pattern,
        }

    prev_window = (float(exit_at_sec), float(exit_at_sec) + float(duration_sec))
    next_window = (float(entry_at_sec), float(entry_at_sec) + float(duration_sec))

    # Phase 2.5 v2 — louder, denser reinforcement so the "drum push" actually
    # carries the transition. Tuning rationale:
    #   gain 1.4              — engine multiplies by SAMPLE_GAIN[4]=3.0 → real ~4.2x,
    #                          headroom against the limiter so snares stay punchy
    #                          without overwhelming the song
    #   pattern "all"         — every beat, not every other (was 'backbeat')
    #   sample_key 4          — snare_crack stays the rhythm anchor
    if prev_s >= 0.65 and next_s >= 0.65:
        return None
    if prev_s < 0.40 and next_s < 0.40:
        p = _entry(prev_song, *prev_window, gain=1.4, pattern="all", key=4)
        n = _entry(next_song, *next_window, gain=1.4, pattern="all", key=4)
        if p:
            sides["prev"] = p
        if n:
            sides["next"] = n
    elif prev_s + 0.18 <= next_s:
        p = _entry(prev_song, *prev_window, gain=1.4, pattern="all", key=4)
        if p:
            sides["prev"] = p
    elif next_s + 0.18 <= prev_s:
        n = _entry(next_song, *next_window, gain=1.4, pattern="all", key=4)
        if n:
            sides["next"] = n
    else:
        weaker = "prev" if prev_s <= next_s else "next"
        if weaker == "prev":
            p = _entry(prev_song, *prev_window, gain=1.0, pattern="backbeat", key=4)
            if p:
                sides["prev"] = p
        else:
            n = _entry(next_song, *next_window, gain=1.0, pattern="backbeat", key=4)
            if n:
                sides["next"] = n

    if not sides:
        return None
    sides["prev_strength"] = round(prev_s, 3)
    sides["next_strength"] = round(next_s, 3)
    return sides


def build_transition_spec(
    prev_song,
    next_song,
    cursor_sec: float,
    rule_key: str | None = None,
    *,
    forced_from_at_sec: float | None = None,
    forced_to_at_sec: float | None = None,
    forced_fade_sec: float | None = None,
    enable_cross_style: bool = True,
) -> dict:
    rule = pick_rule(prev_song, next_song, rule_key)
    spec = rule["apply"](prev_song, next_song, cursor_sec)
    spec["rule_key"] = rule["key"]
    spec["rule_label_zh"] = rule["label_zh"]
    if "_fit_score" in rule:
        spec["fit_score"] = rule["_fit_score"]
    if "_fit_top3" in rule:
        spec["fit_top3"] = rule["_fit_top3"]
    # Lift minimum duration for FX-bound rules. Their original spec is short
    # because the original FX (reverse, kick-roll, smash) was supposed to
    # cover the cut. RK's audio-engine has only volume/EQ envelopes, so a
    # 1-1.5s window is heard as a hard splice. The rule's musical intent
    # (which preset to dial in) is still correct — only the duration needs
    # widening so the envelope can actually breathe.
    min_dur = _MIN_DURATION_FOR_RULE.get(rule["key"])
    if min_dur is not None:
        spec["duration_sec"] = max(float(spec.get("duration_sec", 0.0)), min_dur)

    # Phase-1 smart exit/entry: enrich the spec with phrase-aligned points so
    # mobile can xfade from outro→intro instead of end→start. Mobile reads
    # from_at_sec / to_at_sec when present and falls back to the legacy
    # cursor / 0 if either is missing.
    smart = _smart_exit_entry(prev_song, next_song, cursor_sec, float(spec.get("duration_sec", 6.0)))
    if forced_from_at_sec is not None:
        smart["exit_at_sec"] = float(forced_from_at_sec)
    if forced_to_at_sec is not None:
        smart["entry_at_sec"] = float(forced_to_at_sec)
        smart["skipped_intro_sec"] = float(forced_to_at_sec)
    if forced_fade_sec is not None:
        smart["snapped_dur"] = float(forced_fade_sec)
    spec["from_at_sec"] = round(smart["exit_at_sec"], 3)
    spec["to_at_sec"] = round(smart["entry_at_sec"], 3)
    spec["duration_sec"] = round(smart["snapped_dur"], 3)
    spec["start_in_prev"] = spec["from_at_sec"]
    spec["start_in_next"] = spec["to_at_sec"]
    if smart["exit_section"]:
        spec["exit_section"] = smart["exit_section"]
    spec["skipped_intro_sec"] = round(smart["skipped_intro_sec"], 3)
    if smart.get("target_bpm") is not None:
        spec["target_bpm"] = round(float(smart["target_bpm"]), 2)
    if smart.get("tempo_ratio") is not None:
        spec["tempo_ratio"] = round(float(smart["tempo_ratio"]), 5)
    spec["align_strategy"] = smart.get("align_strategy") or "skip"

    # Phase 2.5 — beat reinforcement
    reinforce = _plan_beat_reinforce(
        prev_song,
        next_song,
        exit_at_sec=float(spec["from_at_sec"]),
        entry_at_sec=float(spec["to_at_sec"]),
        duration_sec=float(spec["duration_sec"]),
    )
    if reinforce:
        spec["beat_reinforce"] = reinforce

    # Phase 3.1 — stem curves dispatch (engine respects only when both decks
    # have all 4 stems; otherwise stem_curves is metadata for cutInfo display).
    stem_curves = _stem_curves_for(rule["key"])
    if stem_curves:
        spec["stem_curves"] = stem_curves
    if enable_cross_style:
        return transition_strategy.apply_cross_style_strategy(prev_song, next_song, cursor_sec, spec)
    return spec


# Minimum transition length on RK basic playback tier (envelope-only, no FX).
# Keep this in sync with mobile/lib/src/dj_control_page.dart `_minFadeForRule`.
_MIN_DURATION_FOR_RULE: dict[str, float] = {
    "spin_back":         5.0,
    "loop_roll":         4.0,
    "drop_swap":         4.0,
    "back_to_back_drop": 4.0,
    "echo_tail":         5.0,
    "reverb_throw":      5.0,
}
