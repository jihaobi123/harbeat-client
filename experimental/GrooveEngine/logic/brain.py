"""Bar-candidate transition planning logic for GrooveEngine."""

from __future__ import annotations

from dataclasses import dataclass

from core.datatypes import PlaylistPlan, PlaylistTransition, PhraseSegment, TrackMetadata, TransitionPlan, TransitionWindowScore
from core.enums import PhraseType, TransitionType
from logic.strategies import STRATEGY_REGISTRY


@dataclass(slots=True)
class PlannerWeights:
    phrase_alignment: float = 0.28
    energy_delta: float = 0.22
    harmonic: float = 0.10
    strategy_bias: float = 0.14
    bar_position: float = 0.14
    style_fit: float = 0.12


class TransitionPlanner:
    def __init__(self, weights: PlannerWeights | None = None) -> None:
        self.weights = weights or PlannerWeights()

    def plan(self, track_a: TrackMetadata, track_b: TrackMetadata) -> TransitionPlan:
        candidates: list[TransitionWindowScore] = []
        for exit_bar in self._candidate_exit_bars(track_a):
            for entry_bar in self._candidate_entry_bars(track_b):
                strategy = self._select_strategy(track_a, track_b, exit_bar, entry_bar)
                overlap = self._overlap_for_strategy(strategy)
                candidates.append(self._score_window(track_a, track_b, exit_bar, entry_bar, overlap, strategy))
        best = max(candidates, key=lambda item: item.total_score)
        plan = TransitionPlan(
            mix_start_time=self._bar_start_time(track_a, best.track_a_exit_bar),
            overlap_duration_beats=best.overlap_beats,
            target_bpm=(track_a.beatgrid.bpm + track_b.beatgrid.bpm) / 2.0,
            strategy=best.strategy,
            track_a_exit_bar=best.track_a_exit_bar,
            track_b_entry_bar=best.track_b_entry_bar,
            automation=[],
            score_breakdown=best,
        )
        plan.automation = STRATEGY_REGISTRY[best.strategy].build_automation(plan)
        return plan

    def _candidate_exit_bars(self, track: TrackMetadata) -> list[int]:
        last_bar = track.bar_count()
        start = max(1, last_bar - 48)
        bars = [bar for bar in range(start, last_bar + 1) if self._is_candidate_bar(track, bar)]
        return bars or [max(1, last_bar - 16)]

    def _candidate_entry_bars(self, track: TrackMetadata) -> list[int]:
        end = min(track.bar_count(), 49)
        bars = [bar for bar in range(1, end + 1) if self._is_candidate_bar(track, bar)]
        return bars or [1]

    def _is_candidate_bar(self, track: TrackMetadata, bar: int) -> bool:
        phrase = track.phrase_at_bar(bar)
        return self._is_eight_count_boundary(bar) or self._is_phrase_edge(bar, phrase)

    def _score_window(self, track_a: TrackMetadata, track_b: TrackMetadata, exit_bar: int, entry_bar: int, overlap: int, strategy: TransitionType) -> TransitionWindowScore:
        phrase_score, phrase_notes = self._score_phrase_alignment(track_a, track_b, exit_bar, entry_bar)
        energy_score, energy_notes = self._score_energy(track_a, track_b, exit_bar, entry_bar, strategy)
        harmonic_score, harmonic_notes = self._score_harmonic(track_a, track_b, strategy)
        strategy_bias, strategy_notes = self._strategy_bias(strategy)
        bar_position_score, bar_notes = self._score_bar_position(track_a, track_b, exit_bar, entry_bar)
        style_score, style_notes = self._score_style_fit(track_a, track_b, exit_bar, entry_bar, strategy)
        total = (
            phrase_score * self.weights.phrase_alignment
            + energy_score * self.weights.energy_delta
            + harmonic_score * self.weights.harmonic
            + strategy_bias * self.weights.strategy_bias
            + bar_position_score * self.weights.bar_position
            + style_score * self.weights.style_fit
        )
        return TransitionWindowScore(
            track_a_exit_bar=exit_bar,
            track_b_entry_bar=entry_bar,
            overlap_beats=overlap,
            phrase_score=phrase_score,
            energy_score=energy_score,
            harmonic_score=harmonic_score,
            total_score=min(total, 1.0),
            strategy=strategy,
            notes=phrase_notes + energy_notes + harmonic_notes + bar_notes + style_notes + strategy_notes,
        )

    def _score_phrase_alignment(self, track_a: TrackMetadata, track_b: TrackMetadata, exit_bar: int, entry_bar: int) -> tuple[float, list[str]]:
        a_phrase = track_a.phrase_at_bar(exit_bar)
        b_phrase = track_b.phrase_at_bar(entry_bar)
        score = 1.0
        notes: list[str] = []
        if not self._is_eight_count_boundary(exit_bar):
            score -= 0.18
            notes.append("Track A exit misses 8-count boundary.")
        if not self._is_eight_count_boundary(entry_bar):
            score -= 0.18
            notes.append("Track B entry misses 8-count boundary.")
        if a_phrase:
            progress = self._phrase_progress(exit_bar, a_phrase)
            if progress < 0.45:
                score -= 0.18
                notes.append(f"Track A exits too early inside {a_phrase.phrase_type.value}.")
            elif progress > 0.82:
                notes.append(f"Track A exits late in {a_phrase.phrase_type.value}, good handoff zone.")
        if b_phrase:
            progress = self._phrase_progress(entry_bar, b_phrase)
            if progress < 0.18:
                notes.append(f"Track B enters at fresh {b_phrase.phrase_type.value} phrase opening.")
            elif progress > 0.35:
                score -= 0.20
                notes.append(f"Track B enters mid-{b_phrase.phrase_type.value} phrase.")
        return max(score, 0.0), notes

    def _score_energy(self, track_a: TrackMetadata, track_b: TrackMetadata, exit_bar: int, entry_bar: int, strategy: TransitionType) -> tuple[float, list[str]]:
        a_energy = track_a.energy_at_bar(exit_bar)
        b_energy = track_b.energy_at_bar(entry_bar)
        if not a_energy or not b_energy:
            return 0.5, ["Missing energy data; using neutral score."]
        delta = abs(a_energy.combined - b_energy.combined)
        score = max(0.0, 1.0 - delta)
        notes = [f"Energy delta: {delta:.3f}."]
        a_phrase = track_a.phrase_at_bar(exit_bar)
        b_phrase = track_b.phrase_at_bar(entry_bar)
        if a_phrase and b_phrase and a_phrase.phrase_type == PhraseType.DROP and b_phrase.phrase_type == PhraseType.DROP:
            score = max(score, 0.95)
            notes.append("Drop-to-drop phrase match detected.")
        elif strategy == TransitionType.MELODIC_RESET and b_energy.combined < a_energy.combined:
            score = min(1.0, max(score, 0.84))
            notes.append("Intentional energy reset approved.")
        elif strategy == TransitionType.TRIPLET_SWAP and delta <= 0.24:
            score = min(1.0, score + 0.12)
            notes.append("Triplet swap rewards tight dancer continuity.")
        elif strategy == TransitionType.RISER and b_phrase and b_phrase.phrase_type in {PhraseType.CHORUS, PhraseType.DROP}:
            score = min(1.0, score + 0.15)
            notes.append("Riser favors launch into chorus/drop.")
        elif a_phrase and b_phrase and a_phrase.phrase_type == PhraseType.CHORUS and b_phrase.phrase_type == PhraseType.INTRO:
            score *= 0.45
            notes.append("Harsh chorus-to-intro reset penalized.")
        return score, notes

    def _score_harmonic(self, track_a: TrackMetadata, track_b: TrackMetadata, strategy: TransitionType) -> tuple[float, list[str]]:
        key_a = track_a.key.tonic
        key_b = track_b.key.tonic
        camelot_a = track_a.key.camelot
        camelot_b = track_b.key.camelot
        if key_a == key_b:
            return 1.0, ["Matching tonal centers."]
        return 0.35, ["Harmonic mismatch detected."]

    def _score_bar_position(self, track_a: TrackMetadata, track_b: TrackMetadata, exit_bar: int, entry_bar: int) -> tuple[float, list[str]]:
        a_phrase = track_a.phrase_at_bar(exit_bar)
        b_phrase = track_b.phrase_at_bar(entry_bar)
        score = 0.75
        notes: list[str] = []
        if a_phrase:
            progress = self._phrase_progress(exit_bar, a_phrase)
            if progress >= 0.75:
                score += 0.15
                notes.append("Track A exit is near phrase release zone.")
            elif progress <= 0.25:
                score -= 0.20
                notes.append("Track A exit is too close to phrase start.")
        if b_phrase:
            progress = self._phrase_progress(entry_bar, b_phrase)
            if progress <= 0.12:
                score += 0.15
                notes.append("Track B entry hits phrase opening.")
            elif progress >= 0.40:
                score -= 0.18
                notes.append("Track B entry starts too deep inside phrase.")
        if self._bar_energy_slope(track_a, exit_bar) < -0.05:
            score += 0.08
            notes.append("Track A energy is naturally resolving near exit bar.")
        if self._bar_energy_slope(track_b, entry_bar) > 0.03:
            score += 0.08
            notes.append("Track B energy is rising from entry bar.")
        return max(0.0, min(score, 1.0)), notes

    def _score_style_fit(self, track_a: TrackMetadata, track_b: TrackMetadata, exit_bar: int, entry_bar: int, strategy: TransitionType) -> tuple[float, list[str]]:
        a_phrase = track_a.phrase_at_bar(exit_bar)
        b_phrase = track_b.phrase_at_bar(entry_bar)
        a_style = self._style_profile(track_a)
        b_style = self._style_profile(track_b)
        delta = abs(a_style["density"] - b_style["density"])
        notes = [f"Style density delta: {delta:.3f}."]
        score = max(0.35, 1.0 - delta)
        if strategy == TransitionType.CLEAN_BLEND and delta <= 0.20:
            score = min(1.0, score + 0.12)
            notes.append("Blend-friendly texture match.")
        if strategy == TransitionType.ECHO_OUT and delta >= 0.28:
            score = min(1.0, score + 0.14)
            notes.append("Echo-out accepts strong style contrast.")
        if strategy == TransitionType.MELODIC_RESET and b_style["density"] < a_style["density"]:
            score = min(1.0, score + 0.16)
            notes.append("Melodic reset benefits from lower-density incoming groove.")
        if strategy == TransitionType.CUT_SWAP and a_phrase and b_phrase and a_phrase.phrase_type == b_phrase.phrase_type == PhraseType.DROP:
            score = min(1.0, score + 0.14)
            notes.append("Cut swap reinforced by impact-to-impact structure.")
        return score, notes

    def _select_strategy(self, track_a: TrackMetadata, track_b: TrackMetadata, exit_bar: int, entry_bar: int) -> TransitionType:
        a_phrase = track_a.phrase_at_bar(exit_bar)
        b_phrase = track_b.phrase_at_bar(entry_bar)
        a_energy = track_a.energy_at_bar(exit_bar)
        b_energy = track_b.energy_at_bar(entry_bar)
        a_value = a_energy.combined if a_energy else 0.5
        b_value = b_energy.combined if b_energy else 0.5
        delta = abs(a_value - b_value)
        bpm_delta = abs(track_a.beatgrid.bpm - track_b.beatgrid.bpm)
        style_delta = abs(self._style_profile(track_a)["density"] - self._style_profile(track_b)["density"])
        harmonic_adjacent = bool(track_a.key.camelot and track_b.key.camelot and self._camelot_is_adjacent(track_a.key.camelot, track_b.key.camelot))
        if bpm_delta > 8 or delta > 0.58:
            return TransitionType.ECHO_OUT
        if a_phrase and b_phrase and a_phrase.phrase_type == PhraseType.DROP and b_phrase.phrase_type == PhraseType.DROP and delta < 0.22:
            return TransitionType.CUT_SWAP
        if a_phrase and b_phrase and a_phrase.phrase_type == PhraseType.BUILD and b_phrase.phrase_type in {PhraseType.CHORUS, PhraseType.DROP}:
            return TransitionType.RISER
        if delta >= 0.30 and b_value < a_value and (style_delta > 0.18 or not harmonic_adjacent):
            return TransitionType.MELODIC_RESET
        if delta <= 0.24 and bpm_delta <= 3 and style_delta <= 0.20:
            return TransitionType.TRIPLET_SWAP
        return TransitionType.CLEAN_BLEND

    def _strategy_bias(self, strategy: TransitionType) -> tuple[float, list[str]]:
        bias = {
            TransitionType.CLEAN_BLEND: 0.80,
            TransitionType.ECHO_OUT: 0.82,
            TransitionType.RISER: 0.90,
            TransitionType.CUT_SWAP: 0.93,
            TransitionType.TRIPLET_SWAP: 0.91,
            TransitionType.MELODIC_RESET: 0.88,
        }[strategy]
        return bias, [f"Strategy bias applied for {strategy.value}."]

    def _overlap_for_strategy(self, strategy: TransitionType) -> int:
        return {
            TransitionType.CLEAN_BLEND: 32,
            TransitionType.ECHO_OUT: 4,
            TransitionType.RISER: 16,
            TransitionType.CUT_SWAP: 1,
            TransitionType.TRIPLET_SWAP: 3,
            TransitionType.MELODIC_RESET: 8,
        }[strategy]

    def _bar_start_time(self, track: TrackMetadata, bar: int) -> float:
        for beat in track.beatgrid.beats:
            if beat.bar == bar and beat.beat_in_bar == 1:
                return beat.time
        return 0.0

    def _camelot_is_adjacent(self, a: str, b: str) -> bool:
        try:
            num_a, letter_a = int(a[:-1]), a[-1]
            num_b, letter_b = int(b[:-1]), b[-1]
        except ValueError:
            return False
        if letter_a == letter_b and ((num_a - num_b) % 12 in {1, 11}):
            return True
        return num_a == num_b and letter_a != letter_b

    def _is_eight_count_boundary(self, bar: int) -> bool:
        return (bar - 1) % 2 == 0

    def _is_phrase_edge(self, bar: int, phrase: PhraseSegment | None) -> bool:
        return bool(phrase and (bar == phrase.start_bar or bar == phrase.end_bar))

    def _phrase_progress(self, bar: int, phrase: PhraseSegment) -> float:
        span = max(phrase.end_bar - phrase.start_bar + 1, 1)
        return (bar - phrase.start_bar) / span

    def _bar_energy_slope(self, track: TrackMetadata, bar: int) -> float:
        current = track.energy_at_bar(bar)
        previous = track.energy_at_bar(max(1, bar - 1))
        following = track.energy_at_bar(min(track.bar_count(), bar + 1))
        if not current:
            return 0.0
        prev_val = previous.combined if previous else current.combined
        next_val = following.combined if following else current.combined
        return (next_val - prev_val) / 2.0

    def _style_profile(self, track: TrackMetadata) -> dict[str, float]:
        energies = [point.combined for point in track.energy_bars]
        avg_energy = sum(energies) / len(energies) if energies else 0.5
        high_energy = sum(1 for point in track.energy_bars if point.combined >= 0.72)
        impact_ratio = high_energy / max(len(track.energy_bars), 1)
        drop_like = sum(1 for phrase in track.phrases if phrase.phrase_type in {PhraseType.DROP, PhraseType.CHORUS, PhraseType.BUILD})
        phrase_ratio = drop_like / max(len(track.phrases), 1)
        density = min(1.0, avg_energy * 0.55 + impact_ratio * 0.25 + phrase_ratio * 0.20)
        return {"density": density}
