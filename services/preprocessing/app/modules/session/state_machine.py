"""C6 Session state machine — manages the DJ set's energy arc.

States: setup → warmup → build → peak → recover → (hold | emergency) → close

Transitions are triggered by:
  - Session duration / track count (automatic)
  - User button presses (manual)
  - Energy level changes (derived)

The state machine does NOT select tracks or execute playback — it only
determines the current phase and target energy direction.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from .schemas import EnergyLevel, SessionState

logger = logging.getLogger(__name__)

# ── State transition rules ───────────────────────────────────────────────────
# (from_state, to_state, condition_name, automatic?)
TRANSITIONS: dict[SessionState, list[tuple[SessionState, str, bool]]] = {
    SessionState.setup: [
        (SessionState.warmup, "session_start", False),  # manual: user starts
    ],
    SessionState.warmup: [
        (SessionState.build, "energy_up_or_track_count", True),
        (SessionState.emergency, "emergency_trigger", False),
        (SessionState.close, "session_end", False),
    ],
    SessionState.build: [
        (SessionState.peak, "energy_peak_reached", True),
        (SessionState.recover, "energy_down_intent", False),
        (SessionState.hold, "hold_intent", False),
        (SessionState.emergency, "emergency_trigger", False),
    ],
    SessionState.peak: [
        (SessionState.recover, "fatigue_or_energy_down", True),
        (SessionState.hold, "hold_intent", False),
        (SessionState.emergency, "emergency_trigger", False),
    ],
    SessionState.recover: [
        (SessionState.build, "energy_up_intent", False),
        (SessionState.peak, "energy_jump", False),
        (SessionState.close, "session_end", False),
        (SessionState.emergency, "emergency_trigger", False),
    ],
    SessionState.hold: [
        (SessionState.build, "release_hold", False),
        (SessionState.recover, "release_hold_low", False),
        (SessionState.emergency, "emergency_trigger", False),
    ],
    SessionState.emergency: [
        (SessionState.recover, "recovery_successful", True),
        (SessionState.close, "force_close", False),
    ],
    SessionState.close: [
        (SessionState.setup, "new_session", False),
    ],
}

# ── Energy bounds per state ──────────────────────────────────────────────────
STATE_ENERGY_BOUNDS: dict[SessionState, tuple[float, float]] = {
    SessionState.setup: (0.0, 0.0),
    SessionState.warmup: (0.15, 0.50),
    SessionState.build: (0.40, 0.75),
    SessionState.peak: (0.65, 1.0),
    SessionState.recover: (0.20, 0.55),
    SessionState.hold: (0.25, 0.80),
    SessionState.emergency: (0.20, 0.60),
    SessionState.close: (0.0, 0.3),
}

# ── Track count hints before auto-transition ─────────────────────────────────
STATE_AUTO_TRANSITION_TRACKS: dict[SessionState, int] = {
    SessionState.warmup: 4,   # after ~4 tracks, consider auto-build
    SessionState.build: 5,    # after ~5 tracks, consider auto-peak
    SessionState.peak: 6,     # after ~6 tracks, consider auto-recover
    SessionState.recover: 4,  # after ~4 tracks, consider auto-build or close
}


@dataclass
class StateMachineContext:
    """Immutable-ish context passed to transition guards."""
    state: SessionState
    track_count_in_state: int = 0
    current_energy: float = 0.5
    target_energy: float = 0.5
    total_track_count: int = 0
    session_duration_sec: float = 0.0
    user_intent: str | None = None  # last button pressed


class SessionStateMachine:
    """Manages the session's energy-state lifecycle."""

    def __init__(self, initial_state: SessionState = SessionState.setup):
        self._state = initial_state
        self._state_started_at: float = time.time()
        self._track_count_in_state: int = 0
        self._total_track_count: int = 0
        self._current_energy: float = 0.0
        self._target_energy: float = 0.5
        self._listeners: list[Callable[[SessionState, SessionState], None]] = []

    # ── properties ───────────────────────────────────────────────────────

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def target_energy(self) -> float:
        lo, hi = STATE_ENERGY_BOUNDS.get(self._state, (0.0, 1.0))
        return (lo + hi) / 2.0

    @property
    def energy_bounds(self) -> tuple[float, float]:
        return STATE_ENERGY_BOUNDS.get(self._state, (0.0, 1.0))

    @property
    def context(self) -> StateMachineContext:
        return StateMachineContext(
            state=self._state,
            track_count_in_state=self._track_count_in_state,
            current_energy=self._current_energy,
            target_energy=self._target_energy,
            total_track_count=self._total_track_count,
            session_duration_sec=time.time() - self._state_started_at,
        )

    # ── state mutations ──────────────────────────────────────────────────

    def start(self, initial_energy: float = 0.3) -> SessionState:
        """Start the session: setup → warmup."""
        return self._transition(SessionState.warmup, "session_start")

    def on_track_change(self, new_energy: float) -> None:
        """Notify state machine that a track change occurred."""
        self._current_energy = new_energy
        self._track_count_in_state += 1
        self._total_track_count += 1

        # Check auto-transitions
        auto_limit = STATE_AUTO_TRANSITION_TRACKS.get(self._state)
        if auto_limit and self._track_count_in_state >= auto_limit:
            if self._state == SessionState.warmup:
                self._transition(SessionState.build, "auto_track_count")
            elif self._state == SessionState.build:
                self._transition(SessionState.peak, "auto_track_count")
            elif self._state == SessionState.peak:
                self._transition(SessionState.recover, "auto_track_count")
            elif self._state == SessionState.recover and self._total_track_count > 20:
                self._transition(SessionState.close, "auto_track_count")

    def handle_intent(self, intent: str) -> SessionState | None:
        """Process a user intent, return new state if transition occurred."""
        # State-aware intent mapping
        state_intent_map: dict[SessionState, dict[str, tuple[SessionState, str]]] = {
            SessionState.warmup: {
                "energy_up": (SessionState.build, "intent_energy_up"),
                "emergency_next": (SessionState.emergency, "intent_emergency"),
                "close": (SessionState.close, "intent_close"),
            },
            SessionState.build: {
                "energy_up": (SessionState.peak, "intent_energy_up"),
                "energy_down": (SessionState.recover, "intent_energy_down"),
                "hold": (SessionState.hold, "intent_hold"),
                "emergency_next": (SessionState.emergency, "intent_emergency"),
            },
            SessionState.peak: {
                "energy_down": (SessionState.recover, "intent_energy_down"),
                "hold": (SessionState.hold, "intent_hold"),
                "emergency_next": (SessionState.emergency, "intent_emergency"),
            },
            SessionState.recover: {
                "energy_up": (SessionState.build, "intent_energy_up"),
                "energy_down": (SessionState.close, "intent_close"),
                "hold": (SessionState.hold, "intent_hold"),
                "emergency_next": (SessionState.emergency, "intent_emergency"),
                "close": (SessionState.close, "intent_close"),
            },
            SessionState.hold: {
                "energy_up": (SessionState.build, "intent_release_hold"),
                "energy_down": (SessionState.recover, "intent_release_hold_low"),
                "emergency_next": (SessionState.emergency, "intent_emergency"),
            },
            SessionState.emergency: {
                "energy_down": (SessionState.recover, "intent_recovery"),
                "close": (SessionState.close, "intent_close"),
            },
        }

        state_map = state_intent_map.get(self._state, {})
        mapping = state_map.get(intent)
        if mapping:
            target, reason = mapping
            return self._transition(target, reason)
        else:
            logger.debug("[session] intent '%s' not valid from state %s", intent, self._state.value)
        return None

    def force_emergency(self) -> SessionState:
        """Force transition to emergency state."""
        return self._transition(SessionState.emergency, "force_emergency")

    # ── internal ─────────────────────────────────────────────────────────

    def _transition(self, to_state: SessionState, reason: str) -> SessionState:
        old = self._state
        if old == to_state:
            return to_state

        valid = [t[0] for t in TRANSITIONS.get(old, [])]
        if to_state not in valid and old != SessionState.setup:
            logger.warning("[session] invalid transition %s → %s (reason=%s), forcing",
                          old.value, to_state.value, reason)
            # Still allow it — MC judgment overrides rules

        self._state = to_state
        self._state_started_at = time.time()
        self._track_count_in_state = 0
        lo, hi = STATE_ENERGY_BOUNDS.get(to_state, (0.0, 1.0))
        self._target_energy = (lo + hi) / 2.0

        logger.info("[session] %s → %s (reason=%s, target_energy=%.2f)",
                    old.value, to_state.value, reason, self._target_energy)

        for listener in self._listeners:
            try:
                listener(old, to_state)
            except Exception:
                logger.exception("[session] listener error")

        return to_state

    def on_state_change(self, callback: Callable[[SessionState, SessionState], None]) -> None:
        """Register a listener for state transitions."""
        self._listeners.append(callback)

    def snapshot(self) -> dict:
        return {
            "state": self._state.value,
            "target_energy": round(self._target_energy, 2),
            "energy_bounds": list(self.energy_bounds),
            "track_count_in_state": self._track_count_in_state,
            "total_track_count": self._total_track_count,
        }
