"""Pure domain routing and explicit wire adapters for physical controls."""

from .domain import ActionKind, InputAction, route_logical_key
from .protocol import encode_audio_trigger

__all__ = ["ActionKind", "InputAction", "encode_audio_trigger", "route_logical_key"]
