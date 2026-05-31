"""C6 Session Orchestration — the system's central coordinator.

Responsibilities:
  - Session state machine (warmup → build → peak → recover → close)
  - Track queue buffer (always 2-3 candidates preloaded)
  - Safety pool (10-20 "can't go wrong" fallback tracks)
  - Undo/redo stack (max 10 actions, all non-emergency actions reversible)
  - Button quantization (execute at next bar/phrase boundary)
  - Coordinator: wires C3 (recommendation) ↔ C4 (playback) ↔ C5 (interaction)

Module boundary:
  - C6 reads C1 data (TrackAnalysis) — READ ONLY
  - C6 queries C3 for candidate tracks
  - C6 sends commands to C4 for playback execution
  - C6 receives intents from C5 (buttons/UI)
  - C6 does NOT import internal implementations of C1/C3/C4
"""

from .coordinator import SessionCoordinator
from .queue_manager import QueueManager
from .safety_pool import SafetyPool
from .schemas import (
    ButtonIntent,
    Candidate,
    CandidateList,
    ControlCommand,
    SafetyPoolConfig,
    SceneConfig,
    SessionConfig,
    SessionSnapshot,
    SessionState,
    UndoableAction,
)
from .state_machine import SessionStateMachine
from .undo_stack import UndoStack

__all__ = [
    "SessionCoordinator",
    "SessionStateMachine",
    "QueueManager",
    "SafetyPool",
    "UndoStack",
    "SessionState",
    "SessionConfig",
    "SceneConfig",
    "SessionSnapshot",
    "ButtonIntent",
    "Candidate",
    "CandidateList",
    "ControlCommand",
    "SafetyPoolConfig",
    "UndoableAction",
]
