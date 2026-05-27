"""Energy-curve sequencer for street-dance DJ sets.

Given a list of songs, sort them according to a chosen energy curve preset
designed for real street-dance scenarios (battle / cypher / class / showcase
/ generic). Each preset defines a target energy curve in [0,1] across the
N slots; the assignment uses a Hungarian-lite greedy match (each slot picks
the unused song closest to its target).

Presets (street-dance authentic):
  - battle_4rounds    : Warmup -> Top 8 -> Top 4 -> Final. Step-wise rises
                        with within-segment small bumps. Classic battle layout
                        (Red Bull BC One, Juste Debout).
  - cypher_circle     : Slow climb, long high plateau, no cool-down. Mirrors
                        a cypher session -- once it's lit, it stays lit.
  - class_choreo      : Warm-up -> teach (medium-flat) -> run-through peaks
                        -> cool-down stretch. Dance studio class workflow.
  - showcase          : Cinematic single arc with a slow build, a mid-set
                        "story" dip, then a final peak.
  - battle_1v1_short  : Aggressive 3-segment punch -- entry, mid-clash,
                        finisher. 2-3 minute 1v1 calls.

Legacy presets retained for backwards compatibility:
  - warmup_to_peak / wave / rise_fall / battle
"""
from __future__ import annotations

import math
from typing import Sequence

from .energy_hiphop import compute_dance_energy


PRESETS = [
    "battle_4rounds",
    "cypher_circle",
    "class_choreo",
    "showcase",
    "battle_1v1_short",
    "warmup_to_peak",
    "wave",
    "rise_fall",
    "battle",
]


PRESET_META: dict[str, dict] = {
    "battle_4rounds": {
        "label_zh": "Battle 四轮制",
        "desc_zh": "暖场 → 8 进 4 → 4 进 2 → 决赛，阶梯上升 + 小起伏。",
        "scene": "battle",
    },
    "cypher_circle": {
        "label_zh": "Cypher 围圈",
        "desc_zh": "缓慢爬升后长时间高原维持，不收尾。",
        "scene": "cypher",
    },
    "class_choreo": {
        "label_zh": "Class / Choreo 课堂",
        "desc_zh": "热身 → 教学中段 → 走整段冲峰 → 拉伸放松。",
        "scene": "class",
    },
    "showcase": {
        "label_zh": "Showcase 表演",
        "desc_zh": "慢起 → 起承转合 → 最高点收尾，影视感节奏。",
        "scene": "showcase",
    },
    "battle_1v1_short": {
        "label_zh": "1v1 短局",
        "desc_zh": "三段递增急速冲峰，适合 2–3 min 单挑。",
        "scene": "battle",
    },
    "warmup_to_peak": {"label_zh": "暖场至峰值", "desc_zh": "单调上升的暖场。", "scene": "generic"},
    "wave": {"label_zh": "波浪", "desc_zh": "两个上升、两个下降。", "scene": "generic"},
    "rise_fall": {"label_zh": "起承转合", "desc_zh": "单段弧形（intro → climax → cool-down）。", "scene": "generic"},
    "battle": {"label_zh": "Battle 高低跳", "desc_zh": "高低能量交替（旧版）。", "scene": "battle"},
}


# --------------------------------------------------------------------------- #
# Target curves
# --------------------------------------------------------------------------- #
def _curve_battle_4rounds(n: int) -> list[float]:
    if n <= 1:
        return [0.5] * n
    bases = [0.30, 0.55, 0.75, 0.90]
    out: list[float] = []
    for i in range(n):
        seg = min(3, int(i * 4 / n))
        seg_start = seg * n / 4
        seg_len = n / 4
        local = (i - seg_start) / max(1.0, seg_len - 1)
        bump = 0.06 * math.sin(math.pi * local)
        out.append(bases[seg] + bump)
    return out


def _curve_cypher_circle(n: int) -> list[float]:
    if n <= 1:
        return [0.7] * n
    out: list[float] = []
    for i in range(n):
        x = i / (n - 1)
        if x < 0.30:
            v = 0.30 + (0.75 - 0.30) * (x / 0.30)
        else:
            v = 0.82 + 0.06 * math.sin(2 * math.pi * (x - 0.30) * 2.5)
        out.append(v)
    return out


def _curve_class_choreo(n: int) -> list[float]:
    if n <= 1:
        return [0.5] * n
    out: list[float] = []
    for i in range(n):
        x = i / (n - 1)
        if x < 0.15:
            v = 0.30 + 0.20 * (x / 0.15)
        elif x < 0.55:
            v = 0.55 + 0.05 * math.sin(math.pi * (x - 0.15) / 0.40 * 3)
        elif x < 0.85:
            v = 0.70 + 0.20 * math.sin(math.pi * (x - 0.55) / 0.30)
        else:
            v = 0.85 - 0.45 * ((x - 0.85) / 0.15)
        out.append(v)
    return out


def _curve_showcase(n: int) -> list[float]:
    if n <= 1:
        return [0.6] * n
    out: list[float] = []
    for i in range(n):
        x = i / (n - 1)
        if x < 0.20:
            v = 0.25 + 0.30 * (x / 0.20) ** 1.2
        elif x < 0.45:
            v = 0.55 + 0.25 * math.sin(math.pi * (x - 0.20) / 0.25)
        elif x < 0.65:
            v = 0.60 - 0.20 * math.sin(math.pi * (x - 0.45) / 0.20)
        else:
            v = 0.45 + 0.55 * ((x - 0.65) / 0.35) ** 0.7
        out.append(v)
    return out


def _curve_battle_1v1(n: int) -> list[float]:
    if n <= 1:
        return [0.7] * n
    out: list[float] = []
    for i in range(n):
        seg = min(2, int(i * 3 / n))
        bases = [0.55, 0.78, 0.95]
        seg_start = seg * n / 3
        local = (i - seg_start) / max(1.0, n / 3 - 1)
        out.append(bases[seg] + 0.05 * local)
    return out


def _curve_warmup_to_peak(n: int) -> list[float]:
    return [0.30 + 0.65 * (i / (n - 1)) for i in range(n)] if n > 1 else [0.5]


def _curve_wave(n: int) -> list[float]:
    return [0.50 + 0.40 * math.sin(2 * math.pi * i / max(1, n - 1) - math.pi / 2) for i in range(n)] if n > 1 else [0.5]


def _curve_rise_fall(n: int) -> list[float]:
    return [0.30 + 0.65 * math.sin(math.pi * i / (n - 1)) for i in range(n)] if n > 1 else [0.5]


def _curve_battle_legacy(n: int) -> list[float]:
    return [0.40 + 0.50 * (0.5 + 0.5 * math.sin(math.pi * i)) if i % 2 == 0 else 0.85 for i in range(n)] if n > 1 else [0.5]


_CURVE_FUNCS = {
    "battle_4rounds": _curve_battle_4rounds,
    "cypher_circle": _curve_cypher_circle,
    "class_choreo": _curve_class_choreo,
    "showcase": _curve_showcase,
    "battle_1v1_short": _curve_battle_1v1,
    "warmup_to_peak": _curve_warmup_to_peak,
    "wave": _curve_wave,
    "rise_fall": _curve_rise_fall,
    "battle": _curve_battle_legacy,
}


def _target_curve(preset: str, n: int) -> list[float]:
    fn = _CURVE_FUNCS.get(preset) or _curve_warmup_to_peak
    return [max(0.05, min(0.99, v)) for v in fn(n)]


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def list_presets() -> list[dict]:
    return [
        {"key": k, **PRESET_META.get(k, {"label_zh": k, "desc_zh": "", "scene": "generic"})}
        for k in PRESETS
    ]


def sequence_songs(songs: Sequence, preset: str = "battle_4rounds") -> list[dict]:
    if preset not in PRESETS:
        preset = "battle_4rounds"
    enriched = []
    for s in songs:
        eb = compute_dance_energy(s)
        enriched.append({"song": s, "energy": eb.total, "breakdown": eb.as_dict()})

    n = len(enriched)
    targets = _target_curve(preset, n)
    remaining = list(range(n))
    result: list[dict] = []
    for slot, tgt in enumerate(targets):
        best_idx = None
        best_cost = None
        for r in remaining:
            cost = abs(enriched[r]["energy"] - tgt)
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best_idx = r
        if best_idx is None:
            break
        s = enriched[best_idx]
        remaining.remove(best_idx)
        result.append({
            "song_id": getattr(s["song"], "id", None),
            "position": slot,
            "target_energy": round(tgt, 4),
            "actual_energy": round(s["energy"], 4),
            "breakdown": {k: round(v, 4) for k, v in s["breakdown"].items()},
        })
    return result
