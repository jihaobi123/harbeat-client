"""Preset EQ/fader envelopes for MP3-based DJ band mixing."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


EQ_STRATEGIES = {
    "standard_blend",
    "energy_lift",
    "energy_drop",
    "tempo_compat",
    "cross_style",
}

USER_MODE_TO_STRATEGY = {
    "smooth": "standard_blend",
    "standard": "standard_blend",
    "rhythm": "tempo_compat",
    "tempo": "tempo_compat",
    "vocal_safe": "energy_drop",
    "filter": "energy_lift",
    "energy_up": "energy_lift",
    "energy_down": "energy_drop",
    "overlap": "cross_style",
    "cross_style": "cross_style",
}


_PRESETS: dict[str, dict[str, Any]] = {
    "standard_blend": {
        "label_zh": "策略1 标准频段融合",
        "duration_beats": 16,
        "rk_style": "eq_band_mix",
    },
    "energy_lift": {
        "label_zh": "策略2 能量递增",
        "duration_beats": 24,
        "rk_style": "eq_band_mix",
    },
    "energy_drop": {
        "label_zh": "策略3 能量递减",
        "duration_beats": 28,
        "rk_style": "eq_band_mix",
    },
    "tempo_compat": {
        "label_zh": "策略4 BPM差异兼容",
        "duration_beats": 20,
        "rk_style": "eq_band_mix",
    },
    "cross_style": {
        "label_zh": "策略5 风格跨界",
        "duration_beats": 32,
        "rk_style": "eq_band_mix",
    },
}


def preset_for_strategy(strategy: str) -> dict[str, Any]:
    return deepcopy(_PRESETS.get(strategy) or _PRESETS["standard_blend"])


def strategy_for_user_mode(mode: str | None, *, auto_strategy: str) -> str:
    raw = (mode or "auto").strip().lower()
    if raw == "auto":
        return auto_strategy if auto_strategy in EQ_STRATEGIES else "standard_blend"
    return USER_MODE_TO_STRATEGY.get(raw, auto_strategy)
