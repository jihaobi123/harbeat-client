"""Pure command validation for cached default-render execution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class DefaultRenderCommand(str, Enum):
    PREPARE = "prepare_default_render"
    SCHEDULE = "schedule_default_render"
    PLAY_NOW = "default_render_playback"


@dataclass(frozen=True, slots=True)
class ValidatedDefaultRenderCommand:
    command: DefaultRenderCommand
    plan: Mapping[str, Any]
    pair_id: str
    from_song_id: str
    to_song_id: str
    from_at_sec: float
    to_at_sec: float
    duration_sec: float
    min_lead_sec: float | None


def validate_default_render_command(
    command: str,
    plan: Mapping[str, Any],
    *,
    requested_to_song_id: object = None,
    min_lead_sec: object = None,
) -> ValidatedDefaultRenderCommand:
    try:
        kind = DefaultRenderCommand(command)
    except ValueError as exc:
        raise ValueError(f"unsupported default render command: {command}") from exc
    if not isinstance(plan, Mapping):
        raise ValueError("transition plan must be an object")
    default = plan.get("default_mix") if isinstance(plan.get("default_mix"), Mapping) else {}
    pair_id = _required_same("pair_id", plan.get("pair_id"), default.get("pair_id"))
    from_song_id = _required_same("from_song_id", plan.get("from_song_id"), default.get("from_song_id"))
    to_song_id = _required_same("to_song_id", plan.get("to_song_id"), default.get("to_song_id"), requested_to_song_id)
    from_at = _non_negative("from_at_sec", plan.get("from_at_sec", default.get("from_at_sec")))
    to_at = _non_negative("to_at_sec", plan.get("to_at_sec", default.get("to_at_sec")))
    duration = _non_negative("duration_sec", plan.get("duration_sec", default.get("duration_sec")), positive=True)
    lead = None
    if kind is DefaultRenderCommand.SCHEDULE:
        lead = _non_negative("min_lead_sec", 1.5 if min_lead_sec is None else min_lead_sec, positive=True)
    return ValidatedDefaultRenderCommand(kind, plan, pair_id, from_song_id, to_song_id, from_at, to_at, duration, lead)


def _required_same(name: str, *values: object) -> str:
    present = [str(value) for value in values if value not in (None, "")]
    if not present:
        raise ValueError(f"transition plan is missing {name}")
    if len(set(present)) != 1:
        raise ValueError(f"transition plan has conflicting {name}")
    return present[0]


def _non_negative(name: str, value: object, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"transition plan has invalid {name}") from exc
    if not math.isfinite(number) or number < 0 or (positive and number <= 0):
        raise ValueError(f"transition plan has invalid {name}")
    return number
