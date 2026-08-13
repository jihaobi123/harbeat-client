"""Side-effect-free domain rules for HarBeat physical controls."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

SFX_KEYS = frozenset({1, 2, 3, 4, 5})
NAVIGATION_KEYS = frozenset({7, 8, 9})
PAUSE_KEY = 0
VINYL_STOP_PHYSICAL_KEY = 6
VINYL_STOP_SAMPLE_KEY = 3
VOLUME_UP_KEY = 100
VOLUME_DOWN_KEY = 101


class ActionKind(str, Enum):
    AUDIO_TRIGGER = "audio_trigger"
    NAVIGATION_EVENT = "navigation_event"
    VOLUME = "volume"


@dataclass(frozen=True, slots=True)
class InputAction:
    logical_key: int
    kind: ActionKind
    audio_trigger_key: int | None = None
    volume_direction: str | None = None
    notify_edge: bool = True

    def __post_init__(self) -> None:
        if self.kind is ActionKind.AUDIO_TRIGGER:
            if self.audio_trigger_key is None or self.volume_direction is not None:
                raise ValueError("audio action requires only audio_trigger_key")
        elif self.kind is ActionKind.VOLUME:
            if self.volume_direction not in {"+", "-"} or self.audio_trigger_key is not None:
                raise ValueError("volume action requires only '+' or '-' direction")
        elif self.audio_trigger_key is not None or self.volume_direction is not None:
            raise ValueError("navigation action cannot contain audio or volume data")


def route_logical_key(key: int) -> InputAction:
    """Return the single authoritative action for a normalized logical key."""
    if key in SFX_KEYS:
        return InputAction(key, ActionKind.AUDIO_TRIGGER, audio_trigger_key=key)
    if key == VINYL_STOP_PHYSICAL_KEY:
        return InputAction(key, ActionKind.AUDIO_TRIGGER, audio_trigger_key=VINYL_STOP_SAMPLE_KEY)
    if key == PAUSE_KEY:
        return InputAction(key, ActionKind.AUDIO_TRIGGER, audio_trigger_key=PAUSE_KEY)
    if key == VOLUME_UP_KEY:
        return InputAction(key, ActionKind.VOLUME, volume_direction="+")
    if key == VOLUME_DOWN_KEY:
        return InputAction(key, ActionKind.VOLUME, volume_direction="-")
    if key in NAVIGATION_KEYS:
        return InputAction(key, ActionKind.NAVIGATION_EVENT)
    raise ValueError(f"unsupported logical key: {key}")
