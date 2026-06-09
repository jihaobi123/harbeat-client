"""Preset EQ/fader envelopes for MP3-based DJ band mixing."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


EQ_STRATEGIES = {
    "smooth_blend",
    "soft_bass_swap",
    "hard_bass_swap",
    "vocal_safe",
    "filter_sweep",
}

USER_MODE_TO_STRATEGY = {
    "smooth": "smooth_blend",
    "rhythm": "hard_bass_swap",
    "vocal_safe": "vocal_safe",
    "filter": "filter_sweep",
}


_PRESETS: dict[str, dict[str, Any]] = {
    "smooth_blend": {
        "label_zh": "丝滑频段融合",
        "duration_beats": 32,
        "rk_style": "blend",
        "deck_a": {
            "fader": [[0, 1.0], [24, 0.70], [32, 0.0]],
            "eq": {
                "low": [[0, 0], [20, 0], [28, -9], [32, -18]],
                "mid": [[0, 0], [20, -3], [32, -18]],
                "high": [[0, 0], [16, -3], [32, -15]],
            },
            "filter": None,
            "fx": None,
        },
        "deck_b": {
            "fader": [[0, 0.0], [8, 0.25], [24, 0.78], [32, 1.0]],
            "eq": {
                "low": [[0, -18], [18, -12], [28, -3], [32, 0]],
                "mid": [[0, -9], [16, -4], [32, 0]],
                "high": [[0, -6], [8, -2], [16, 0]],
            },
            "filter": None,
            "fx": None,
        },
    },
    "soft_bass_swap": {
        "label_zh": "软低频换底",
        "duration_beats": 32,
        "rk_style": "bass_swap",
        "deck_a": {
            "fader": [[0, 1.0], [24, 0.82], [32, 0.0]],
            "eq": {
                "low": [[0, 0], [20, 0], [28, -12], [32, -24]],
                "mid": [[0, 0], [20, -3], [32, -18]],
                "high": [[0, 0], [24, -3], [32, -12]],
            },
            "filter": None,
            "fx": None,
        },
        "deck_b": {
            "fader": [[0, 0.0], [8, 0.30], [24, 0.80], [32, 1.0]],
            "eq": {
                "low": [[0, -24], [20, -18], [28, -6], [32, 0]],
                "mid": [[0, -12], [16, -6], [32, 0]],
                "high": [[0, -8], [8, -3], [16, 0]],
            },
            "filter": None,
            "fx": None,
        },
    },
    "hard_bass_swap": {
        "label_zh": "强节奏低频换底",
        "duration_beats": 32,
        "rk_style": "bass_swap",
        "deck_a": {
            "fader": [[0, 1.0], [24, 0.75], [32, 0.0]],
            "eq": {
                "low": [[0, 0], [24, 0], [28, -12], [32, -60]],
                "mid": [[0, 0], [16, -3], [28, -12], [32, -60]],
                "high": [[0, 0], [20, -3], [32, -60]],
            },
            "filter": None,
            "fx": None,
        },
        "deck_b": {
            "fader": [[0, 0.0], [8, 0.35], [24, 0.75], [32, 1.0]],
            "eq": {
                "low": [[0, -60], [24, -60], [28, -9], [32, 0]],
                "mid": [[0, -15], [16, -6], [32, 0]],
                "high": [[0, -9], [8, -3], [16, 0]],
            },
            "filter": None,
            "fx": None,
        },
    },
    "vocal_safe": {
        "label_zh": "人声保护衔接",
        "duration_beats": 32,
        "rk_style": "vocal_ducking",
        "deck_a": {
            "fader": [[0, 1.0], [20, 0.85], [32, 0.0]],
            "eq": {
                "low": [[0, 0], [24, -8], [32, -24]],
                "mid": [[0, 0], [12, -2], [24, -10], [32, -30]],
                "high": [[0, 0], [24, -3], [32, -18]],
            },
            "filter": None,
            "fx": None,
        },
        "deck_b": {
            "fader": [[0, 0.0], [12, 0.25], [24, 0.70], [32, 1.0]],
            "eq": {
                "low": [[0, -18], [20, -10], [32, 0]],
                "mid": [[0, -18], [20, -12], [28, -4], [32, 0]],
                "high": [[0, -6], [8, -2], [16, 0]],
            },
            "filter": None,
            "fx": None,
        },
    },
    "filter_sweep": {
        "label_zh": "扫频打开",
        "duration_beats": 32,
        "rk_style": "filter",
        "deck_a": {
            "fader": [[0, 1.0], [20, 0.78], [32, 0.0]],
            "eq": {
                "low": [[0, 0], [20, -6], [32, -24]],
                "mid": [[0, 0], [20, -4], [32, -18]],
                "high": [[0, 0], [16, -6], [32, -24]],
            },
            "filter": {"type": "lowpass", "cutoff_hz": [[0, 18000], [32, 350]]},
            "fx": None,
        },
        "deck_b": {
            "fader": [[0, 0.0], [8, 0.25], [24, 0.80], [32, 1.0]],
            "eq": {
                "low": [[0, -18], [24, -8], [32, 0]],
                "mid": [[0, -10], [16, -4], [32, 0]],
                "high": [[0, -12], [8, -6], [20, 0]],
            },
            "filter": {"type": "highpass", "cutoff_hz": [[0, 900], [32, 30]]},
            "fx": None,
        },
    },
}


def preset_for_strategy(strategy: str) -> dict[str, Any]:
    return deepcopy(_PRESETS.get(strategy) or _PRESETS["smooth_blend"])


def strategy_for_user_mode(mode: str | None, *, auto_strategy: str) -> str:
    raw = (mode or "auto").strip().lower()
    if raw == "auto":
        return auto_strategy if auto_strategy in EQ_STRATEGIES else "smooth_blend"
    return USER_MODE_TO_STRATEGY.get(raw, auto_strategy)
