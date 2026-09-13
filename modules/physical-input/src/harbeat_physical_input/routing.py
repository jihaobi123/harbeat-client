"""Compatibility imports for the v0.1 public module path.

New code should import domain rules and protocol adapters from the package
root. This facade remains explicit until deployed adapters migrate.
"""

from .domain import InputAction, route_logical_key
from .protocol import encode_audio_trigger

__all__ = ["InputAction", "encode_audio_trigger", "route_logical_key"]
