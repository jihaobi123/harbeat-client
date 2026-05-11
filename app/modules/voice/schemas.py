"""Voice command request/response models."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

VoiceIntent = Literal[
    "play",
    "pause",
    "hold",
    "release",
    "next",
    "lift_energy",
    "drop_energy",
    "switch_style",
    "emergency_stop",
    "noop",
]


class VoiceCommandRequest(BaseModel):
    text: str = Field(description="Raw transcribed text (Chinese or English)")
    session_id: Optional[str] = None
    user_id: Optional[int] = None
    language_hint: Literal["auto", "zh", "en"] = "auto"


class VoiceCommandResponse(BaseModel):
    intent: VoiceIntent
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    matched_keywords: list[str] = Field(default_factory=list)
    command_payload: Optional[dict] = None
    action_taken: str = ""
    error: Optional[str] = None
