"""EQ-band envelope generation for the 5 automatic DJ mixer strategies.

The source package expresses band curves as linear keep ratios. RK's
``envelope_runner`` expects EQ values in dB, so this module converts ratios to
dB before plans leave Jetson.
"""

from __future__ import annotations

import math
from typing import Any, Callable


class MixingStrategyParams:
    """Strategy durations and curve parameters from ``dj_mixer_package``."""

    @staticmethod
    def get_strategy_params(strategy_num: int, fade_sec: float | None = None) -> dict[str, Any]:
        if strategy_num == 1:
            return {
                "fade_sec": 16.0,
                "bass_switch_point": 0.6,
                "mid_out_threshold": 0.9,
                "mid_in_threshold": 0.3,
                "high_out_exp": 0.8,
                "high_in_exp": 0.7,
                "description": "vocal valley with 60 percent bass handoff",
            }
        if strategy_num == 2:
            return {
                "fade_sec": 24.0,
                "bass_switch_point": 0.4,
                "mid_out_threshold": 0.8,
                "mid_in_threshold": 0.5,
                "high_out_exp": 1.2,
                "high_in_exp": 0.5,
                "description": "energy lift with early bass handoff",
            }
        if strategy_num == 3:
            return {
                "fade_sec": 28.0,
                "bass_switch_point": 0.65,
                "mid_out_keep_ratio": 0.5,
                "mid_in_start_ratio": 0.15,
                "high_out_exp": 0.7,
                "high_in_exp": 1.2,
                "description": "energy downshift with vocal-safe mid handling",
            }
        if strategy_num == 4:
            return {
                "fade_sec": 20.0,
                "bass_switch_point": 0.6,
                "mid_out_threshold": 0.9,
                "mid_in_threshold": 0.3,
                "high_out_exp": 0.8,
                "high_in_exp": 0.7,
                "description": "BPM/key difference handling with standard EQ handoff",
            }
        if strategy_num == 5:
            return {
                "fade_sec": 32.0,
                "bass_gap_start": 0.45,
                "bass_gap_end": 0.55,
                "mid_switch_point": 0.5,
                "high_out_exp": 0.5,
                "high_in_exp": 2.0,
                "description": "cross-style overlap with controlled bass gap",
            }
        return MixingStrategyParams.get_strategy_params(1, fade_sec)


def generate_eq_band_envelopes(strategy_num: int, fade_sec: float | None = None) -> dict[str, Any]:
    """Generate RK-ready deck curves for a package strategy number."""
    params = MixingStrategyParams.get_strategy_params(strategy_num, fade_sec)
    resolved_fade = float(params["fade_sec"])
    if strategy_num == 2:
        ratios = _strategy2_ratios(params, resolved_fade)
    elif strategy_num == 3:
        ratios = _strategy3_ratios(params, resolved_fade)
    elif strategy_num == 4:
        ratios = _strategy1_ratios(params, resolved_fade)
    elif strategy_num == 5:
        ratios = _strategy5_ratios(params, resolved_fade)
    else:
        ratios = _strategy1_ratios(params, resolved_fade)
    return _ratios_to_rk_decks(ratios, resolved_fade)


def _strategy1_ratios(params: dict[str, Any], fade_sec: float) -> dict[str, list[float]]:
    xs = _linspace(fade_sec)
    bs = float(params["bass_switch_point"])
    mot = float(params["mid_out_threshold"])
    mit = float(params["mid_in_threshold"])
    return {
        "a_low": [1.0 - b for b in [
            x / bs * 0.3 if x < bs else 0.3 + (x - bs) / (1.0 - bs) * 0.7
            for x in xs
        ]],
        "b_low": [
            x / bs * 0.3 if x < bs else 0.3 + (x - bs) / (1.0 - bs) * 0.7
            for x in xs
        ],
        "a_mid": [
            1.0 - (x / mot * 0.75) if x < mot else 0.25 * _pow(1.0 - (x - mot) / (1.0 - mot), 1.5)
            for x in xs
        ],
        "b_mid": [_piecewise_mid_in(x, mit, first=0.10, second=0.15, third=0.40) for x in xs],
        "a_high": [1.0 - _pow(x, float(params["high_out_exp"])) for x in xs],
        "b_high": [_pow(x, float(params["high_in_exp"])) for x in xs],
    }


def _strategy2_ratios(params: dict[str, Any], fade_sec: float) -> dict[str, list[float]]:
    xs = _linspace(fade_sec)
    bs = float(params["bass_switch_point"])
    mot = float(params["mid_out_threshold"])
    return {
        "a_low": [1.0 - b for b in [
            x / bs * 0.2 if x < bs else 0.2 + (x - bs) / (1.0 - bs) * 0.8
            for x in xs
        ]],
        "b_low": [
            x / bs * 0.2 if x < bs else 0.2 + (x - bs) / (1.0 - bs) * 0.8
            for x in xs
        ],
        "a_mid": [
            1.0 - (x / mot * 0.6) if x < mot else 0.4 * _pow(1.0 - (x - mot) / (1.0 - mot), 2.0)
            for x in xs
        ],
        "b_mid": [
            0.05 + 0.1 * (x / 0.5)
            if x < 0.5
            else 0.15 + (x - 0.5) / 0.25 * 0.35
            if x < 0.75
            else 0.5 + (x - 0.75) / 0.25 * 0.5
            for x in xs
        ],
        "a_high": [1.0 - _pow(x, float(params["high_out_exp"])) for x in xs],
        "b_high": [_pow(x, float(params["high_in_exp"])) for x in xs],
    }


def _strategy3_ratios(params: dict[str, Any], fade_sec: float) -> dict[str, list[float]]:
    xs = _linspace(fade_sec)
    bs = float(params["bass_switch_point"])
    return {
        "a_low": [1.0 - b for b in [
            x / bs * 0.25 if x < bs else 0.25 + (x - bs) / (1.0 - bs) * 0.75
            for x in xs
        ]],
        "b_low": [
            x / bs * 0.25 if x < bs else 0.25 + (x - bs) / (1.0 - bs) * 0.75
            for x in xs
        ],
        "a_mid": [
            1.0 - (x / 0.8 * 0.5) if x < 0.8 else 0.5 * _pow(1.0 - (x - 0.8) / 0.2, 2.0)
            for x in xs
        ],
        "b_mid": [
            0.15 + 0.1 * (x / 0.4)
            if x < 0.4
            else 0.25 + (x - 0.4) / 0.3 * 0.25
            if x < 0.7
            else 0.5 + (x - 0.7) / 0.3 * 0.5
            for x in xs
        ],
        "a_high": [1.0 - _pow(x, float(params["high_out_exp"])) for x in xs],
        "b_high": [_pow(x, float(params["high_in_exp"])) for x in xs],
    }


def _strategy5_ratios(params: dict[str, Any], fade_sec: float) -> dict[str, list[float]]:
    xs = _linspace(fade_sec)
    gap_start = float(params["bass_gap_start"])
    gap_end = float(params["bass_gap_end"])
    switch = float(params["mid_switch_point"])

    def a_low(x: float) -> float:
        if x < gap_start:
            return 1.0 - (x / gap_start * 0.9)
        if x < gap_end:
            return 0.1
        return 0.1 * (1.0 - (x - gap_end) / (1.0 - gap_end))

    def b_low(x: float) -> float:
        if x < gap_start:
            return x / gap_start * 0.1
        if x < gap_end:
            return 0.1
        return 0.1 + (x - gap_end) / (1.0 - gap_end) * 0.9

    return {
        "a_low": [a_low(x) for x in xs],
        "b_low": [b_low(x) for x in xs],
        "a_mid": [
            1.0 - (x / switch * 0.8) if x < switch else 0.2 * _pow(1.0 - (x - switch) / (1.0 - switch), 3.0)
            for x in xs
        ],
        "b_mid": [
            0.05 * _pow(x / switch, 3.0) if x < switch else 0.05 + (x - switch) / (1.0 - switch) * 0.95
            for x in xs
        ],
        "a_high": [1.0 - _pow(x, float(params["high_out_exp"])) for x in xs],
        "b_high": [_pow(x, float(params["high_in_exp"])) for x in xs],
    }


def _ratios_to_rk_decks(ratios: dict[str, list[float]], fade_sec: float) -> dict[str, Any]:
    count = max(len(v) for v in ratios.values())
    times = [round(i * fade_sec / max(1, count - 1), 3) for i in range(count)]

    def curve(key: str) -> list[list[float]]:
        values = ratios[key]
        return [[times[i], _ratio_to_db(values[i])] for i in range(min(count, len(values)))]

    return {
        "deck_a": {
            "fader": _unity_fader(times),
            "eq": {
                "low": curve("a_low"),
                "mid": curve("a_mid"),
                "high": curve("a_high"),
            },
            "filter": None,
            "fx": None,
        },
        "deck_b": {
            "fader": _unity_fader(times),
            "eq": {
                "low": curve("b_low"),
                "mid": curve("b_mid"),
                "high": curve("b_high"),
            },
            "filter": None,
            "fx": None,
        },
    }


def _linspace(fade_sec: float) -> list[float]:
    count = max(8, int(round(fade_sec * 10.0)))
    return [i / max(1, count - 1) for i in range(count)]


def _unity_fader(times: list[float]) -> list[list[float]]:
    return [[t, 1.0] for t in times]


def _piecewise_mid_in(x: float, mit: float, *, first: float, second: float, third: float) -> float:
    if x < mit:
        return first + 0.05 * (x / max(0.001, mit))
    if x < 0.6:
        return second + (x - mit) / max(0.001, 0.6 - mit) * 0.25
    return third + (x - 0.6) / 0.4 * 0.6


def _ratio_to_db(value: float) -> float:
    ratio = max(0.001, min(1.0, float(value)))
    return round(max(-60.0, min(0.0, 20.0 * math.log10(ratio))), 3)


def _pow(value: float, exponent: float) -> float:
    return math.pow(max(0.0, min(1.0, value)), exponent)
