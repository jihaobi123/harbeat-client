"""Generate MP3-only DJ EQ band mix transition plans."""

from __future__ import annotations

import hashlib
from typing import Any

from app.modules.dj_control import mixer_rules
from app.modules.dj_control.band_analysis import clamp01
from app.modules.dj_control.eq_transition_presets import preset_for_strategy, strategy_for_user_mode
from app.modules.dj_control.mix_profile import build_mix_profile


def _curve_avg(curve: Any, default: float = 0.5) -> float:
    if not isinstance(curve, list) or not curve:
        return default
    vals: list[float] = []
    for item in curve:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            vals.append(clamp01(item[1], default))
    return sum(vals) / len(vals) if vals else default


def _camelot_distance(a: str | None, b: str | None) -> int | None:
    if not a or not b:
        return None
    try:
        an, al = int(a[:-1]), a[-1].upper()
        bn, bl = int(b[:-1]), b[-1].upper()
    except (ValueError, IndexError):
        return None
    if al not in "AB" or bl not in "AB":
        return None
    num_diff = min((an - bn) % 12, (bn - an) % 12)
    letter_diff = 0 if al == bl else 1
    return num_diff + letter_diff


def _auto_strategy(prev_song: Any, next_song: Any, prev_profile: dict, next_profile: dict) -> str:
    prev_bpm = float(getattr(prev_song, "bpm", 0.0) or prev_profile.get("bpm") or 0.0)
    next_bpm = float(getattr(next_song, "bpm", 0.0) or next_profile.get("bpm") or 0.0)
    bpm_diff = abs(prev_bpm - next_bpm) if prev_bpm and next_bpm else 0.0
    prev_energy = clamp01(getattr(prev_song, "energy", None), 0.5)
    next_energy = clamp01(getattr(next_song, "energy", None), 0.5)
    e_delta = next_energy - prev_energy
    cam = _camelot_distance(getattr(prev_song, "camelot_key", None), getattr(next_song, "camelot_key", None))

    prev_vocal = _curve_avg((prev_profile.get("density") or {}).get("vocal_density_curve"), 0.25)
    next_vocal = _curve_avg((next_profile.get("density") or {}).get("vocal_density_curve"), 0.25)
    prev_low = _curve_avg((prev_profile.get("band_energy") or {}).get("low_curve"), prev_energy)
    next_low = _curve_avg((next_profile.get("band_energy") or {}).get("low_curve"), next_energy)

    if prev_vocal > 0.55 and next_vocal > 0.45:
        return "vocal_safe"
    if bpm_diff > 8.0 or (cam is not None and cam >= 4):
        return "filter_sweep"
    if next_energy > 0.68 or e_delta > 0.12:
        return "hard_bass_swap" if prev_low + next_low > 1.05 else "soft_bass_swap"
    if prev_low + next_low > 1.25:
        return "soft_bass_swap"
    return "smooth_blend"


def _beats_to_sec(beats: int, bpm: float | None, fallback: float) -> float:
    if bpm and bpm > 0:
        return max(3.0, min(30.0, beats * 60.0 / bpm))
    return fallback


def plan_eq_band_mix_transition(
    prev_song: Any,
    next_song: Any,
    *,
    cursor_sec: float = 0.0,
    rule_key: str | None = None,
    eq_mix_user_mode: str | None = "auto",
    target_style: str | None = None,
) -> dict[str, Any]:
    """Return a transition plan with doc-shaped EQ/fader curves and fallback fields."""
    prev_profile = build_mix_profile(prev_song)
    next_profile = build_mix_profile(next_song)
    auto = _auto_strategy(prev_song, next_song, prev_profile, next_profile)
    strategy = strategy_for_user_mode(eq_mix_user_mode, auto_strategy=auto)
    preset = preset_for_strategy(strategy)

    prev_bpm = float(getattr(prev_song, "bpm", 0.0) or prev_profile.get("bpm") or 0.0)
    duration_beats = int(preset.get("duration_beats") or 32)
    fallback_seed = mixer_rules.build_transition_spec(prev_song, next_song, cursor_sec, rule_key)
    fade_sec = _beats_to_sec(duration_beats, prev_bpm if prev_bpm > 0 else None, float(fallback_seed.get("duration_sec", 8.0) or 8.0))
    fallback = mixer_rules.build_transition_spec(
        prev_song,
        next_song,
        cursor_sec,
        rule_key,
        forced_fade_sec=fade_sec,
    )
    to_at_sec = float(fallback.get("to_at_sec", fallback.get("start_in_next", 0.0)) or 0.0)
    from_at_sec = float(fallback.get("from_at_sec", fallback.get("start_in_prev", cursor_sec)) or cursor_sec)
    transition_id = hashlib.sha1(
        f"eq-band|{getattr(prev_song, 'id', '')}|{getattr(next_song, 'id', '')}|{strategy}|{cursor_sec:.2f}".encode("utf-8")
    ).hexdigest()[:16]

    deck_a = preset["deck_a"]
    deck_b = preset["deck_b"]
    deck_a["song_id"] = getattr(prev_song, "id", None)
    deck_b["song_id"] = getattr(next_song, "id", None)

    label = preset.get("label_zh") or strategy
    plan = {
        **fallback,
        "transition_mode": "eq_band_mix",
        "strategy": strategy,
        "eq_strategy": strategy,
        "eq_mix_user_mode": eq_mix_user_mode or "auto",
        "duration_beats": duration_beats,
        "start": {"type": "next_phrase", "start_after_beats": 0},
        "target": {"song_id": getattr(next_song, "id", None), "start_cue_sec": round(to_at_sec, 3)},
        "deck_a": deck_a,
        "deck_b": deck_b,
        "safety": {
            "headroom_db": -6,
            "limiter_ceiling_db": -1,
            "smooth_ms": 30,
            "fallback_mode": "ordinary_xfade",
        },
        "reason": [
            f"EQ band mix strategy={strategy}, user_mode={eq_mix_user_mode or 'auto'}",
            "使用原始 MP3/PCM 的 Low/Mid/High + fader 曲线，不依赖 stems。",
            "如果 RK 不支持 eq_band_mix，会自动回退普通 xfade。",
        ],
        "prev_mix_profile_v1": prev_profile,
        "next_mix_profile_v1": next_profile,
        # Compatibility fields consumed by existing Flutter/RK fallback paths.
        "rule_key": f"eq_band_mix:{strategy}",
        "rule_label_zh": label,
        "duration_sec": round(fade_sec, 3),
        "fade_sec": round(fade_sec, 3),
        "from_at_sec": round(from_at_sec, 3),
        "to_at_sec": round(to_at_sec, 3),
        "start_in_prev": round(from_at_sec, 3),
        "start_in_next": round(to_at_sec, 3),
        "to_song_id": getattr(next_song, "id", None),
        "style": preset.get("rk_style") or "blend",
        "rk_style": preset.get("rk_style") or "blend",
        "fallback_style": fallback.get("rk_style") or fallback.get("style") or "blend",
        "transition_id": transition_id,
        "target_style": target_style,
    }
    return plan
