"""Explicit renderer policies shared by transition render entry points."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

AUTOMATIC_RENDERER_VERSION = "three_band_default_v9_fast_phase_window"
FAST_CUT_RENDERER_VERSION = "three_band_default_v7_standalone_curve_no_energy_floor"


class RendererKind(str, Enum):
    AUTOMATIC_V9 = "automatic_v9"
    FAST_CUT_V7 = "fast_cut_v7"


@dataclass(frozen=True, slots=True)
class RendererPolicy:
    kind: RendererKind
    version: str
    compatibility_used: bool = False
    reason: str | None = None


def resolve_renderer_policy(default_meta: Mapping[str, Any], plan: Mapping[str, Any]) -> RendererPolicy:
    requested = str(
        default_meta.get("required_renderer_version")
        or default_meta.get("renderer_version")
        or plan.get("required_renderer_version")
        or plan.get("renderer_version")
        or ""
    ).strip()
    if requested == FAST_CUT_RENDERER_VERSION:
        return RendererPolicy(RendererKind.FAST_CUT_V7, FAST_CUT_RENDERER_VERSION)
    if requested == AUTOMATIC_RENDERER_VERSION:
        return RendererPolicy(RendererKind.AUTOMATIC_V9, AUTOMATIC_RENDERER_VERSION)
    if not requested:
        return RendererPolicy(
            RendererKind.AUTOMATIC_V9,
            AUTOMATIC_RENDERER_VERSION,
            compatibility_used=True,
            reason="v0.1_missing_version_default",
        )
    raise ValueError(f"unsupported renderer version: {requested}")
