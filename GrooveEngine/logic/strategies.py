"""Transition strategy implementations for GrooveEngine."""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.datatypes import AutomationLane, AutomationPoint, TransitionPlan
from core.enums import FXType, TransitionType


class TransitionStrategy(ABC):
    """Base class for all transition automation generators."""

    transition_type: TransitionType

    @abstractmethod
    def build_automation(self, plan: TransitionPlan) -> list[AutomationLane]:
        """Return automation lanes for the provided transition plan."""


class CleanBlendStrategy(TransitionStrategy):
    """Eight-bar bass swap transition."""

    transition_type = TransitionType.CLEAN_BLEND

    def build_automation(self, plan: TransitionPlan) -> list[AutomationLane]:
        overlap = float(plan.overlap_duration_beats)
        points = [
            AutomationPoint(beat_offset=0.0, fx_type=FXType.LOW_EQ, value=1.0, deck="A"),
            AutomationPoint(beat_offset=16.0, fx_type=FXType.LOW_EQ, value=0.0, deck="A"),
            AutomationPoint(beat_offset=0.0, fx_type=FXType.LOW_EQ, value=0.0, deck="B"),
            AutomationPoint(beat_offset=16.0, fx_type=FXType.LOW_EQ, value=1.0, deck="B"),
            AutomationPoint(beat_offset=overlap, fx_type=FXType.VOLUME, value=0.0, deck="A"),
            AutomationPoint(beat_offset=0.0, fx_type=FXType.VOLUME, value=0.0, deck="B"),
            AutomationPoint(beat_offset=8.0, fx_type=FXType.VOLUME, value=1.0, deck="B"),
        ]
        return [AutomationLane(name="clean_blend", points=points)]


class EchoOutStrategy(TransitionStrategy):
    """Short overlap with echo tail on the outgoing track."""

    transition_type = TransitionType.ECHO_OUT

    def build_automation(self, plan: TransitionPlan) -> list[AutomationLane]:
        start = max(float(plan.overlap_duration_beats) - 4.0, 0.0)
        points = [
            AutomationPoint(beat_offset=start, fx_type=FXType.DELAY_MIX, value=0.8, deck="A"),
            AutomationPoint(beat_offset=start, fx_type=FXType.DELAY_FEEDBACK, value=0.72, deck="A"),
            AutomationPoint(beat_offset=float(plan.overlap_duration_beats), fx_type=FXType.VOLUME, value=0.0, deck="A"),
            AutomationPoint(beat_offset=0.0, fx_type=FXType.VOLUME, value=0.0, deck="B"),
            AutomationPoint(beat_offset=1.0, fx_type=FXType.VOLUME, value=1.0, deck="B"),
        ]
        return [AutomationLane(name="echo_out", points=points)]


class RiserStrategy(TransitionStrategy):
    """Build-up style transition with HPF and noise."""

    transition_type = TransitionType.RISER

    def build_automation(self, plan: TransitionPlan) -> list[AutomationLane]:
        overlap = float(plan.overlap_duration_beats)
        points = [
            AutomationPoint(beat_offset=0.0, fx_type=FXType.HIGH_PASS, value=0.05, deck="A"),
            AutomationPoint(beat_offset=overlap - 1.0, fx_type=FXType.HIGH_PASS, value=0.95, deck="A"),
            AutomationPoint(beat_offset=2.0, fx_type=FXType.NOISE_LEVEL, value=0.3, deck="master"),
            AutomationPoint(beat_offset=overlap - 1.0, fx_type=FXType.NOISE_LEVEL, value=1.0, deck="master"),
            AutomationPoint(beat_offset=overlap, fx_type=FXType.NOISE_LEVEL, value=0.0, deck="master"),
            AutomationPoint(beat_offset=overlap, fx_type=FXType.VOLUME, value=0.0, deck="A"),
            AutomationPoint(beat_offset=0.0, fx_type=FXType.VOLUME, value=0.0, deck="B"),
            AutomationPoint(beat_offset=4.0, fx_type=FXType.VOLUME, value=1.0, deck="B"),
        ]
        return [AutomationLane(name="riser", points=points)]


class CutSwapStrategy(TransitionStrategy):
    """Fast cut for impact transitions in battle or hype moments."""

    transition_type = TransitionType.CUT_SWAP

    def build_automation(self, plan: TransitionPlan) -> list[AutomationLane]:
        points = [
            AutomationPoint(beat_offset=0.0, fx_type=FXType.VOLUME, value=1.0, deck="A"),
            AutomationPoint(beat_offset=0.75, fx_type=FXType.VOLUME, value=0.0, deck="A"),
            AutomationPoint(beat_offset=0.0, fx_type=FXType.HIGH_PASS, value=0.0, deck="B"),
            AutomationPoint(beat_offset=0.0, fx_type=FXType.VOLUME, value=0.0, deck="B"),
            AutomationPoint(beat_offset=0.75, fx_type=FXType.VOLUME, value=1.0, deck="B"),
        ]
        return [AutomationLane(name="cut_swap", points=points)]


class TripletSwapStrategy(TransitionStrategy):
    """Three-step volume choreography to maintain dancer momentum."""

    transition_type = TransitionType.TRIPLET_SWAP

    def build_automation(self, plan: TransitionPlan) -> list[AutomationLane]:
        points = [
            AutomationPoint(beat_offset=0.0, fx_type=FXType.VOLUME, value=1.0, deck="A"),
            AutomationPoint(beat_offset=1.0, fx_type=FXType.VOLUME, value=0.65, deck="A"),
            AutomationPoint(beat_offset=2.0, fx_type=FXType.VOLUME, value=0.25, deck="A"),
            AutomationPoint(beat_offset=3.0, fx_type=FXType.VOLUME, value=0.0, deck="A"),
            AutomationPoint(beat_offset=0.0, fx_type=FXType.VOLUME, value=0.0, deck="B"),
            AutomationPoint(beat_offset=1.0, fx_type=FXType.VOLUME, value=0.45, deck="B"),
            AutomationPoint(beat_offset=2.0, fx_type=FXType.VOLUME, value=0.78, deck="B"),
            AutomationPoint(beat_offset=3.0, fx_type=FXType.VOLUME, value=1.0, deck="B"),
            AutomationPoint(beat_offset=0.0, fx_type=FXType.LOW_EQ, value=0.0, deck="B"),
            AutomationPoint(beat_offset=2.0, fx_type=FXType.LOW_EQ, value=1.0, deck="B"),
        ]
        return [AutomationLane(name="triplet_swap", points=points)]


class MelodicResetStrategy(TransitionStrategy):
    """Intentional breakdown-style reset via filtering and delayed release."""

    transition_type = TransitionType.MELODIC_RESET

    def build_automation(self, plan: TransitionPlan) -> list[AutomationLane]:
        overlap = float(plan.overlap_duration_beats)
        points = [
            AutomationPoint(beat_offset=0.0, fx_type=FXType.HIGH_PASS, value=0.15, deck="A"),
            AutomationPoint(beat_offset=2.0, fx_type=FXType.HIGH_PASS, value=0.85, deck="A"),
            AutomationPoint(beat_offset=2.0, fx_type=FXType.REVERB_MIX, value=0.45, deck="A"),
            AutomationPoint(beat_offset=min(overlap, 4.0), fx_type=FXType.VOLUME, value=0.0, deck="A"),
            AutomationPoint(beat_offset=0.0, fx_type=FXType.VOLUME, value=0.0, deck="B"),
            AutomationPoint(beat_offset=2.0, fx_type=FXType.HIGH_PASS, value=0.75, deck="B"),
            AutomationPoint(beat_offset=4.0, fx_type=FXType.HIGH_PASS, value=0.0, deck="B"),
            AutomationPoint(beat_offset=4.0, fx_type=FXType.VOLUME, value=1.0, deck="B"),
        ]
        return [AutomationLane(name="melodic_reset", points=points)]


STRATEGY_REGISTRY: dict[TransitionType, TransitionStrategy] = {
    TransitionType.CLEAN_BLEND: CleanBlendStrategy(),
    TransitionType.ECHO_OUT: EchoOutStrategy(),
    TransitionType.RISER: RiserStrategy(),
    TransitionType.CUT_SWAP: CutSwapStrategy(),
    TransitionType.TRIPLET_SWAP: TripletSwapStrategy(),
    TransitionType.MELODIC_RESET: MelodicResetStrategy(),
}
