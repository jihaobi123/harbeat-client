"""Typed use-case facade around behavior-compatible planning engines."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping

from .transition_planner import (
    REQUIRED_AUDIO_FEATURE_SOURCE,
    plan_default_transition,
    plan_fast_cut_transition,
    plan_target_energy_transition,
    plan_target_style_transition,
)


class PlanningMode(str, Enum):
    DEFAULT = "default"
    FAST = "fast"
    ENERGY = "energy"
    STYLE = "style"


@dataclass(frozen=True, slots=True)
class PlanningRequest:
    mode: PlanningMode
    previous_song: Any
    next_song: Any
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TransitionPlanningService:
    engines: Mapping[PlanningMode, Callable[..., dict[str, Any]]] = field(
        default_factory=lambda: {
            PlanningMode.DEFAULT: plan_default_transition,
            PlanningMode.FAST: plan_fast_cut_transition,
            PlanningMode.ENERGY: plan_target_energy_transition,
            PlanningMode.STYLE: plan_target_style_transition,
        }
    )

    def plan(self, request: PlanningRequest) -> dict[str, Any]:
        engine = self.engines.get(request.mode)
        if engine is None:
            raise ValueError(f"planning engine is not registered: {request.mode}")
        plan = engine(request.previous_song, request.next_song, **dict(request.options))
        validate_transition_plan(plan, request.mode)
        return plan


def validate_transition_plan(plan: Mapping[str, Any], mode: PlanningMode) -> None:
    if not isinstance(plan, Mapping):
        raise ValueError("planner returned a non-object plan")
    default = plan.get("default_mix")
    if not isinstance(default, Mapping):
        raise ValueError("transition plan is missing default_mix metadata")
    pair_id = str(plan.get("pair_id") or default.get("pair_id") or "").strip()
    if not pair_id:
        raise ValueError("transition plan is missing pair_id")
    for field_name in ("from_at_sec", "to_at_sec", "duration_sec"):
        value = plan.get(field_name, default.get(field_name))
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
            raise ValueError(f"transition plan has invalid {field_name}")
        if float(value) < 0 or (field_name == "duration_sec" and float(value) <= 0):
            raise ValueError(f"transition plan has invalid {field_name}")
    if mode is not PlanningMode.DEFAULT:
        source = default.get("audio_feature_source")
        if source != REQUIRED_AUDIO_FEATURE_SOURCE:
            raise ValueError("manual transition must use precomputed v2 candidates")
        if any(bool(value) for value in (
            plan.get("degraded"), plan.get("fallback_used"),
            default.get("degraded"), default.get("fallback_used"),
        )):
            raise ValueError("manual transition cannot use degraded or fallback output")
