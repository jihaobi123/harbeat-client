"""
Live DJ Control models — Pydantic schemas for /live/override and /live/intent.

Copy to: /home/cat/cypher/edge-agent/edge_agent/live_models.py
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TransitionDetail(BaseModel):
    """Detailed info about the next upcoming transition."""
    to_song_id: str = ""
    style: str = "blend"
    starts_in_sec: float = 0.0
    confidence: float = 0.0
    tags: list[str] = Field(default_factory=list)


class LiveOverrideRequest(BaseModel):
    """Force-override the next transition parameters."""
    next_song_id: str | None = None
    style: str | None = None
    fade_sec: float | None = Field(default=None, ge=0.5, le=30.0)
    execute: Literal["now", "next_beat", "next_bar", "next_phrase"] = "next_phrase"


class LiveOverrideResponse(BaseModel):
    ok: bool = True
    transition: TransitionDetail = Field(default_factory=TransitionDetail)
    warnings: list[str] = Field(default_factory=list)


class LiveIntentRequest(BaseModel):
    """High-level DJ intent — system replans within constraints."""
    intent: Literal[
        "energy_up", "energy_down", "hold_energy", "drop_now",
        "cooldown", "smoother", "harder", "safer",
        "vocal_safe", "instrumental",
    ]
    scope: Literal["next_transition", "next_3"] = "next_transition"
    max_risk: float = Field(default=0.45, ge=0.0, le=1.0)


class LiveIntentResponse(BaseModel):
    ok: bool = True
    updated_plan: dict[str, Any] | None = None
    explanation: str | None = None
    warnings: list[str] = Field(default_factory=list)
