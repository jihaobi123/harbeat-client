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


def build_transition_spec(prev_song, next_song, cursor_sec: float, rule_key: str | None = None) -> dict:
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
