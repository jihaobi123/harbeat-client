"""Cross-style transition strategy selector.

This layer sits above the existing mixer rules. It does not replace the
current automix recipes; it inspects the A->B compatibility gap and, only when
the pair is too risky for a normal long blend, upgrades the spec to a more
intentional cross-style timeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


TempoRelation = Literal["close", "half-time", "double-time", "unrelated"]


@dataclass(frozen=True)
class TransitionContext:
    bpmDiff: float
    bpmDiffRatio: float
    tempoRelation: TempoRelation
    keyDistance: int
    genreDistance: float
    energyDiff: float
    vocalConflictRisk: float
    phraseBarsAvailable: int
    stemsAvailable: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "bpmDiff": round(self.bpmDiff, 3),
            "bpmDiffRatio": round(self.bpmDiffRatio, 4),
            "tempoRelation": self.tempoRelation,
            "keyDistance": self.keyDistance,
            "genreDistance": round(self.genreDistance, 3),
            "energyDiff": round(self.energyDiff, 3),
            "vocalConflictRisk": round(self.vocalConflictRisk, 3),
            "phraseBarsAvailable": self.phraseBarsAvailable,
            "stemsAvailable": self.stemsAvailable,
        }


@dataclass(frozen=True)
class CrossStyleStrategy:
    key: str
    label_zh: str
    rk_style: str
    fallback_rule: str
    duration_bars: int
    timeline: list[dict[str, Any]]
    stem_curves: dict[str, Any] | None = None
    eq_curves: dict[str, Any] | None = None
    fx: list[dict[str, Any]] | None = None
    tags: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label_zh": self.label_zh,
            "rk_style": self.rk_style,
            "fallback_rule": self.fallback_rule,
            "duration_bars": self.duration_bars,
            "timeline": self.timeline,
            "stem_curves": self.stem_curves or {},
            "eq_curves": self.eq_curves or {},
            "fx": self.fx or [],
            "tags": list(self.tags),
        }


_GENRE_FAMILIES: dict[str, set[str]] = {
    "hiphop": {"hiphop", "hip-hop", "rap", "trap", "boom bap", "r&b", "rnb", "krump"},
    "funk": {"funk", "locking", "popping", "disco", "soul"},
    "club": {"house", "techno", "edm", "electro", "dance", "waacking", "garage"},
    "bass": {"dnb", "drum and bass", "dubstep", "breaks", "jungle"},
    "pop": {"pop", "k-pop", "j-pop", "rock", "indie"},
    "latin": {"latin", "reggaeton", "dancehall", "afrobeat", "afrobeats"},
}


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _energy(song) -> float:
    return max(0.0, min(1.0, _float(getattr(song, "energy", None), 0.5)))


def _bar_sec(song) -> float:
    bpm = _float(getattr(song, "bpm", None), 120.0)
    return 4.0 * 60.0 / bpm if bpm > 0 else 2.0


def _camelot_distance(a: str | None, b: str | None) -> int:
    def parse(v: str | None) -> tuple[int, str] | None:
        if not v:
            return None
        s = str(v).strip().upper()
        if len(s) < 2 or s[-1] not in ("A", "B"):
            return None
        try:
            n = int(s[:-1])
        except ValueError:
            return None
        return (n, s[-1]) if 1 <= n <= 12 else None

    pa = parse(a)
    pb = parse(b)
    if pa is None or pb is None:
        return 6
    na, la = pa
    nb, lb = pb
    wheel = min((na - nb) % 12, (nb - na) % 12)
    return wheel + (0 if la == lb else 1)


def _genre_terms(song) -> set[str]:
    out: set[str] = set()
    for attr in ("genre", "style"):
        raw = getattr(song, attr, None)
        if raw:
            out.add(str(raw).strip().lower())
    gp = getattr(song, "genre_profile", None)
    if isinstance(gp, dict):
        for key in ("genre", "primary", "primary_genre", "style"):
            if gp.get(key):
                out.add(str(gp[key]).strip().lower())
        for item in gp.get("tags") or gp.get("genres") or []:
            out.add(str(item).strip().lower())
    for item in getattr(song, "dance_styles", None) or []:
        if isinstance(item, dict) and item.get("key"):
            out.add(str(item["key"]).strip().lower())
    return {x for x in out if x}


def _family_for(term: str) -> str | None:
    for family, aliases in _GENRE_FAMILIES.items():
        if term in aliases or any(alias in term for alias in aliases):
            return family
    return None


def _genre_distance(a, b) -> float:
    ta = _genre_terms(a)
    tb = _genre_terms(b)
    if not ta or not tb:
        return 0.5
    if ta & tb:
        return 0.0
    fa = {_family_for(t) for t in ta}
    fb = {_family_for(t) for t in tb}
    fa.discard(None)
    fb.discard(None)
    if fa and fb and fa & fb:
        return 0.35
    if fa and fb:
        return 0.85
    return 0.65


def _tempo_relation(a_bpm: float, b_bpm: float) -> TempoRelation:
    if a_bpm <= 0 or b_bpm <= 0:
        return "unrelated"
    ratio = b_bpm / a_bpm
    if abs(ratio - 1.0) <= 0.06:
        return "close"
    if abs(ratio - 2.0) <= 0.08:
        return "double-time"
    if abs(ratio - 0.5) <= 0.08:
        return "half-time"
    return "unrelated"


def _section_vocal_density(song, at_sec: float) -> float:
    try:
        from app.modules.dj_set.section_energy import compute_section_energy_map
        sections = compute_section_energy_map(song)
    except Exception:
        sections = []
    if sections:
        sec = min(sections, key=lambda s: abs(((s.start + s.end) / 2.0) - at_sec))
        return float(sec.section_vocal_density)
    for cue in getattr(song, "cue_points", None) or []:
        label = str(cue.get("label") or "").lower()
        if label in {"verse", "chorus", "hook", "rap", "bridge"}:
            try:
                if abs(float(cue.get("time") or 0.0) - at_sec) <= 12.0:
                    return 0.75
            except (TypeError, ValueError):
                pass
    return 0.35


def _phrase_bars_available(prev, nxt, cursor_sec: float) -> int:
    bpm = _float(getattr(prev, "bpm", None), 120.0)
    bar = 4.0 * 60.0 / bpm if bpm > 0 else 2.0
    dur = _float(getattr(prev, "duration", None), cursor_sec + 8.0)
    remaining = max(0.0, dur - cursor_sec)
    by_time = int(remaining // bar)
    windows = getattr(prev, "transition_windows", None) or []
    by_window = 0
    for w in windows:
        try:
            start = _float(w.get("start") or w.get("start_sec"), 0.0)
            end = _float(w.get("end") or w.get("end_sec"), start)
            if end >= cursor_sec:
                by_window = max(by_window, int((end - max(start, cursor_sec)) // bar))
        except AttributeError:
            continue
    bars = max(by_time, by_window)
    if bars >= 16:
        return 16
    if bars >= 8:
        return 8
    if bars >= 4:
        return 4
    return max(0, bars)


def _stems_available(a, b) -> bool:
    def complete(song) -> bool:
        stems = getattr(song, "stems", None)
        return isinstance(stems, dict) and all(stems.get(k) for k in ("vocals", "drums", "bass", "other"))

    return complete(a) and complete(b)


def build_transition_context(
    prev,
    nxt,
    cursor_sec: float,
    *,
    from_at_sec: float | None = None,
    to_at_sec: float | None = None,
    planned_fade_sec: float | None = None,
) -> TransitionContext:
    a_bpm = _float(getattr(prev, "bpm", None), 0.0)
    b_bpm = _float(getattr(nxt, "bpm", None), 0.0)
    bpm_diff = abs(b_bpm - a_bpm) if a_bpm and b_bpm else 0.0
    bpm_ratio = bpm_diff / max(a_bpm, b_bpm) if max(a_bpm, b_bpm) > 0 else 1.0
    a_vocal = _section_vocal_density(prev, from_at_sec if from_at_sec is not None else cursor_sec)
    b_vocal = _section_vocal_density(nxt, to_at_sec if to_at_sec is not None else 0.0)
    phrase_bars = _phrase_bars_available(prev, nxt, cursor_sec)
    if planned_fade_sec is not None:
        bar = _bar_sec(prev)
        phrase_bars = max(phrase_bars, int(float(planned_fade_sec) // max(0.001, bar)))
    if phrase_bars >= 16:
        phrase_bars = 16
    elif phrase_bars >= 8:
        phrase_bars = 8
    elif phrase_bars >= 4:
        phrase_bars = 4
    return TransitionContext(
        bpmDiff=bpm_diff,
        bpmDiffRatio=bpm_ratio,
        tempoRelation=_tempo_relation(a_bpm, b_bpm),
        keyDistance=_camelot_distance(getattr(prev, "camelot_key", None), getattr(nxt, "camelot_key", None)),
        genreDistance=_genre_distance(prev, nxt),
        energyDiff=abs(_energy(nxt) - _energy(prev)),
        vocalConflictRisk=max(0.0, min(1.0, a_vocal * b_vocal)),
        phraseBarsAvailable=phrase_bars,
        stemsAvailable=_stems_available(prev, nxt),
    )


def _timeline(*items: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(item) for item in items]


def _strategy_echo_out_hard_drop(bars: int) -> CrossStyleStrategy:
    return CrossStyleStrategy(
        key="echo_out_hard_drop",
        label_zh="Echo Out 硬落点",
        rk_style="echo_freeze",
        fallback_rule="raw_echo_drop",
        duration_bars=min(4, max(1, bars)),
        timeline=_timeline(
            {"at": 0.00, "deck": "prev", "action": "eq", "bass_db": -3},
            {"at": 0.55, "deck": "prev", "action": "eq", "bass_db": -18},
            {"at": 0.78, "deck": "prev", "action": "echo", "sync": "1/4", "feedback": 0.58},
            {"at": 0.88, "deck": "system", "action": "impact", "optional": True},
            {"at": 1.00, "deck": "next", "action": "drop_on_downbeat"},
        ),
        eq_curves={"prev_low": [0, -18, -48], "next_low": [-12, 0]},
        fx=[{"name": "tempo_synced_echo", "time_div": "1/4"}, {"name": "impact", "optional": True}],
        tags=("punctuation", "no_long_overlap"),
    )


def _strategy_percussion_bridge(bars: int) -> CrossStyleStrategy:
    return CrossStyleStrategy(
        key="percussion_bridge",
        label_zh="鼓组桥接",
        rk_style="drum_swap",
        fallback_rule="filter_sweep_high",
        duration_bars=8 if bars >= 8 else 4,
        timeline=_timeline(
            {"at": 0.00, "deck": "prev", "action": "strip", "keep": ["drums"]},
            {"at": 0.20, "deck": "prev", "action": "filter_sweep", "mode": "highpass_light"},
            {"at": 0.45, "deck": "next", "action": "stem_in", "stems": ["drums"]},
            {"at": 0.62, "deck": "next", "action": "stem_in", "stems": ["bass"]},
            {"at": 0.78, "deck": "next", "action": "stem_in", "stems": ["other"]},
            {"at": 1.00, "deck": "prev", "action": "mute", "stems": ["drums"]},
        ),
        stem_curves={
            "prev": {"vocals": "linear_out", "drums": "hold_then_out", "bass": "out_early", "other": "out_early"},
            "next": {"vocals": "in_late", "drums": "linear_in", "bass": "in_at_break", "other": "linear_in"},
        },
        eq_curves={"prev_low": [0, -9, -18], "next_low": [-18, -9, 0]},
        fx=[{"name": "hipass_sweep", "on": "prev", "amount": "light"}],
        tags=("rhythm_bridge", "key_neutral"),
    )


def _strategy_stem_strip_rebuild(bars: int, allow_vocal_overlap: bool) -> CrossStyleStrategy:
    return CrossStyleStrategy(
        key="stem_strip_rebuild",
        label_zh="分轨拆层重建",
        rk_style="vocal_handoff",
        fallback_rule="drum_only_bridge",
        duration_bars=8 if bars >= 8 else 4,
        timeline=_timeline(
            {"at": 0.00, "deck": "prev", "action": "stem_out", "stem": "vocals"},
            {"at": 0.20, "deck": "prev", "action": "stem_out", "stem": "other"},
            {"at": 0.42, "deck": "prev", "action": "bass_out"},
            {"at": 0.45, "deck": "next", "action": "stem_in", "stem": "drums"},
            {"at": 0.58, "deck": "next", "action": "bass_in"},
            {"at": 0.72, "deck": "next", "action": "stem_in", "stem": "other"},
            {"at": 0.88 if allow_vocal_overlap else 0.96, "deck": "next", "action": "stem_in", "stem": "vocals"},
        ),
        stem_curves={
            "prev": {"vocals": "out_early", "drums": "hold_then_out", "bass": "out_at_break", "other": "out_early"},
            "next": {"vocals": "linear_in" if allow_vocal_overlap else "in_very_late", "drums": "linear_in", "bass": "in_at_break", "other": "in_late"},
        },
        eq_curves={"bass_exclusive": True},
        tags=("stem_aware", "no_double_vocal", "bass_exclusive"),
    )


def _strategy_auto_bpm_ramp(bars: int) -> CrossStyleStrategy:
    return CrossStyleStrategy(
        key="auto_bpm_ramp",
        label_zh="自动 BPM Ramp",
        rk_style="rise",
        fallback_rule="filter_sweep_high",
        duration_bars=8 if bars >= 8 else 4,
        timeline=_timeline(
            {"at": 0.00, "deck": "prev", "action": "tempo_ramp_start"},
            {"at": 0.15, "deck": "prev", "action": "stem_out", "stems": ["vocals", "other"]},
            {"at": 0.72, "deck": "prev", "action": "tempo_ramp_arrive"},
            {"at": 0.76, "deck": "next", "action": "drop_on_downbeat"},
            {"at": 1.00, "deck": "prev", "action": "fade_out"},
        ),
        stem_curves={
            "prev": {"vocals": "out_early", "drums": "hold_then_out", "bass": "linear_out", "other": "out_early"},
            "next": {"vocals": "in_late", "drums": "linear_in", "bass": "linear_in", "other": "linear_in"},
        },
        fx=[{"name": "tempo_ramp"}, {"name": "highpass_mask"}],
        tags=("tempo_ramp", "downbeat_drop"),
    )


def _strategy_half_double_pivot(bars: int) -> CrossStyleStrategy:
    return CrossStyleStrategy(
        key="half_time_double_time_pivot",
        label_zh="半速/倍速 Pivot",
        rk_style="drum_swap",
        fallback_rule="raw_xfade_6s",
        duration_bars=8 if bars >= 8 else 4,
        timeline=_timeline(
            {"at": 0.00, "deck": "prev", "action": "drum_loop", "feel": "source"},
            {"at": 0.45, "deck": "system", "action": "drum_fill", "optional": True},
            {"at": 0.50, "deck": "next", "action": "drums_in", "feel": "target"},
            {"at": 0.72, "deck": "system", "action": "micro_silence", "beats": 0.5, "optional": True},
            {"at": 0.76, "deck": "next", "action": "bass_and_body_in"},
        ),
        stem_curves={
            "prev": {"vocals": "linear_out", "drums": "hold_then_out", "bass": "out_at_break", "other": "linear_out"},
            "next": {"vocals": "in_late", "drums": "linear_in", "bass": "in_at_break", "other": "linear_in"},
        },
        fx=[{"name": "drum_fill", "optional": True}, {"name": "impact", "optional": True}],
        tags=("half_double_time", "rhythm_pivot"),
    )


def _strategy_neutral_fx_bridge(bars: int) -> CrossStyleStrategy:
    return CrossStyleStrategy(
        key="neutral_fx_bridge",
        label_zh="中性 FX 桥",
        rk_style="melt",
        fallback_rule="raw_lp_swap",
        duration_bars=min(4, max(1, bars)),
        timeline=_timeline(
            {"at": 0.00, "deck": "prev", "action": "filter_sweep"},
            {"at": 0.38, "deck": "prev", "action": "echo_out"},
            {"at": 0.45, "deck": "system", "action": "noise_sweep", "tonal": False},
            {"at": 0.68, "deck": "system", "action": "impact", "optional": True},
            {"at": 0.75, "deck": "next", "action": "drop_on_downbeat"},
        ),
        eq_curves={"neutral_bridge": True, "prev_low": [0, -18, -48]},
        fx=[{"name": "noise_sweep", "tonal": False}, {"name": "echo", "time_div": "1/4"}],
        tags=("no_stems_fallback", "key_neutral"),
    )


def _strategy_breakdown_reset(bars: int) -> CrossStyleStrategy:
    return CrossStyleStrategy(
        key="breakdown_reset",
        label_zh="Breakdown Reset",
        rk_style="fade",
        fallback_rule="raw_fade_out_in",
        duration_bars=4 if bars >= 4 else 2,
        timeline=_timeline(
            {"at": 0.00, "deck": "prev", "action": "fade_to_breakdown"},
            {"at": 0.35, "deck": "prev", "action": "remove_low_end"},
            {"at": 0.58, "deck": "system", "action": "short_air_gap", "beats": 0.5, "optional": True},
            {"at": 0.62, "deck": "next", "action": "intro_or_downbeat_in"},
            {"at": 1.00, "deck": "next", "action": "full_body"},
        ),
        eq_curves={"prev_low": [0, -24, -48], "reset_gap": True},
        fx=[{"name": "short_reverb_tail"}, {"name": "air_gap", "optional": True}],
        tags=("reset", "phrase_punctuation"),
    )


def _strategy_impact_slam_cut(bars: int) -> CrossStyleStrategy:
    return CrossStyleStrategy(
        key="impact_slam_cut",
        label_zh="Impact Slam Cut",
        rk_style="slam",
        fallback_rule="raw_hard_cut",
        duration_bars=1,
        timeline=_timeline(
            {"at": 0.00, "deck": "prev", "action": "quick_low_cut"},
            {"at": 0.50, "deck": "system", "action": "impact", "optional": True},
            {"at": 0.75, "deck": "prev", "action": "mute"},
            {"at": 1.00, "deck": "next", "action": "drop_on_downbeat"},
        ),
        eq_curves={"prev_low": [0, -48], "hard_gate": True},
        fx=[{"name": "impact", "optional": True}],
        tags=("emergency_safe", "short_overlap"),
    )


def select_cross_style_strategy(ctx: TransitionContext) -> CrossStyleStrategy | None:
    """Return a cross-style strategy when normal blend risk is high."""
    bars = ctx.phraseBarsAvailable or 4
    very_far = ctx.bpmDiffRatio > 0.16 or ctx.keyDistance >= 5 or ctx.genreDistance >= 0.80
    medium_bpm_gap = 0.08 <= ctx.bpmDiffRatio <= 0.12
    high_conflict = ctx.vocalConflictRisk >= 0.38 or ctx.keyDistance >= 4

    if ctx.tempoRelation in {"half-time", "double-time"} and bars >= 4:
        return _strategy_half_double_pivot(bars)
    if medium_bpm_gap and bars >= 4:
        return _strategy_auto_bpm_ramp(bars)
    if very_far and not ctx.stemsAvailable and bars >= 2:
        return _strategy_neutral_fx_bridge(bars)
    if very_far:
        return _strategy_echo_out_hard_drop(bars)
    if ctx.stemsAvailable and high_conflict:
        return _strategy_stem_strip_rebuild(bars, allow_vocal_overlap=ctx.keyDistance <= 1)
    if ctx.stemsAvailable and ctx.genreDistance >= 0.55 and bars >= 4:
        return _strategy_percussion_bridge(bars)
    if ctx.energyDiff >= 0.35 and bars >= 4:
        return _strategy_breakdown_reset(bars)
    if ctx.bpmDiffRatio > 0.12 or (
        ctx.genreDistance >= 0.65 and (ctx.keyDistance >= 4 or ctx.vocalConflictRisk >= 0.38)
    ):
        return _strategy_impact_slam_cut(bars)
    return None


def apply_cross_style_strategy(prev, nxt, cursor_sec: float, spec: dict) -> dict:
    """Attach context and, when needed, replace normal rule metadata."""
    ctx = build_transition_context(
        prev,
        nxt,
        cursor_sec,
        from_at_sec=_float(spec.get("from_at_sec"), cursor_sec),
        to_at_sec=_float(spec.get("to_at_sec"), 0.0),
        planned_fade_sec=_float(spec.get("duration_sec"), 0.0),
    )
    strategy = select_cross_style_strategy(ctx)
    spec["transition_context"] = ctx.as_dict()
    if strategy is None:
        spec["transition_strategy"] = {
            "key": "standard_compatibility_blend",
            "label_zh": "标准兼容混音",
            "reason": "BPM、调性、风格或人声风险未超过跨风格阈值",
        }
        return spec

    bar = _bar_sec(prev)
    duration = max(0.05, min(32.0, strategy.duration_bars * bar))
    if strategy.key == "impact_slam_cut":
        duration = max(0.5, min(duration, bar))
    spec["rule_key"] = strategy.key
    spec["rule_label_zh"] = strategy.label_zh
    spec["duration_sec"] = round(duration, 3)
    spec["type"] = "cross_style_transition"
    spec["fallback_style"] = strategy.fallback_rule
    spec["rk_style"] = strategy.rk_style
    spec["timeline"] = strategy.timeline
    spec["transition_strategy"] = strategy.as_dict()
    if strategy.stem_curves:
        spec["stem_curves"] = strategy.stem_curves
    if strategy.eq_curves:
        spec["eq_curves"] = strategy.eq_curves
        spec["eq_curve"] = {**(spec.get("eq_curve") or {}), **strategy.eq_curves}
    if strategy.fx:
        spec["fx"] = list(spec.get("fx") or []) + strategy.fx
    spec["strategy_tags"] = list(strategy.tags)
    return spec


def list_cross_style_strategies() -> list[dict[str, Any]]:
    return [
        _strategy_echo_out_hard_drop(4).as_dict(),
        _strategy_percussion_bridge(8).as_dict(),
        _strategy_stem_strip_rebuild(8, allow_vocal_overlap=False).as_dict(),
        _strategy_auto_bpm_ramp(8).as_dict(),
        _strategy_half_double_pivot(8).as_dict(),
        _strategy_neutral_fx_bridge(4).as_dict(),
        _strategy_breakdown_reset(4).as_dict(),
        _strategy_impact_slam_cut(1).as_dict(),
    ]
