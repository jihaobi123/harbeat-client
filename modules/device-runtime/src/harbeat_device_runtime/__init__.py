"""Independent device connection and runtime contracts."""

from .endpoint import EndpointError, RkEndpoint
from .operation import OperationRef, OperationStatus
from .state import (
  ConnectionHealth,
  ConnectionProfile,
  DeviceIdentity,
  PlaybackState,
  RuntimeSession,
  parse_health,
  parse_playback,
)

__all__ = [
  "ConnectionHealth",
  "ConnectionProfile",
  "DeviceIdentity",
  "EndpointError",
  "OperationRef",
  "OperationStatus",
  "PlaybackState",
  "RkEndpoint",
  "RuntimeSession",
  "parse_health",
  "parse_playback",
]
