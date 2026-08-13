"""Independent device connection and runtime contracts."""

from .endpoint import EndpointError, RkEndpoint
from .connection import (
  ConnectionProfileStore,
  ConnectionSnapshot,
  ConnectionTracker,
  FailureKind,
  classify_connection_error,
)
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
  "ConnectionProfileStore",
  "ConnectionSnapshot",
  "ConnectionTracker",
  "ConnectionProfile",
  "DeviceIdentity",
  "EndpointError",
  "FailureKind",
  "OperationRef",
  "OperationStatus",
  "PlaybackState",
  "RkEndpoint",
  "RuntimeSession",
  "classify_connection_error",
  "parse_health",
  "parse_playback",
]
