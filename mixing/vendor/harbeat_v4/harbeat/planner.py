"""Mini set planning."""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence

from .models import (
    MiniSetPlan,
    PairAnalysis,
    PairAnalysisLookup,
    PairAnalysisProvider,
    TrackProfile,
    TransitionConfig,
)
from .scoring import score_transition_candidate
from .transition import build_transition_plan


class InsufficientTracksError(ValueError):
    """Raised when a style pool cannot fill a complete mini set."""


class MiniSetPlanner:
    """Greedy mini set planner following the DJ continuity rules."""

    def __init__(
        self,
        config: TransitionConfig | None = None,
        *,
        seed: int | None = None,
        pair_lookup: PairAnalysisLookup | None = None,
        pair_provider: PairAnalysisProvider | None = None,
    ) -> None:
        self.config = config or TransitionConfig()
        self._rng = random.Random(seed)
        self._pair_lookup = pair_lookup or {}
        self._pair_provider = pair_provider

    def _pair_analysis(self, current: TrackProfile, incoming: TrackProfile) -> PairAnalysis:
        direct = self._pair_lookup.get((current.id, incoming.id))
        if direct is not None:
            return direct
        reverse = self._pair_lookup.get((incoming.id, current.id))
        if reverse is not None:
            return reverse
        if self._pair_provider:
            provided = self._pair_provider(current, incoming)
            if provided is not None:
                return provided
        return PairAnalysis()

    @staticmethod
    def _same_style(left: TrackProfile, right: TrackProfile) -> bool:
        return left.style.strip().lower() == right.style.strip().lower()

    def _select_start(
        self,
        tracks: Sequence[TrackProfile],
        start_track_id: str | None,
        style: str | None,
    ) -> TrackProfile:
        if start_track_id:
            for track in tracks:
                if track.id == start_track_id:
                    return track
            raise ValueError(f"start_track_id not found: {start_track_id}")

        pool = list(tracks)
        if style:
            normalized = style.strip().lower()
            pool = [track for track in tracks if track.style.strip().lower() == normalized]
            if not pool:
                raise ValueError(f"style not found: {style}")

        if not pool:
            raise ValueError("tracks cannot be empty")
        return self._rng.choice(pool)

    def plan_mini_set(
        self,
        tracks: Sequence[TrackProfile],
        *,
        start_track_id: str | None = None,
        style: str | None = None,
    ) -> MiniSetPlan:
        """Plan one fixed-size mini set."""

        if self.config.mini_set_size < 2:
            raise ValueError("mini_set_size must be at least 2")

        all_tracks = tuple(tracks)
        start = self._select_start(all_tracks, start_track_id, style)
        style_pool = [
            track
            for track in all_tracks
            if self._same_style(start, track) and track.id != start.id
        ]
        needed = self.config.mini_set_size - 1
        if len(style_pool) < needed:
            raise InsufficientTracksError(
                f"style '{start.style}' needs {self.config.mini_set_size} tracks, "
                f"but only {len(style_pool) + 1} are available"
            )

        selected: list[TrackProfile] = [start]
        remaining = style_pool
        while len(selected) < self.config.mini_set_size:
            current = selected[-1]
            scored = [
                (
                    score_transition_candidate(
                        current,
                        candidate,
                        self.config,
                        self._pair_analysis(current, candidate),
                    ),
                    candidate,
                )
                for candidate in remaining
            ]
            scored.sort(
                key=lambda item: (
                    -item[0].total,
                    abs(item[0].bpm_delta),
                    item[1].title.lower(),
                    item[1].id,
                )
            )
            next_track = scored[0][1]
            selected.append(next_track)
            remaining = [track for track in remaining if track.id != next_track.id]

        transitions = tuple(
            build_transition_plan(
                selected[index],
                selected[index + 1],
                self.config,
                self._pair_analysis(selected[index], selected[index + 1]),
            )
            for index in range(len(selected) - 1)
        )
        return MiniSetPlan(style=start.style, tracks=tuple(selected), transitions=transitions)

    def plan_mini_sets(
        self,
        tracks: Sequence[TrackProfile],
        *,
        set_count: int,
    ) -> tuple[MiniSetPlan, ...]:
        """Plan multiple mini sets while rotating styles when possible."""

        by_style: dict[str, list[TrackProfile]] = defaultdict(list)
        for track in tracks:
            by_style[track.style.strip().lower()].append(track)

        eligible_styles = [
            style for style, pool in by_style.items() if len(pool) >= self.config.mini_set_size
        ]
        if not eligible_styles:
            raise InsufficientTracksError("no style has enough tracks for a mini set")

        plans: list[MiniSetPlan] = []
        previous_style: str | None = None
        for _ in range(set_count):
            choices = [style for style in eligible_styles if style != previous_style] or eligible_styles
            chosen_style = self._rng.choice(choices)
            plan = self.plan_mini_set(by_style[chosen_style], style=chosen_style)
            plans.append(plan)
            previous_style = chosen_style

        return tuple(plans)

