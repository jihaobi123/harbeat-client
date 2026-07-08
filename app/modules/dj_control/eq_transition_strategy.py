"""Generate MP3-only DJ EQ band mix transition plans."""

from __future__ import annotations

import hashlib
from typing import Any

from app.modules.dj_control import mixer_rules
from app.modules.dj_control.auto_mixer.feature_analyzer import FeatureAnalyzer
from app.modules.dj_control.auto_mixer.mixing_strategies import (
    MixingStrategyParams,
    generate_eq_band_envelopes,
)
from app.modules.dj_control.auto_mixer.strategy_selector import StrategySelector
from app.modules.dj_control.eq_transition_presets import preset_for_strategy
from app.modules.dj_control.mix_profile import build_mix_profile


def generate_eq_band_mix_transition(
    prev_song: Any,
    next_song: Any,
    *,
    from_at_sec: float,
    to_at_sec: float,
    strategy_num: int,
    strategy_name: str,
    selection_reason: str | None = None,
    features1: dict[str, float] | None = None,
    features2: dict[str, float] | None = None,
    transition_mode: str = "eq_band_mix",
    eq_mix_user_mode: str | None = "auto",
    fallback: dict[str, Any] | None = None,
    rule_key_prefix: str | None = None,
    target_style: str | None = None,
    transition_seed: str | None = None,
) -> dict[str, Any]:
    """Build a full RK-compatible EQ-band plan from a selected package strategy."""
    params = MixingStrategyParams.get_strategy_params(strategy_num)
    fade_sec = float(params["fade_sec"])
    envelopes = generate_eq_band_envelopes(strategy_num, fade_sec)
    preset = preset_for_strategy(strategy_name)
    fallback = dict(fallback or {})
    prev_id = _song_id(prev_song)
    next_id = _song_id(next_song)

    deck_a = dict(envelopes["deck_a"])
    deck_b = dict(envelopes["deck_b"])
    deck_a["song_id"] = prev_id
    deck_b["song_id"] = next_id

    prefix = rule_key_prefix or transition_mode
    transition_id = hashlib.sha1(
        (
            transition_seed
            or f"{prefix}|{prev_id}|{next_id}|{strategy_num}|{from_at_sec:.2f}|{to_at_sec:.2f}|{fade_sec:.2f}"
        ).encode("utf-8")
    ).hexdigest()[:16]
    selection = {
        "strategy_num": strategy_num,
        "strategy_name": strategy_name,
        "reason": selection_reason or params["description"],
        "features1": features1 or FeatureAnalyzer.extract_features(prev_song),
        "features2": features2 or FeatureAnalyzer.extract_features(next_song),
        "duration_sec": fade_sec,
        "duration_beats": int(round(fade_sec)),
        "curve_units": "rk_db",
        "source": "dj_mixer_package",
    }
    label = preset.get("label_zh") or strategy_name
    plan = {
        **fallback,
        "transition_mode": transition_mode,
        "execution_mode": "eq_band_mix",
        "strategy": strategy_name,
        "eq_strategy": strategy_name,
        "strategy_num": strategy_num,
        "eq_mix_user_mode": eq_mix_user_mode or "auto",
        # RK uses this field as the curve x-axis end. Keep it aligned to seconds.
        "duration_beats": int(round(fade_sec)),
        "duration_sec": round(fade_sec, 3),
        "fade_sec": round(fade_sec, 3),
        "from_at_sec": round(float(from_at_sec), 3),
        "to_at_sec": round(float(to_at_sec), 3),
        "start_in_prev": round(float(from_at_sec), 3),
        "start_in_next": round(float(to_at_sec), 3),
        "to_song_id": next_id,
        "target": {"song_id": next_id, "start_cue_sec": round(float(to_at_sec), 3)},
        "deck_a": deck_a,
        "deck_b": deck_b,
        "safety": {
            "headroom_db": 0,
            "limiter_ceiling_db": -1,
            "smooth_ms": 30,
            "fallback_mode": "ordinary_xfade",
        },
        "reason": [
            f"AutoMixer selected strategy {strategy_num}={strategy_name}: {selection['reason']}",
            "使用本地 MP3/PCM 的 Low/Mid/High dB 自动化，不依赖 Spotify API 或 stems。",
            "EQ 曲线来自 dj_mixer_package，并已转换为 RK dB 语义。",
        ],
        "rule_key": f"{prefix}:{strategy_name}",
        "rule_label_zh": label,
        "style": preset.get("rk_style") or "blend",
        "rk_style": preset.get("rk_style") or "blend",
        "fallback_style": fallback.get("rk_style") or fallback.get("style") or "blend",
        "transition_id": transition_id,
        "target_style": target_style,
        "auto_strategy_selection": selection,
        "strategy_description": params["description"],
    }
    return plan


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
    features1 = FeatureAnalyzer.extract_features(_feature_payload(prev_song, prev_profile))
    features2 = FeatureAnalyzer.extract_features(_feature_payload(next_song, next_profile))
    strategy_num, strategy, selection_reason = StrategySelector.select(
        features1,
        features2,
        user_strategy=eq_mix_user_mode,
    )
    fade_sec = float(MixingStrategyParams.get_strategy_params(strategy_num)["fade_sec"])
    fallback = mixer_rules.build_transition_spec(
        prev_song,
        next_song,
        cursor_sec,
        rule_key,
        forced_fade_sec=fade_sec,
    )
    to_at_sec = float(fallback.get("to_at_sec", fallback.get("start_in_next", 0.0)) or 0.0)
    from_at_sec = float(fallback.get("from_at_sec", fallback.get("start_in_prev", cursor_sec)) or cursor_sec)
    plan = generate_eq_band_mix_transition(
        prev_song,
        next_song,
        from_at_sec=from_at_sec,
        to_at_sec=to_at_sec,
        strategy_num=strategy_num,
        strategy_name=strategy,
        selection_reason=selection_reason,
        features1=features1,
        features2=features2,
        transition_mode="eq_band_mix",
        eq_mix_user_mode=eq_mix_user_mode,
        fallback=fallback,
        rule_key_prefix="eq_band_mix",
        target_style=target_style,
        transition_seed=f"eq-band|{_song_id(prev_song)}|{_song_id(next_song)}|{strategy}|{cursor_sec:.2f}",
    )
    plan["start"] = {"type": "next_phrase", "start_after_beats": 0}
    plan["prev_mix_profile_v1"] = prev_profile
    plan["next_mix_profile_v1"] = next_profile
    return plan


def _feature_payload(song: Any, profile: dict[str, Any]) -> dict[str, Any]:
    music_features = _get(song, "music_features") or {}
    dj_features = _get(music_features, "dj") if isinstance(music_features, dict) else {}
    return {
        "bpm": _get(song, "bpm") or profile.get("bpm"),
        "energy": _get(song, "energy"),
        "phrase_map": _get(song, "phrase_map"),
        "music_features": music_features,
        "loudness_profile": _get(song, "loudness_profile") or {},
        "genre_profile": _get(song, "genre_profile") or {},
        "stem_activity": _get(song, "stem_activity") or {},
        "bass_risk_windows": _get(song, "bass_risk_windows") or [],
        "vocal_events": _get(song, "vocal_events") or [],
        "low_ratio": _curve_avg((profile.get("band_energy") or {}).get("low_curve")) or _get(dj_features, "low_ratio"),
        "mid_ratio": _curve_avg((profile.get("band_energy") or {}).get("mid_curve")) or _get(dj_features, "mid_ratio"),
        "high_ratio": _curve_avg((profile.get("band_energy") or {}).get("high_curve")) or _get(dj_features, "high_ratio"),
    }


def _curve_avg(curve: Any) -> float | None:
    if not isinstance(curve, list) or not curve:
        return None
    vals: list[float] = []
    for item in curve:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                vals.append(float(item[1]))
            except (TypeError, ValueError):
                continue
    return sum(vals) / len(vals) if vals else None


def _song_id(song: Any) -> Any:
    return _get(song, "id") or _get(song, "song_id")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
