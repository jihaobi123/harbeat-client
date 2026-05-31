"""C6 Session Coordinator — the central nervous system of HarBeat Live DJ.

Wires together:
  - SessionStateMachine (energy arc)
  - QueueManager (track buffer + history)
  - SafetyPool (fallback tracks)
  - UndoStack (reversible actions)

Receives ButtonIntents (from C5) → queries C3 for candidates →
dispatches ControlCommands (to C4).

This is the ONLY module that coordinates between recommendation and playback.
No other module should directly connect C3 ↔ C4.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable, Protocol

from .queue_manager import QueueManager
from .safety_pool import SafetyPool
from .schemas import (
    ButtonIntent,
    Candidate,
    CandidateList,
    ControlCommand,
    SceneConfig,
    SessionConfig,
    SessionSnapshot,
    SessionState,
)
from .state_machine import SessionStateMachine
from .undo_stack import UndoStack

logger = logging.getLogger(__name__)


# ── Protocol for C3 recommendation (dependency injection) ────────────────────


class CandidateSelector(Protocol):
    """C3 interface: given context, return candidate tracks."""

    def select_candidates(
        self,
        current_track_id: str,
        session_state: str,
        target_energy: float,
        current_energy: float,
        avoid_ids: list[str],
        intent: str | None,
    ) -> CandidateList:
        ...


class PlaybackController(Protocol):
    """C4 interface: execute control commands on the playback engine."""

    def execute(self, command: ControlCommand) -> bool:
        ...


# ═══════════════════════════════════════════════════════════════════════════════
# Coordinator
# ═══════════════════════════════════════════════════════════════════════════════


class SessionCoordinator:
    """Central coordinator for a DJ session.

    Usage:
        coord = SessionCoordinator(config)
        coord.start(scene_config)

        # On user button press (from C5):
        cmd = coord.handle_intent(ButtonIntent(action="energy_up"))

        # On track change (from C4):
        coord.on_track_changed(new_track_id, energy=0.65)

        # Get current state for UI (for C5):
        snap = coord.snapshot()
    """

    def __init__(
        self,
        config: SessionConfig | None = None,
        candidate_selector: CandidateSelector | None = None,
        playback_controller: PlaybackController | None = None,
    ):
        self._config = config or SessionConfig()
        self._session_id = str(uuid.uuid4())[:8]
        self._state_machine = SessionStateMachine()
        self._queue = QueueManager(buffer_size=self._config.queue_buffer_size)
        self._safety_pool = SafetyPool()
        self._undo = UndoStack(max_depth=self._config.undo_depth)
        self._candidate_selector = candidate_selector
        self._playback = playback_controller
        self._started_at: float = 0.0
        self._event_log: list[dict] = []

    # ── lifecycle ────────────────────────────────────────────────────────

    def start(self, scene: SceneConfig | None = None) -> SessionSnapshot:
        """Start the session: setup → warmup."""
        if scene:
            self._config.scene = scene
        self._started_at = time.time()
        self._state_machine.start(initial_energy=0.3)
        self._log_event("session_start", {"scene": self._config.scene.scene.value})
        return self.snapshot()

    def stop(self) -> SessionSnapshot:
        """Stop the session: → close."""
        self._state_machine.handle_intent("close")
        self._log_event("session_stop", {})
        return self.snapshot()

    # ── intent handling (C5 → C6) ────────────────────────────────────────

    def handle_intent(self, intent: ButtonIntent) -> ControlCommand | None:
        """Process a user button press. Returns a ControlCommand for C4, or None if no action needed."""
        action = intent.action
        self._log_event("intent", {"action": action, "source": intent.source})

        # ── Emergency actions — bypass state machine ──
        if action == "emergency_next":
            return self._handle_emergency_next()

        # ── Undo ──
        if action == "undo":
            return self._handle_undo()

        # ── Session-level actions ──
        if action in ("energy_up", "energy_down", "hold"):
            new_state = self._state_machine.handle_intent(action)
            if new_state:
                self._log_event("state_change", {"to": new_state.value, "reason": action})

        # ── Track-level actions → query C3, get candidates ──
        if action in ("next", "energy_up", "energy_down", "style_change", "hold"):
            return self._handle_track_action(action, intent.params)

        # ── Loop / pause ──
        if action == "loop":
            return ControlCommand(action="loop", params={"bars": 8}, execute_at="next_bar")
        if action == "pause":
            return ControlCommand(action="pause", params={}, execute_at="now")
        if action == "talkover":
            return ControlCommand(action="duck", params={"db": -12}, execute_at="now")

        return None

    def _handle_track_action(self, action: str, params: dict) -> ControlCommand | None:
        """Query C3 for candidates and return a ControlCommand."""
        state = self._state_machine
        queue = self._queue

        # Gather context for C3
        avoid_ids = list(queue.recently_played_ids())
        if queue.current_track_id:
            avoid_ids.append(queue.current_track_id)

        # Query C3
        if self._candidate_selector:
            candidates = self._candidate_selector.select_candidates(
                current_track_id=queue.current_track_id,
                session_state=state.state.value,
                target_energy=state.target_energy,
                current_energy=queue.current_energy,
                avoid_ids=avoid_ids,
                intent=action,
            )
        else:
            # No C3 available — use safety pool
            fallback_id = self._safety_pool.get_random(exclude=avoid_ids)
            candidates = CandidateList(
                candidates=[],
                fallback_track_id=fallback_id or "",
            )

        # Pick best candidate
        best = candidates.best or candidates.safe
        if not best and candidates.candidates:
            best = candidates.candidates[0]

        to_track_id = ""
        template = "safe_blend"
        if best:
            to_track_id = best.track_id
            template = best.template
        elif candidates.fallback_track_id:
            to_track_id = candidates.fallback_track_id
            template = "emergency_next"

        if not to_track_id:
            logger.warning("[coordinator] no candidate found for action '%s'", action)
            # Last resort: random safety pool track
            to_track_id = self._safety_pool.get_random() or ""
            template = "emergency_next"

        # Push to undo stack BEFORE execution
        self._undo.push(
            action=action,
            prev_track_id=queue.current_track_id,
            prev_position_sec=0.0,
            prev_state=state.state,
            metadata={"to_track_id": to_track_id, "template": template},
        )

        # Update queue
        if candidates.candidates:
            self._queue.refill(candidates)

        # Map action to transition template
        template_map = {
            "energy_up": "energy_lift",
            "energy_down": "recovery_blend",
            "style_change": "style_change",
            "hold": "safe_blend",
            "next": template,
        }
        transition_template = template_map.get(action, template)

        # Build control command for C4
        return ControlCommand(
            action="xfade",
            params={
                "to_track_id": to_track_id,
                "style": transition_template,
                "fade_sec": 8.0 if transition_template == "safe_blend" else 4.0,
            },
            execute_at="next_phrase",
            quantize=True,
        )

    def _handle_emergency_next(self) -> ControlCommand:
        """Emergency: get safest track immediately."""
        self._state_machine.force_emergency()
        safe_id = self._safety_pool.get_safest(
            exclude=[self._queue.current_track_id]
        )
        if not safe_id:
            safe_id = self._safety_pool.get_random() or ""

        self._log_event("emergency_next", {"to_track_id": safe_id})

        return ControlCommand(
            action="emergency_cut",
            params={"to_track_id": safe_id},
            execute_at="now",
            quantize=False,
        )

    def _handle_undo(self) -> ControlCommand | None:
        """Undo the last action."""
        entry = self._undo.pop()
        if not entry:
            logger.info("[coordinator] undo requested but stack is empty")
            return None

        self._log_event("undo", {"action": entry.action, "prev_track": entry.prev_track_id})

        # Restore previous state
        if entry.prev_state:
            self._state_machine._transition(entry.prev_state, "undo")

        return ControlCommand(
            action="xfade",
            params={
                "to_track_id": entry.prev_track_id,
                "style": "safe_blend",
                "fade_sec": 6.0,
                "to_at_sec": entry.prev_position_sec,
            },
            execute_at="next_bar",
            quantize=True,
        )

    # ── feedback (C4 → C6) ───────────────────────────────────────────────

    def on_track_changed(self, track_id: str, energy: float = 0.5, artist: str = "") -> None:
        """Notify coordinator that a new track is now playing."""
        self._queue.set_current(track_id, artist=artist, energy=energy)
        self._state_machine.on_track_change(energy)
        self._log_event("track_changed", {"track_id": track_id, "energy": energy})

    def on_track_nearing_end(self, position_sec: float, duration_sec: float) -> ControlCommand | None:
        """Called when current track is near the end (~30s remaining).
        If queue is empty, triggers auto-refill from safety pool.
        """
        remaining = duration_sec - position_sec
        if remaining < 30 and self._queue.is_empty:
            logger.info("[coordinator] queue empty with %.0fs remaining, using safety pool", remaining)
            safe_id = self._safety_pool.get_random(
                exclude=[self._queue.current_track_id]
            )
            if safe_id:
                return ControlCommand(
                    action="xfade",
                    params={"to_track_id": safe_id, "style": "safe_blend", "fade_sec": 8.0},
                    execute_at="next_phrase",
                    quantize=True,
                )
        return None

    # ── safety pool ──────────────────────────────────────────────────────

    def build_safety_pool(self, track_summaries: list[dict]) -> int:
        """Build the safety pool from available track data."""
        return len(self._safety_pool.build(track_summaries))

    # ── snapshot ─────────────────────────────────────────────────────────

    def snapshot(self) -> SessionSnapshot:
        """Get the full session state for UI display and persistence."""
        return SessionSnapshot(
            session_id=self._session_id,
            state=self._state_machine.state,
            scene=self._config.scene,
            current_track_id=self._queue.current_track_id,
            current_position_sec=0.0,
            current_energy=self._queue.current_energy,
            queue=[c.track_id for c in [self._queue.peek(i) for i in range(self._queue.size)] if c],
            history=[h["track_id"] for h in getattr(self._queue, '_history', [])],
            safety_pool_ids=self._safety_pool.pool,
            undo_depth=self._undo.depth,
            energy_history=[],
            created_at=self._started_at,
            updated_at=time.time(),
        )

    # ── event log ────────────────────────────────────────────────────────

    def _log_event(self, event_type: str, data: dict) -> None:
        self._event_log.append({
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
            "state": self._state_machine.state.value,
        })
        if len(self._event_log) > 1000:
            self._event_log = self._event_log[-500:]

    @property
    def event_log(self) -> list[dict]:
        return list(self._event_log)
