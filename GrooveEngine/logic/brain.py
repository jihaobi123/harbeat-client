"""Bar-candidate transition planning logic for GrooveEngine."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from audio.offline_renderer import OfflineDualDeckRenderer
from audio.sync import DEFAULT_TIME_STRETCH_PROVIDER, describe_time_stretch_provider
from core.datatypes import PhraseSegment, TrackMetadata, TransitionPlan, TransitionWindowScore
from core.enums import PhraseType, TransitionType
from logic.reporting import build_candidate_search_report, candidate_row
from logic.strategies import STRATEGY_REGISTRY


@dataclass(slots=True)
class PlannerWeights:
    phrase_alignment: float = 0.16
    energy_delta: float = 0.12
    harmonic: float = 0.08
    strategy_bias: float = 0.12
    bar_position: float = 0.10
    style_fit: float = 0.08
    phase_alignment: float = 0.14
    spectral_conflict: float = 0.08
    loudness_continuity: float = 0.06
    dance_continuity: float = 0.06
    sync_quality: float = 0.04


@dataclass(slots=True)
class TransitionSearchCandidate:
    exit_bar: int
    entry_bar: int
    overlap_beats: int
    target_bpm: float
    phase_offset_beats: float
    handoff_profile: str
    strategy: TransitionType


class TransitionPlanner:
    def __init__(self, weights: PlannerWeights | None = None) -> None:
        self.weights = weights or PlannerWeights()

    def plan(self, a: TrackMetadata, b: TrackMetadata) -> TransitionPlan:
        best = self.top_candidates(a, b, limit=1)[0]
        plan = TransitionPlan(mix_start_time=self._bar_start_time(a, best.track_a_exit_bar), overlap_duration_beats=best.overlap_beats, target_bpm=best.target_bpm, phase_offset_beats=best.phase_offset_beats, alignment_confidence=best.alignment_confidence, handoff_profile=best.handoff_profile, strategy=best.strategy, track_a_exit_bar=best.track_a_exit_bar, track_b_entry_bar=best.track_b_entry_bar, automation=[], score_breakdown=best)
        plan.automation = STRATEGY_REGISTRY[best.strategy].build_automation(plan)
        return plan

    def plan_with_strategy(self, a: TrackMetadata, b: TrackMetadata, strategy: TransitionType) -> TransitionPlan:
        candidates = self.top_candidates(a, b, limit=20)
        match = next((c for c in candidates if c.strategy == strategy), None)
        best = match or candidates[0]
        plan = TransitionPlan(mix_start_time=self._bar_start_time(a, best.track_a_exit_bar), overlap_duration_beats=best.overlap_beats, target_bpm=best.target_bpm, phase_offset_beats=best.phase_offset_beats, alignment_confidence=best.alignment_confidence, handoff_profile=best.handoff_profile, strategy=best.strategy, track_a_exit_bar=best.track_a_exit_bar, track_b_entry_bar=best.track_b_entry_bar, automation=[], score_breakdown=best)
        plan.automation = STRATEGY_REGISTRY[best.strategy].build_automation(plan)
        return plan

    def top_candidates(self, a: TrackMetadata, b: TrackMetadata, limit: int = 5) -> list[TransitionWindowScore]:
        ranked = sorted((self._score_candidate(a, b, c) for c in self._generate_search_candidates(a, b)), key=lambda x: x.total_score, reverse=True)
        for i, item in enumerate(ranked, start=1):
            item.search_rank = i
        return ranked[: max(1, limit)]

    def candidate_report(self, a: TrackMetadata, b: TrackMetadata, limit: int = 5, render_shortlist_limit: int | None = None) -> dict[str, object]:
        candidates = self.top_candidates(a, b, limit=limit)
        rows = [candidate_row(label=f"{a.title} -> {b.title}", candidate=item) for item in candidates]
        shortlist_size = max(1, min(render_shortlist_limit or min(3, len(rows) or 1), len(rows) or 1))
        rows = self._render_validate_shortlist(a, b, candidates, rows, shortlist_size)
        final_rows = sorted(rows, key=lambda row: float(row.get("final_score", row.get("score", 0.0))), reverse=True)
        for index, row in enumerate(final_rows, start=1):
            row["final_rank"] = index
            row["score"] = float(row.get("final_score", row.get("score", 0.0)))
        return build_candidate_search_report(
            title=f"{a.title} -> {b.title}",
            rows=final_rows,
            metadata={
                "track_a_id": a.track_id,
                "track_b_id": b.track_id,
                "track_a_title": a.title,
                "track_b_title": b.title,
                "candidate_count": len(candidates),
                "analysis_candidate_count": len(candidates),
                "render_validation_shortlist_count": shortlist_size,
                "two_stage_selection": True,
                "track_a_sync": self._track_sync_summary(a),
                "track_b_sync": self._track_sync_summary(b),
            },
        )


    def _render_validate_shortlist(self, a: TrackMetadata, b: TrackMetadata, candidates: list[TransitionWindowScore], rows: list[dict[str, object]], shortlist_size: int) -> list[dict[str, object]]:
        if not candidates or not rows:
            return rows
        renderer = OfflineDualDeckRenderer()
        audio_a = self._preview_audio(a)
        audio_b = self._preview_audio(b)
        validated = [dict(row) for row in rows]
        for index, candidate in enumerate(candidates):
            if index >= shortlist_size:
                break
            row = validated[index]
            row["render_validation_available"] = True
            try:
                plan = TransitionPlan(
                    mix_start_time=self._bar_start_time(a, candidate.track_a_exit_bar),
                    overlap_duration_beats=candidate.overlap_beats,
                    target_bpm=candidate.target_bpm,
                    phase_offset_beats=candidate.phase_offset_beats,
                    alignment_confidence=candidate.alignment_confidence,
                    handoff_profile=candidate.handoff_profile,
                    strategy=candidate.strategy,
                    track_a_exit_bar=candidate.track_a_exit_bar,
                    track_b_entry_bar=candidate.track_b_entry_bar,
                    automation=[],
                    score_breakdown=candidate,
                )
                plan.automation = STRATEGY_REGISTRY[candidate.strategy].build_automation(plan)
                result = renderer.render_transition(audio_a, a, a.title, plan, audio_b, b, b.title)
                summary = result.transition_summary
                render_score = self._render_validation_score(summary)
                analysis_score = float(row.get("analysis_score", candidate.total_score))
                final_score = self._combine_analysis_and_render_scores(analysis_score, render_score)
                row.update({
                    "render_validation_status": "validated",
                    "render_validation_error": "",
                    "render_validation_score": render_score,
                    "final_score": final_score,
                    "score_delta_after_render": final_score - analysis_score,
                    "score": final_score,
                    "render_peak_db": float(summary.get("peak_db", summary.get("render_peak_db", 0.0))),
                    "render_rms_db": float(summary.get("rms_db", summary.get("render_rms_db", 0.0))),
                    "render_headroom_db": float(summary.get("headroom_db", summary.get("render_headroom_db", 0.0))),
                    "render_loudness_delta_db": abs(float(summary.get("loudness_delta_db", summary.get("render_loudness_delta_db", 0.0)))),
                    "render_spectral_conflict": float(summary.get("low_band_conflict", summary.get("spectral_conflict", summary.get("render_spectral_conflict", 0.0)))),
                    "render_low_band_conflict": float(summary.get("low_band_conflict", 0.0)),
                    "render_bass_overlap_indicator": float(summary.get("bass_overlap_indicator", 0.0)),
                    "render_transient_loss_indicator": float(summary.get("transient_loss_indicator", 0.0)),
                    "render_groove_softening_indicator": float(summary.get("groove_softening_indicator", 0.0)),
                    "render_vocal_overlap_risk": float(summary.get("vocal_overlap_risk", 0.0)),
                    "render_summary": summary,
                })
            except Exception as exc:
                row.update({
                    "render_validation_status": "failed",
                    "render_validation_error": str(exc),
                    "render_validation_score": None,
                    "final_score": float(row.get("analysis_score", candidate.total_score)),
                    "score_delta_after_render": 0.0,
                    "score": float(row.get("analysis_score", candidate.total_score)),
                })
        return validated

    def _preview_audio(self, metadata: TrackMetadata, seconds: float = 24.0) -> np.ndarray:
        sample_rate = int(metadata.sample_rate)
        frame_count = max(sample_rate, int(sample_rate * seconds))
        timeline = np.arange(frame_count, dtype=np.float32) / sample_rate
        base_freq = 55.0 + (metadata.beatgrid.bpm % 80.0)
        accent = 110.0 + (metadata.beatgrid.bpm % 120.0)
        pulse = 0.55 + 0.45 * np.sin(2.0 * np.pi * max(metadata.beatgrid.bpm / 60.0, 0.5) * timeline)
        left = 0.10 * np.sin(2.0 * np.pi * base_freq * timeline) * pulse
        right = 0.08 * np.sin(2.0 * np.pi * accent * timeline + 0.35) * pulse
        return np.column_stack([left, right]).astype(np.float32)

    def _render_validation_score(self, summary: dict[str, object]) -> float:
        loudness = abs(float(summary.get("loudness_delta_db", summary.get("render_loudness_delta_db", 0.0))))
        spectral = float(summary.get("low_band_conflict", summary.get("spectral_conflict", summary.get("render_spectral_conflict", 0.0))))
        headroom = float(summary.get("headroom_db", summary.get("render_headroom_db", 0.0)))
        transient = max(float(summary.get("transient_loss_indicator", 0.0)), float(summary.get("groove_softening_indicator", 0.0)))
        peak = float(summary.get("peak_db", summary.get("render_peak_db", 0.0)))
        loudness_score = 1.0 - min(loudness / 12.0, 1.0)
        spectral_score = 1.0 - min(max(spectral, 0.0), 1.0)
        headroom_score = min(max(headroom / 6.0, 0.0), 1.0)
        peak_score = 1.0 - min(max(peak + 0.2, 0.0) / 3.0, 1.0)
        transient_score = 1.0 - min(max(transient, 0.0), 1.0)
        return float(np.clip(loudness_score * 0.26 + spectral_score * 0.28 + headroom_score * 0.18 + peak_score * 0.12 + transient_score * 0.16, 0.0, 1.0))

    def _combine_analysis_and_render_scores(self, analysis_score: float, render_score: float) -> float:
        return float(np.clip(analysis_score * 0.58 + render_score * 0.42, 0.0, 1.0))

    def _generate_search_candidates(self, a: TrackMetadata, b: TrackMetadata) -> list[TransitionSearchCandidate]:
        out: list[TransitionSearchCandidate] = []
        bpms = list(dict.fromkeys([round(a.beatgrid.bpm, 3), round((a.beatgrid.bpm + b.beatgrid.bpm) / 2.0, 3), round(b.beatgrid.bpm, 3)]))
        overlaps = self._candidate_overlap_beats(a, b)
        phase_offsets = self._candidate_phase_offsets(a, b)
        handoff_profiles = self._candidate_handoff_profiles(a, b)
        for xb in self._candidate_exit_bars(a):
            for yb in self._candidate_entry_bars(b):
                for ov in overlaps:
                    for tbpm in bpms:
                        for po in phase_offsets:
                            for hp in handoff_profiles:
                                for s in self._candidate_strategies_for_window(a, b, xb, yb, ov, hp):
                                    out.append(TransitionSearchCandidate(xb, yb, ov, tbpm, po, hp, s))
        return out

    def _candidate_overlap_beats(self, a: TrackMetadata, b: TrackMetadata) -> list[int]:
        overlaps = [4, 8, 16, 32]
        analyzer_safe_max = min(a.beat_analysis.recommended_max_overlap_beats, b.beat_analysis.recommended_max_overlap_beats)
        provider_safe_max = min(
            int(self._provider_sync_summary(a, b)["recommended_max_overlap_beats"]),
            analyzer_safe_max,
        )
        drift_risk = max(a.beat_analysis.phase_drift_risk, b.beat_analysis.phase_drift_risk)
        phrase_sync_ok = a.beat_analysis.phrase_sync_usable and b.beat_analysis.phrase_sync_usable
        long_blend_ok = a.beat_analysis.long_blend_usable and b.beat_analysis.long_blend_usable
        if drift_risk >= 0.72:
            provider_safe_max = min(provider_safe_max, 8)
        elif drift_risk >= 0.58:
            provider_safe_max = min(provider_safe_max, 16)
        overlaps = [ov for ov in overlaps if ov <= max(4, provider_safe_max)]
        if not long_blend_ok:
            overlaps = [ov for ov in overlaps if ov <= 16]
        if not phrase_sync_ok:
            overlaps = [ov for ov in overlaps if ov <= 8]
        return overlaps or [4]

    def _candidate_phase_offsets(self, a: TrackMetadata, b: TrackMetadata) -> tuple[float, ...]:
        if a.beat_analysis.ambiguous_bar_phase or b.beat_analysis.ambiguous_bar_phase:
            return (0.0,)
        if max(a.beat_analysis.phase_drift_risk, b.beat_analysis.phase_drift_risk) >= 0.60:
            return (0.0,)
        if min(a.beat_analysis.sub_beat_confidence, b.beat_analysis.sub_beat_confidence) < 0.55:
            return (0.0,)
        if min(a.beat_analysis.local_window_stability_min, b.beat_analysis.local_window_stability_min) < 0.55:
            return (0.0, 0.5)
        return (0.0, 0.5, 1.0)

    def _candidate_handoff_profiles(self, a: TrackMetadata, b: TrackMetadata) -> tuple[str, ...]:
        if not (a.beat_analysis.long_blend_usable and b.beat_analysis.long_blend_usable):
            return ("reset_cut", "bass_swap")
        return ("smooth_blend", "bass_swap", "reset_cut")

    def _candidate_exit_bars(self, t: TrackMetadata) -> list[int]:
        last = t.bar_count(); start = max(1, last - 48)
        bars = [bar for bar in range(start, last + 1) if self._is_candidate_bar(t, bar)]
        return bars or [max(1, last - 16)]

    def _candidate_entry_bars(self, t: TrackMetadata) -> list[int]:
        end = min(t.bar_count(), 49)
        bars = [bar for bar in range(1, end + 1) if self._is_candidate_bar(t, bar)]
        return bars or [1]

    def _candidate_strategies_for_window(self, a: TrackMetadata, b: TrackMetadata, xb: int, yb: int, ov: int, hp: str) -> list[TransitionType]:
        ap, bp = a.phrase_at_bar(xb), b.phrase_at_bar(yb)
        if ov <= 4:
            items = [TransitionType.CUT_SWAP, TransitionType.ECHO_OUT]
        elif ov <= 8:
            items = [TransitionType.ECHO_OUT, TransitionType.TRIPLET_SWAP, TransitionType.MELODIC_RESET]
        else:
            items = [TransitionType.CLEAN_BLEND, TransitionType.RISER, TransitionType.MELODIC_RESET]
        if hp == "bass_swap" and ov >= 8:
            items.append(TransitionType.CLEAN_BLEND)
        if hp == "reset_cut":
            items += [TransitionType.CUT_SWAP, TransitionType.MELODIC_RESET]
        if ap and bp and ap.phrase_type == PhraseType.BUILD and bp.phrase_type in {PhraseType.CHORUS, PhraseType.DROP}:
            items.append(TransitionType.RISER)
        if not (a.beat_analysis.phrase_sync_usable and b.beat_analysis.phrase_sync_usable):
            items = [item for item in items if item not in {TransitionType.CLEAN_BLEND, TransitionType.TRIPLET_SWAP}] or [TransitionType.CUT_SWAP, TransitionType.ECHO_OUT]
        return list(dict.fromkeys(items))

    def _is_candidate_bar(self, t: TrackMetadata, bar: int) -> bool:
        p = t.phrase_at_bar(bar)
        return self._is_eight_count_boundary(bar) or self._is_phrase_edge(bar, p) or any(a.bar == bar for a in t.phrase_anchors)

    def _score_candidate(self, a: TrackMetadata, b: TrackMetadata, c: TransitionSearchCandidate) -> TransitionWindowScore:
        phrase, p_notes = self._score_phrase(a, b, c); energy, e_notes = self._score_energy(a, b, c); harmonic, h_notes = self._score_harmonic(a, b); strategy, s_notes = self._score_strategy(a, b, c); bar_pos, b_notes = self._score_bar_position(a, b, c); style, st_notes = self._score_style(a, b); phase, phase_error, align_conf, drift_risk, recommended_overlap, ph_notes = self._score_phase(a, b, c); spectral, sp_notes = self._score_spectral(a, b, c); loudness, l_notes = self._score_loudness(a, b, c); dance, d_notes = self._score_dance(a, b, c)
        provider_sync = self._provider_sync_summary(a, b)
        sync_quality = self._score_sync_provider(provider_sync, c)
        w = self.weights; total = phrase*w.phrase_alignment + energy*w.energy_delta + harmonic*w.harmonic + strategy*w.strategy_bias + bar_pos*w.bar_position + style*w.style_fit + phase*w.phase_alignment + spectral*w.spectral_conflict + loudness*w.loudness_continuity + dance*w.dance_continuity + sync_quality*w.sync_quality
        return TransitionWindowScore(track_a_exit_bar=c.exit_bar, track_b_entry_bar=c.entry_bar, overlap_beats=c.overlap_beats, target_bpm=c.target_bpm, phase_offset_beats=c.phase_offset_beats, phase_error_beats=phase_error, alignment_confidence=align_conf, handoff_profile=c.handoff_profile, phrase_score=phrase, energy_score=energy, harmonic_score=harmonic, strategy_bias_score=strategy, phase_alignment_score=phase, spectral_conflict_score=spectral, loudness_continuity_score=loudness, dance_continuity_score=dance, sync_drift_risk=drift_risk, recommended_max_overlap_beats=recommended_overlap, total_score=max(0.0, min(total, 1.0)), strategy=c.strategy, notes=p_notes + e_notes + h_notes + s_notes + b_notes + st_notes + ph_notes + sp_notes + l_notes + d_notes)

    def _score_phrase(self, a: TrackMetadata, b: TrackMetadata, c: TransitionSearchCandidate) -> tuple[float, list[str]]:
        ap, bp = a.phrase_at_bar(c.exit_bar), b.phrase_at_bar(c.entry_bar)
        score, notes = 1.0, []
        if not self._is_eight_count_boundary(c.exit_bar): score -= 0.18; notes.append("Track A exit misses 8-count boundary.")
        if not self._is_eight_count_boundary(c.entry_bar): score -= 0.18; notes.append("Track B entry misses 8-count boundary.")
        if ap and self._phrase_progress(c.exit_bar, ap) < 0.45: score -= 0.18; notes.append(f"Track A exits early in {ap.phrase_type.value}.")
        if bp and self._phrase_progress(c.entry_bar, bp) > 0.35: score -= 0.20; notes.append(f"Track B enters mid-{bp.phrase_type.value}.")
        return max(score, 0.0), notes or ["Phrase placement looks usable."]

    def _score_energy(self, a: TrackMetadata, b: TrackMetadata, c: TransitionSearchCandidate) -> tuple[float, list[str]]:
        ae, be = a.energy_at_bar(c.exit_bar), b.energy_at_bar(c.entry_bar)
        if not ae or not be: return 0.5, ["Missing energy data."]
        delta = abs(ae.combined - be.combined)
        return max(0.0, 1.0 - delta), [f"Energy delta {delta:.3f}."]

    def _score_harmonic(self, a: TrackMetadata, b: TrackMetadata) -> tuple[float, list[str]]:
        if a.key.tonic == b.key.tonic: return 1.0, ["Matching tonal center."]
        if a.key.camelot and b.key.camelot and self._camelot_is_adjacent(a.key.camelot, b.key.camelot): return 0.72, ["Adjacent Camelot move."]
        return 0.35, ["Harmonic mismatch."]

    def _score_strategy(self, a: TrackMetadata, b: TrackMetadata, c: TransitionSearchCandidate) -> tuple[float, list[str]]:
        score = {TransitionType.CLEAN_BLEND: 0.80, TransitionType.ECHO_OUT: 0.82, TransitionType.RISER: 0.90, TransitionType.CUT_SWAP: 0.93, TransitionType.TRIPLET_SWAP: 0.91, TransitionType.MELODIC_RESET: 0.88}[c.strategy]
        phrase_sync_ok = a.beat_analysis.phrase_sync_usable and b.beat_analysis.phrase_sync_usable
        if c.strategy == TransitionType.CLEAN_BLEND and c.handoff_profile == "bass_swap":
            score += 0.08
        if c.strategy == TransitionType.CLEAN_BLEND and abs(a.beatgrid.bpm - b.beatgrid.bpm) > 6.0:
            score -= 0.18
        if not phrase_sync_ok and c.strategy in {TransitionType.CLEAN_BLEND, TransitionType.TRIPLET_SWAP}:
            score -= 0.16
        if a.beat_analysis.ambiguous_bar_phase or b.beat_analysis.ambiguous_bar_phase:
            if c.strategy == TransitionType.TRIPLET_SWAP:
                score -= 0.18
            if c.strategy in {TransitionType.CUT_SWAP, TransitionType.ECHO_OUT, TransitionType.MELODIC_RESET}:
                score += 0.04
        return max(0.0, min(score, 1.0)), [f"Strategy {c.strategy.value}, handoff {c.handoff_profile}."]

    def _score_bar_position(self, a: TrackMetadata, b: TrackMetadata, c: TransitionSearchCandidate) -> tuple[float, list[str]]:
        ap, bp = a.phrase_at_bar(c.exit_bar), b.phrase_at_bar(c.entry_bar)
        score = 0.75 + (0.15 if ap and self._phrase_progress(c.exit_bar, ap) >= 0.75 else 0.0) + (0.15 if bp and self._phrase_progress(c.entry_bar, bp) <= 0.12 else 0.0)
        return min(score, 1.0), [f"Bar anchors {c.exit_bar}->{c.entry_bar}."]

    def _score_style(self, a: TrackMetadata, b: TrackMetadata) -> tuple[float, list[str]]:
        delta = abs(self._style_profile(a) - self._style_profile(b))
        return max(0.35, 1.0 - delta), [f"Style density delta {delta:.3f}."]

    def _score_phase(self, a: TrackMetadata, b: TrackMetadata, c: TransitionSearchCandidate) -> tuple[float, float, float, float, int, list[str]]:
        bpm_error = abs(c.target_bpm - a.beatgrid.bpm) + abs(c.target_bpm - b.beatgrid.bpm)
        sub_beat_confidence = min(a.beat_analysis.sub_beat_confidence, b.beat_analysis.sub_beat_confidence)
        phase_error = c.phase_offset_beats + max(a.beat_analysis.estimated_phase_error_beats, b.beat_analysis.estimated_phase_error_beats) + (0.5 if self._is_eight_count_boundary(c.exit_bar) != self._is_eight_count_boundary(c.entry_bar) else 0.0)
        align = min(a.beat_analysis.beat_confidence, b.beat_analysis.beat_confidence) * 0.28 + min(a.beat_analysis.downbeat_confidence, b.beat_analysis.downbeat_confidence) * 0.24 + min(a.beat_analysis.bar_phase_confidence, b.beat_analysis.bar_phase_confidence) * 0.20 + sub_beat_confidence * 0.28
        score = (1.0 - min(bpm_error / 12.0, 1.0) * 0.30 - min(phase_error / 2.5, 1.0) * 0.30) * 0.55 + align * 0.45
        local_min = min(a.beat_analysis.local_window_stability_min, b.beat_analysis.local_window_stability_min)
        drift_risk = max(a.beat_analysis.phase_drift_risk, b.beat_analysis.phase_drift_risk)
        recommended_overlap = min(a.beat_analysis.recommended_max_overlap_beats, b.beat_analysis.recommended_max_overlap_beats)
        if not (a.beat_analysis.long_blend_usable and b.beat_analysis.long_blend_usable) and c.overlap_beats > 12:
            score -= 0.08
        if a.beat_analysis.ambiguous_bar_phase or b.beat_analysis.ambiguous_bar_phase:
            score -= 0.08
        if c.overlap_beats > recommended_overlap:
            score -= min((c.overlap_beats - recommended_overlap) / 24.0, 0.22)
        if drift_risk >= 0.58:
            score -= min((drift_risk - 0.58) * 0.42, 0.14)
        if drift_risk >= 0.70 and c.overlap_beats > 8:
            score -= 0.08
        if sub_beat_confidence < 0.55:
            score -= 0.06
        if sub_beat_confidence < 0.45 and c.phase_offset_beats != 0.0:
            score -= 0.05
        if local_min < 0.50:
            score -= min((0.50 - local_min) * 0.30, 0.08)
        notes = [f"Target BPM {c.target_bpm:.3f}, phase offset {c.phase_offset_beats:.2f} beats.", f"Local beat stability floor {local_min:.3f}.", f"Sync drift risk {drift_risk:.3f}; recommended overlap max {recommended_overlap} beats."]
        if c.overlap_beats > recommended_overlap:
            notes.append(f"Requested overlap {c.overlap_beats} exceeds recommended safe max {recommended_overlap}.")
        if drift_risk >= 0.58 and c.overlap_beats > 8:
            notes.append("Drift risk penalizes long blend.")
        if sub_beat_confidence < 0.55:
            notes.append("Conservative phase search due to low sub-beat confidence.")
        if a.beat_analysis.ambiguous_bar_phase or b.beat_analysis.ambiguous_bar_phase:
            notes.append("Ambiguous bar phase reduces phrase-locked sync confidence.")
        return max(0.0, min(score, 1.0)), min(phase_error, 2.5), max(0.0, min(1.0, align)), drift_risk, recommended_overlap, notes

    def _provider_sync_summary(self, a: TrackMetadata, b: TrackMetadata) -> dict[str, object]:
        target_bpm = (a.beatgrid.bpm + b.beatgrid.bpm) / 2.0
        rate_a = a.beatgrid.bpm / max(target_bpm, 1.0)
        rate_b = b.beatgrid.bpm / max(target_bpm, 1.0)
        provider_a = describe_time_stretch_provider(DEFAULT_TIME_STRETCH_PROVIDER, playback_rate=rate_a)
        provider_b = describe_time_stretch_provider(DEFAULT_TIME_STRETCH_PROVIDER, playback_rate=rate_b)
        return {
            "provider_name": DEFAULT_TIME_STRETCH_PROVIDER,
            "sync_quality_score": min(float(provider_a["sync_quality_score"]), float(provider_b["sync_quality_score"])),
            "recommended_max_overlap_beats": min(int(provider_a["recommended_max_overlap_beats"]), int(provider_b["recommended_max_overlap_beats"])),
            "suitable_for_short_transition": bool(provider_a["suitable_for_short_transition"] and provider_b["suitable_for_short_transition"]),
            "suitable_for_long_transition": bool(provider_a["suitable_for_long_transition"] and provider_b["suitable_for_long_transition"]),
            "prototype_only": bool(provider_a["prototype_only"] or provider_b["prototype_only"]),
            "notes": list(dict.fromkeys(list(provider_a["notes"]) + list(provider_b["notes"]))),
        }

    def _score_sync_provider(self, provider_sync: dict[str, object], c: TransitionSearchCandidate) -> float:
        score = float(provider_sync["sync_quality_score"])
        if c.overlap_beats > int(provider_sync["recommended_max_overlap_beats"]):
            score -= 0.12
        if c.overlap_beats > 8 and not bool(provider_sync["suitable_for_long_transition"]):
            score -= 0.14
        if c.overlap_beats > 16 and bool(provider_sync["prototype_only"]):
            score -= 0.08
        return max(0.0, min(score, 1.0))

    def _score_spectral(self, a: TrackMetadata, b: TrackMetadata, c: TransitionSearchCandidate) -> tuple[float, list[str]]:
        ba, bb = a.band_at_bar(c.exit_bar), b.band_at_bar(c.entry_bar)
        if not ba or not bb:
            return 0.5, ["Missing spectral descriptors."]
        raw = min(ba.sub + ba.bass, bb.sub + bb.bass) * 0.5 + min(ba.low_mid + ba.mid, bb.low_mid + bb.mid) * 0.3 + min(ba.vocal_presence, bb.vocal_presence) * 0.2
        score = max(0.0, 1.0 - min(raw, 1.0))
        if c.handoff_profile == "bass_swap":
            score += 0.12
        elif c.handoff_profile == "reset_cut":
            score += 0.16
        return max(0.0, min(score, 1.0)), [f"Spectral conflict {raw:.3f}."]

    def _score_loudness(self, a: TrackMetadata, b: TrackMetadata, c: TransitionSearchCandidate) -> tuple[float, list[str]]:
        la, lb = a.loudness_at_bar(c.exit_bar), b.loudness_at_bar(c.entry_bar)
        if not la or not lb:
            return 0.5, ["Missing loudness profile."]
        rms_delta = abs(la.rms_db - lb.rms_db)
        short_delta = abs(la.short_loudness - lb.short_loudness)
        score = 1.0 - min(rms_delta / 18.0, 1.0) * 0.6 - min(short_delta, 1.0) * 0.4
        return max(0.0, min(score, 1.0)), [f"Loudness delta {rms_delta:.2f} dB."]

    def _score_dance(self, a: TrackMetadata, b: TrackMetadata, c: TransitionSearchCandidate) -> tuple[float, list[str]]:
        da, db = a.danceability_at_bar(c.exit_bar), b.danceability_at_bar(c.entry_bar)
        if not da or not db:
            return 0.5, ["Missing danceability profile."]
        anchor = min(self._anchor_strength(a, c.exit_bar), self._anchor_strength(b, c.entry_bar))
        groove_delta = abs(da.groove_stability - db.groove_stability)
        score = ((da.eight_count_clarity + db.eight_count_clarity + db.downbeat_clarity) / 3.0) * 0.55 + anchor * 0.25 + (1.0 - groove_delta) * 0.20
        if c.strategy in {TransitionType.TRIPLET_SWAP, TransitionType.CLEAN_BLEND}:
            score += 0.06
        return max(0.0, min(score, 1.0)), [f"Dance groove delta {groove_delta:.3f}."]

    def _bar_start_time(self, t: TrackMetadata, bar: int) -> float:
        for beat in t.beatgrid.beats:
            if beat.bar == bar and beat.beat_in_bar == 1:
                return beat.time
        return 0.0

    def _camelot_is_adjacent(self, a: str, b: str) -> bool:
        try:
            na, la, nb, lb = int(a[:-1]), a[-1], int(b[:-1]), b[-1]
        except ValueError:
            return False
        return (la == lb and ((na - nb) % 12 in {1, 11})) or (na == nb and la != lb)

    def _is_eight_count_boundary(self, bar: int) -> bool:
        return (bar - 1) % 2 == 0

    def _is_phrase_edge(self, bar: int, phrase: PhraseSegment | None) -> bool:
        return bool(phrase and (bar == phrase.start_bar or bar == phrase.end_bar))

    def _phrase_progress(self, bar: int, phrase: PhraseSegment) -> float:
        return (bar - phrase.start_bar) / max(phrase.end_bar - phrase.start_bar + 1, 1)

    def _style_profile(self, t: TrackMetadata) -> float:
        es = [p.combined for p in t.energy_bars]
        avg = sum(es) / len(es) if es else 0.5
        impact = sum(1 for p in t.energy_bars if p.combined >= 0.72) / max(len(t.energy_bars), 1)
        phr = sum(1 for p in t.phrases if p.phrase_type in {PhraseType.DROP, PhraseType.CHORUS, PhraseType.BUILD}) / max(len(t.phrases), 1)
        return min(1.0, avg * 0.55 + impact * 0.25 + phr * 0.20)

    def _track_sync_summary(self, t: TrackMetadata) -> dict[str, object]:
        return {
            "beat_usable": t.beat_analysis.beat_usable,
            "phrase_sync_usable": t.beat_analysis.phrase_sync_usable,
            "long_blend_usable": t.beat_analysis.long_blend_usable,
            "drift_prone": t.beat_analysis.drift_prone,
            "phase_drift_risk": t.beat_analysis.phase_drift_risk,
            "sub_beat_confidence": t.beat_analysis.sub_beat_confidence,
            "recommended_max_overlap_beats": t.beat_analysis.recommended_max_overlap_beats,
            "sync_warnings": t.beat_analysis.sync_warnings,
        }

    def _anchor_strength(self, t: TrackMetadata, bar: int) -> float:
        vals = [a.strength for a in t.phrase_anchors if a.bar == bar]
        return max(vals) if vals else (0.45 if self._is_eight_count_boundary(bar) else 0.25)
