"""Automatic multi-track playlist ordering built on DJ-informed pair scoring."""

from __future__ import annotations

from itertools import permutations

from core.datatypes import PlaylistPlan, PlaylistTransition, TrackMetadata, TransitionPlan
from core.enums import PhraseType, TransitionType
from logic.brain import TransitionPlanner


class PlaylistPlanner:
    """Plans an automatic smooth mix order across multiple candidate tracks."""

    def __init__(self, transition_planner: TransitionPlanner | None = None) -> None:
        self.transition_planner = transition_planner or TransitionPlanner()

    def plan(self, tracks: list[TrackMetadata]) -> PlaylistPlan:
        if len(tracks) < 2:
            raise ValueError("At least two tracks are required for playlist planning.")
        if len({track.track_id for track in tracks}) != len(tracks):
            raise ValueError("Playlist planning requires unique track ids.")

        pair_plans = self._pair_plans(tracks)
        ordered = self._best_order(tracks, pair_plans)
        transitions = [
            PlaylistTransition(track_a_id=a.track_id, track_b_id=b.track_id, plan=pair_plans[(a.track_id, b.track_id)])
            for a, b in zip(ordered, ordered[1:])
        ]
        scores = [transition.plan.score_breakdown.total_score for transition in transitions]
        average_score = sum(scores) / len(scores) if scores else 0.0
        notes = self._sequence_notes(ordered, transitions, average_score)
        return PlaylistPlan(
            ordered_track_ids=[track.track_id for track in ordered],
            ordered_titles=[track.title for track in ordered],
            transitions=transitions,
            average_score=average_score,
            notes=notes,
        )

    def _pair_plans(self, tracks: list[TrackMetadata]) -> dict[tuple[str, str], TransitionPlan]:
        plans: dict[tuple[str, str], TransitionPlan] = {}
        for track_a in tracks:
            for track_b in tracks:
                if track_a.track_id == track_b.track_id:
                    continue
                plans[(track_a.track_id, track_b.track_id)] = self.transition_planner.plan(track_a, track_b)
        return plans

    def _best_order(self, tracks: list[TrackMetadata], pair_plans: dict[tuple[str, str], TransitionPlan]) -> list[TrackMetadata]:
        if len(tracks) <= 7:
            return max(permutations(tracks), key=lambda order: self._sequence_score(list(order), pair_plans))

        start = min(tracks, key=lambda track: (self._intro_bias(track), self._avg_energy(track), track.title.lower()))
        ordered = [start]
        remaining = {track.track_id: track for track in tracks if track.track_id != start.track_id}
        while remaining:
            current = ordered[-1]
            next_track = max(remaining.values(), key=lambda candidate: self._pair_score(current, candidate, pair_plans))
            ordered.append(next_track)
            remaining.pop(next_track.track_id)
        return ordered

    def _sequence_score(self, order: list[TrackMetadata], pair_plans: dict[tuple[str, str], TransitionPlan]) -> float:
        transition_scores: list[float] = []
        repeated_strategy_penalty = 0.0
        previous_strategy: TransitionType | None = None
        energies = [self._avg_energy(track) for track in order]
        progression_bonus = self._energy_progression_bonus(energies)

        for track_a, track_b in zip(order, order[1:]):
            plan = pair_plans[(track_a.track_id, track_b.track_id)]
            transition_scores.append(plan.score_breakdown.total_score)
            if previous_strategy == plan.strategy:
                repeated_strategy_penalty += 0.04
            previous_strategy = plan.strategy

        avg_transition = sum(transition_scores) / len(transition_scores) if transition_scores else 0.0
        intro_bonus = 0.08 if self._intro_bias(order[0]) == 0.0 else 0.0
        finale_bonus = 0.06 if self._outro_bias(order[-1]) <= 0.1 else 0.0
        return avg_transition + progression_bonus + intro_bonus + finale_bonus - repeated_strategy_penalty

    def _pair_score(self, track_a: TrackMetadata, track_b: TrackMetadata, pair_plans: dict[tuple[str, str], TransitionPlan]) -> tuple[float, float, int, float]:
        plan = pair_plans[(track_a.track_id, track_b.track_id)]
        bpm_delta = abs(track_a.beatgrid.bpm - track_b.beatgrid.bpm)
        harmonic_rank = self._camelot_rank(track_a.key.camelot, track_b.key.camelot)
        return (plan.score_breakdown.total_score, -bpm_delta, harmonic_rank, -self._avg_energy(track_b))

    def _sequence_notes(self, ordered: list[TrackMetadata], transitions: list[PlaylistTransition], average_score: float) -> list[str]:
        notes = [f"Auto-selected {len(ordered)} tracks for smooth mix.", f"Average transition score: {average_score:.3f}."]
        notes.append(f"Opening track: {ordered[0].title} ({ordered[0].phrases[0].phrase_type.value if ordered[0].phrases else 'unknown'} bias).")
        notes.append(f"Closing track: {ordered[-1].title}.")
        for transition in transitions:
            notes.append(f"{transition.plan.strategy.value}: {transition.track_a_id} -> {transition.track_b_id} @ {transition.plan.track_a_exit_bar}->{transition.plan.track_b_entry_bar}")
        return notes

    def _energy_progression_bonus(self, energies: list[float]) -> float:
        if len(energies) < 3:
            return 0.02
        slope_reward = 0.0
        for left, right in zip(energies, energies[1:]):
            if right >= left - 0.08:
                slope_reward += 0.02
            else:
                slope_reward -= 0.015
        peak_bonus = 0.03 if max(energies[-2:]) >= max(energies[:-2], default=max(energies)) else 0.0
        return slope_reward + peak_bonus

    def _avg_energy(self, track: TrackMetadata) -> float:
        values = [point.combined for point in track.energy_bars]
        return sum(values) / len(values) if values else 0.5

    def _intro_bias(self, track: TrackMetadata) -> float:
        first_phrase = track.phrases[0].phrase_type if track.phrases else PhraseType.UNKNOWN
        if first_phrase == PhraseType.INTRO:
            return 0.0
        if first_phrase == PhraseType.VERSE:
            return 0.1
        return 0.2

    def _outro_bias(self, track: TrackMetadata) -> float:
        last_phrase = track.phrases[-1].phrase_type if track.phrases else PhraseType.UNKNOWN
        if last_phrase == PhraseType.OUTRO:
            return 0.0
        if last_phrase in {PhraseType.CHORUS, PhraseType.DROP}:
            return 0.05
        return 0.12

    def _camelot_rank(self, camelot_a: str | None, camelot_b: str | None) -> int:
        if not camelot_a or not camelot_b:
            return 0
        if camelot_a == camelot_b:
            return 2
        return 1 if self.transition_planner._camelot_is_adjacent(camelot_a, camelot_b) else 0
