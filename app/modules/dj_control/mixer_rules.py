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
    """Find a rule by key, or pick a sensible default."""
    catalog = ANALYZED_TRANSITIONS if _is_analyzed(prev_song) and _is_analyzed(next_song) else RAW_TRANSITIONS
    if rule_key:
        for r in catalog:
            if r["key"] == rule_key:
                return r
    # Default: harmonic_blend if both analyzed, otherwise 6-second xfade.
    return catalog[0]


def _is_analyzed(song) -> bool:
    return bool(getattr(song, "bpm", None)) and bool(getattr(song, "beat_points", None))


def build_transition_spec(prev_song, next_song, cursor_sec: float, rule_key: str | None = None) -> dict:
    rule = pick_rule(prev_song, next_song, rule_key)
    spec = rule["apply"](prev_song, next_song, cursor_sec)
    spec["rule_key"] = rule["key"]
    spec["rule_label_zh"] = rule["label_zh"]
    return spec
