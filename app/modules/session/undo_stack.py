"""C6 Undo stack — reversible action history for session safety.

All non-emergency actions are pushed to the stack before execution.
Undo restores the previous state (track + position + session state).
Emergency actions skip the stack (cannot be undone — by design).
"""

from __future__ import annotations

import logging
import time
from collections import deque

from .schemas import SessionState, UndoableAction

logger = logging.getLogger(__name__)

# Actions that CAN be undone
UNDOABLE_ACTIONS = {
    "next", "energy_up", "energy_down", "style_change",
    "hold", "loop", "pause",
}

# Actions that CANNOT be undone (emergency / destructive)
NON_UNDOABLE_ACTIONS = {
    "emergency_next", "close", "talkover",
}


class UndoStack:
    """Bounded undo stack for DJ session actions."""

    def __init__(self, max_depth: int = 10):
        self._stack: deque[UndoableAction] = deque(maxlen=max_depth)
        self._max_depth = max_depth

    def push(
        self,
        action: str,
        prev_track_id: str = "",
        prev_position_sec: float = 0.0,
        prev_state: SessionState | None = None,
        metadata: dict | None = None,
    ) -> UndoableAction | None:
        """Push an action onto the undo stack. Returns None for non-undoable actions."""
        if action in NON_UNDOABLE_ACTIONS:
            logger.debug("[undo] action '%s' is not undoable — skipping push", action)
            return None
        if action not in UNDOABLE_ACTIONS:
            return None

        entry = UndoableAction(
            action=action,
            prev_track_id=prev_track_id,
            prev_position_sec=prev_position_sec,
            prev_state=prev_state,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self._stack.append(entry)
        logger.info("[undo] pushed '%s' (stack depth=%d)", action, len(self._stack))
        return entry

    def pop(self) -> UndoableAction | None:
        """Pop the most recent undoable action."""
        if not self._stack:
            logger.debug("[undo] stack is empty")
            return None
        entry = self._stack.pop()
        logger.info("[undo] popped '%s' (stack depth=%d)", entry.action, len(self._stack))
        return entry

    def peek(self) -> UndoableAction | None:
        """Peek at the most recent action without popping."""
        if not self._stack:
            return None
        return self._stack[-1]

    def clear(self) -> None:
        """Clear the undo stack."""
        self._stack.clear()
        logger.debug("[undo] stack cleared")

    def can_undo(self) -> bool:
        return len(self._stack) > 0

    @property
    def depth(self) -> int:
        return len(self._stack)

    def snapshot(self) -> dict:
        return {
            "can_undo": self.can_undo(),
            "depth": self.depth,
            "last_action": self.peek().action if self.peek() else None,
        }
