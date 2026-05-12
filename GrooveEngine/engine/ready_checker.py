"""Readiness checker with automatic fallback to FADE_MODE crossover."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time

from core.enums import TransitionType


class FallbackReason(str, Enum):
    NONE = "none"
    RENDER_NOT_READY = "render_not_ready"
    RAPID_MANUAL = "rapid_manual_switch"
    BUFFER_UNDERRUN = "buffer_underrun"
    DECK_EXHAUSTED = "deck_exhausted"


@dataclass(slots=True)
class ReadyChecker:
    """Monitors transition readiness and triggers FADE_MODE when conditions aren't met.

    FADE_MODE is the ultimate safety net: a 4-beat volume-only crossfade that
    requires zero pre-rendering and always works.
    """

    rapid_switch_window_seconds: float = 2.0
    rapid_switch_threshold: int = 3
    render_timeout_seconds: float = 30.0

    _manual_switch_timestamps: list[float] = field(default_factory=list)

    def record_manual_switch(self) -> None:
        now = time.monotonic()
        self._manual_switch_timestamps.append(now)
        cutoff = now - self.rapid_switch_window_seconds
        self._manual_switch_timestamps = [t for t in self._manual_switch_timestamps if t >= cutoff]

    @property
    def rapid_switch_count(self) -> int:
        now = time.monotonic()
        cutoff = now - self.rapid_switch_window_seconds
        self._manual_switch_timestamps = [t for t in self._manual_switch_timestamps if t >= cutoff]
        return len(self._manual_switch_timestamps)

    def check(
        self,
        render_ready: bool,
        buffer_healthy: bool = True,
        deck_has_audio: bool = True,
    ) -> tuple[bool, FallbackReason, TransitionType]:
        """Return (can_use_planned_strategy, fallback_reason, effective_strategy).

        If render_ready is True and no rapid-switch condition exists, the caller
        should use whatever strategy was planned.  Otherwise, FADE_MODE is forced.
        """
        if self.rapid_switch_count >= self.rapid_switch_threshold:
            return False, FallbackReason.RAPID_MANUAL, TransitionType.CUT_SWAP

        if not render_ready:
            return False, FallbackReason.RENDER_NOT_READY, TransitionType.CUT_SWAP

        if not buffer_healthy:
            return False, FallbackReason.BUFFER_UNDERRUN, TransitionType.CUT_SWAP

        if not deck_has_audio:
            return False, FallbackReason.DECK_EXHAUSTED, TransitionType.CUT_SWAP

        return True, FallbackReason.NONE, TransitionType.CUT_SWAP  # third value ignored when ok

    def build_fade_automation(self, overlap_beats: float = 4.0):
        """Return a minimal 4-beat volume-only crossfade automation.

        This is the universal fallback: no EQ, no FX, just volume crossover.
        """
        from core.datatypes import AutomationLane, AutomationPoint
        from core.enums import FXType

        points = [
            AutomationPoint(beat_offset=0.0, fx_type=FXType.VOLUME, value=1.0, deck="A"),
            AutomationPoint(beat_offset=overlap_beats, fx_type=FXType.VOLUME, value=0.0, deck="A"),
            AutomationPoint(beat_offset=0.0, fx_type=FXType.VOLUME, value=0.0, deck="B"),
            AutomationPoint(beat_offset=overlap_beats, fx_type=FXType.VOLUME, value=1.0, deck="B"),
        ]
        return [AutomationLane(name="fade_fallback", points=points)]
