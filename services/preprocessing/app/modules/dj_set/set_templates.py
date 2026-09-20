"""Set Templates — 5 distinct DJ narratives.

A template is **what kind of set** the optimizer is trying to build.
Each template defines:

  - role_skeleton    : ordered list of expected role slots
  - energy_curve_fn  : f(progress 0..1) -> target dance_energy 0..1
  - peak_count       : how many peaks the set should have
  - reset_count      : how many resets after peaks
  - vocal_balance    : target average vocal_density (0..1)
  - allowed_risk     : highest risk_level allowed at edges (A/B/C)
  - description      : human-readable

Five templates:
  smooth          稳态 groove，能量曲线平稳，少 peak
  build           缓慢上扬，最后大爆发
  cypher_wave     波浪状 — peak / reset / peak / reset
  battle_peak     高能 weapon 密集，适合 battle / cypher
  clean_vocal     vocal_moment 主导，适合暖场或人声专场

Templates do NOT pick songs. They give the optimizer a target shape.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class SetTemplate:
    name: str
    description: str
    role_skeleton: tuple[str, ...]
    peak_count: int
    reset_count: int
    vocal_balance: float
    allowed_risk: str  # 'A' | 'B' | 'C'
    energy_curve_fn: Callable[[float], float]
    weight_overrides: dict[str, float] = field(default_factory=dict)

    def target_energy(self, progress: float) -> float:
        return float(max(0.0, min(1.0, self.energy_curve_fn(max(0.0, min(1.0, progress))))))

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "role_skeleton": list(self.role_skeleton),
            "peak_count": self.peak_count,
            "reset_count": self.reset_count,
            "vocal_balance": self.vocal_balance,
            "allowed_risk": self.allowed_risk,
            "weight_overrides": dict(self.weight_overrides),
        }


# ----- Energy curve primitives -------------------------------------------

def _smooth_curve(p: float) -> float:
    # Plateau around 0.55, gentle rise to 0.65, drop to 0.50 at the end
    if p < 0.15:
        return 0.45 + 0.10 * (p / 0.15)
    if p < 0.80:
        return 0.55 + 0.10 * ((p - 0.15) / 0.65)
    return 0.65 - 0.15 * ((p - 0.80) / 0.20)


def _build_curve(p: float) -> float:
    # Slow ramp from 0.40 to 0.85, drop to 0.55 at the very end
    if p < 0.85:
        return 0.40 + 0.45 * (p / 0.85)
    return 0.85 - 0.30 * ((p - 0.85) / 0.15)


def _wave_curve(p: float) -> float:
    # Two crests + two troughs across the set
    import math
    base = 0.55 + 0.25 * math.sin(p * math.pi * 2.0 - math.pi / 2)
    return float(base)


def _battle_curve(p: float) -> float:
    # Stays above 0.70 most of the time; quick reset valleys at 0.4 and 0.7
    if 0.35 < p < 0.45:
        return 0.55
    if 0.70 < p < 0.78:
        return 0.55
    if p < 0.10:
        return 0.55 + 0.20 * (p / 0.10)
    if p > 0.92:
        return 0.85 - 0.30 * ((p - 0.92) / 0.08)
    return 0.80


def _clean_vocal_curve(p: float) -> float:
    # Mid-warm energy, gentle bell shape with vocal-friendly middle
    if p < 0.20:
        return 0.45 + 0.15 * (p / 0.20)
    if p < 0.70:
        return 0.60 + 0.05 * ((p - 0.20) / 0.50)
    return 0.65 - 0.20 * ((p - 0.70) / 0.30)


# ----- Templates ----------------------------------------------------------

SMOOTH = SetTemplate(
    name="smooth",
    description="稳态 groove。能量曲线平稳，少 peak，重点是 groove 连续 + vocal 节奏感。",
    role_skeleton=("opener", "groove_holder", "groove_holder", "vocal_moment", "groove_holder", "closer"),
    peak_count=1,
    reset_count=1,
    vocal_balance=0.55,
    allowed_risk="B",
    energy_curve_fn=_smooth_curve,
    weight_overrides={"groove_continuity": 0.20, "energy_arch_fit": 0.10},
)

BUILD = SetTemplate(
    name="build",
    description="缓慢上扬，最后大爆发。前半段 builder + groove，后段直接拉到 peak。",
    role_skeleton=("opener", "groove_holder", "builder", "builder", "peak", "closer"),
    peak_count=2,
    reset_count=1,
    vocal_balance=0.50,
    allowed_risk="B",
    energy_curve_fn=_build_curve,
    weight_overrides={"energy_arch_fit": 0.20, "narrative_fit": 0.25},
)

CYPHER_WAVE = SetTemplate(
    name="cypher_wave",
    description="波浪状 — peak / reset / peak / reset。适合 cypher 多次 round。",
    role_skeleton=("opener", "builder", "peak", "reset", "builder", "peak", "reset", "closer"),
    peak_count=2,
    reset_count=2,
    vocal_balance=0.50,
    allowed_risk="B",
    energy_curve_fn=_wave_curve,
    weight_overrides={"peak_reset_balance": 0.20},
)

BATTLE_PEAK = SetTemplate(
    name="battle_peak",
    description="battle 高能流，weapon + peak 密集，少量 reset 透气。",
    role_skeleton=("opener", "builder", "peak", "weapon", "reset", "peak", "weapon", "closer"),
    peak_count=3,
    reset_count=1,
    vocal_balance=0.40,
    allowed_risk="C",  # 高能流允许冒一点险
    energy_curve_fn=_battle_curve,
    weight_overrides={"track_role_fit": 0.15, "diversity": 0.10},
)

CLEAN_VOCAL = SetTemplate(
    name="clean_vocal",
    description="vocal_moment 主导。暖场或人声专场，能量保持中段。",
    role_skeleton=("opener", "vocal_moment", "groove_holder", "vocal_moment", "builder", "vocal_moment", "closer"),
    peak_count=1,
    reset_count=1,
    vocal_balance=0.70,
    allowed_risk="B",
    energy_curve_fn=_clean_vocal_curve,
    weight_overrides={"vocal_flow": 0.15},
)


ALL_TEMPLATES: tuple[SetTemplate, ...] = (
    SMOOTH, BUILD, CYPHER_WAVE, BATTLE_PEAK, CLEAN_VOCAL,
)


def get_template(name: str) -> SetTemplate | None:
    for t in ALL_TEMPLATES:
        if t.name == name:
            return t
    return None
