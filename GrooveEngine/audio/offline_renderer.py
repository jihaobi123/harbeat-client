from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from audio.mixer_fx import MixerFX
from audio.sync import SyncPreparation, beats_to_frames, build_sync_alignment_result, ensure_stereo, prepare_track_for_mix
from core.datatypes import BandDescriptor, LoudnessPoint, SyncAlignmentResult, TrackMetadata, TransitionPlan
from core.enums import FXType


EPSILON = 1e-9


@dataclass(slots=True)
class OfflineRenderResult:
    audio: np.ndarray
    sample_rate: int
    transition_summary: dict[str, object]
    render_trace: list[dict[str, float | int | str | bool]]


@dataclass(slots=True)
class OfflineDeckState:
    deck_id: str
    audio: np.ndarray
    source_start_frame: int
    anchor_frame: int
    playback_rate: float

    def source_frame_at(self, timeline_frame: int) -> int:
        return self.source_start_frame + timeline_frame


@dataclass(slots=True)
class BandHandoffState:
    gain_a: float
    gain_b: float
    low_a: float
    low_b: float
    mid_a: float
    mid_b: float
    high_a: float
    high_b: float


@dataclass(slots=True)
class OfflineRenderContext:
    prep_a: SyncPreparation
    prep_b: SyncPreparation
    deck_a: OfflineDeckState
    deck_b: OfflineDeckState
    prefix: np.ndarray
    timeline_frames: int
    overlap_frames: int
    transition_start_frame: int
    master_duration_beats: float
    phase_offset_frames: int
    anchor_timeline_frame_a: int
    anchor_timeline_frame_b: int
    alignment: SyncAlignmentResult
    effective_phase_correction_beats: float
    effective_phase_correction_frames: int


class OfflineDualDeckRenderer:
    def __init__(self, sample_rate: int = 44100, block_size: int = 2048, time_stretch_provider: str | None = None) -> None:
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.time_stretch_provider = time_stretch_provider

    def render_transition(self, audio_a: np.ndarray, metadata_a: TrackMetadata, title_a: str, plan: TransitionPlan, audio_b: np.ndarray, metadata_b: TrackMetadata, title_b: str) -> OfflineRenderResult:
        context = self._build_render_context(audio_a, metadata_a, plan, audio_b, metadata_b)
        mixed_timeline, diagnostics, render_trace = self._render_timeline(context, metadata_a, metadata_b, plan)
        audio = np.vstack([context.prefix, mixed_timeline]).astype(np.float32, copy=False)
        stabilized, output_stats = self.stabilize_output(audio)
        objective_metrics = self._objective_transition_metrics(stabilized, context, metadata_a, metadata_b, plan)
        phrase_a = metadata_a.phrase_at_bar(plan.track_a_exit_bar)
        phrase_b = metadata_b.phrase_at_bar(plan.track_b_entry_bar)
        summary = {
            "track_a": title_a,
            "track_b": title_b,
            "strategy": plan.strategy.value,
            "handoff_profile": plan.handoff_profile,
            "track_a_exit_bar": plan.track_a_exit_bar,
            "track_b_entry_bar": plan.track_b_entry_bar,
            "track_a_exit_phrase": phrase_a.phrase_type.value if phrase_a else "unknown",
            "track_b_entry_phrase": phrase_b.phrase_type.value if phrase_b else "unknown",
            "overlap_beats": plan.overlap_duration_beats,
            "target_bpm": plan.target_bpm,
            "score": plan.score_breakdown.total_score,
            "sync_backend": diagnostics["sync_backend"],
            "sync_backend_a": diagnostics["sync_backend_a"],
            "sync_backend_b": diagnostics["sync_backend_b"],
            "sync_source_bpm_a": diagnostics["sync_source_bpm_a"],
            "sync_source_bpm_b": diagnostics["sync_source_bpm_b"],
            "sync_playback_rate_a": diagnostics["sync_playback_rate_a"],
            "sync_playback_rate_b": diagnostics["sync_playback_rate_b"],
            "spectral_conflict": diagnostics["spectral_conflict"],
            "peak_db": output_stats["peak_db"],
            "rms_db": output_stats["rms_db"],
            "headroom_db": output_stats["headroom_db"],
            "loudness_delta_db": objective_metrics["loudness_delta_db"],
            "low_band_conflict": objective_metrics["low_band_conflict"],
            "bass_overlap_indicator": objective_metrics["bass_overlap_indicator"],
            "transient_loss_indicator": objective_metrics["transient_loss_indicator"],
            "groove_softening_indicator": objective_metrics["groove_softening_indicator"],
            "vocal_overlap_risk": objective_metrics["vocal_overlap_risk"],
            "render_spectral_conflict": diagnostics["spectral_conflict"],
            "render_loudness_delta_db": objective_metrics["loudness_delta_db"],
            "render_gain_a": diagnostics["gain_a"], "render_gain_b": diagnostics["gain_b"],
            "render_low_a": diagnostics["low_a"], "render_low_b": diagnostics["low_b"],
            "render_mid_a": diagnostics["mid_a"], "render_mid_b": diagnostics["mid_b"],
            "render_high_a": diagnostics["high_a"], "render_high_b": diagnostics["high_b"],
            "render_anchor_time_a": diagnostics["anchor_time_a"], "render_anchor_time_b": diagnostics["anchor_time_b"],
            "render_start_time_a": diagnostics["start_time_a"], "render_start_time_b": diagnostics["start_time_b"],
            "render_anchor_timeline_time_a": diagnostics["anchor_timeline_time_a"],
            "render_anchor_timeline_time_b": diagnostics["anchor_timeline_time_b"],
            "render_anchor_delta_beats": diagnostics["anchor_delta_beats"],
            "render_effective_phase_correction_beats": diagnostics["effective_phase_correction_beats"],
            "render_requested_phase_offset": diagnostics["requested_phase_offset_beats"],
            "render_phase_offset_applied": diagnostics["phase_offset_beats_applied"],
            "render_phase_error_estimate": diagnostics["phase_error_estimate"],
            "render_drift_risk": diagnostics["drift_risk"],
            "render_long_overlap_safe": diagnostics["long_overlap_safe"],
            "render_long_blend_safe": diagnostics["long_blend_safe"],
            "render_recommended_max_overlap_beats": diagnostics["recommended_max_overlap_beats"],
            "render_sync_warning_count": diagnostics["sync_warning_count"],
            "render_master_duration_beats": diagnostics["master_duration_beats"],
            "render_overlap_frames": context.overlap_frames,
            "render_transition_start_frame": context.transition_start_frame,
            "render_transition_end_frame": context.transition_start_frame + context.timeline_frames,
            "render_peak_db": output_stats["peak_db"], "render_rms_db": output_stats["rms_db"],
            "render_headroom_db": output_stats["headroom_db"], "render_output_gain": output_stats["output_gain"],
            "render_limiter_reduction_db": output_stats["limiter_reduction_db"],
            "sync_alignment": context.alignment.model_dump(mode="json"),
            "notes": plan.score_breakdown.notes + diagnostics["notes"] + output_stats["notes"] + objective_metrics["notes"],
        }
        summary["render_trace_blocks"] = len(render_trace)
        return OfflineRenderResult(audio=stabilized, sample_rate=self.sample_rate, transition_summary=summary, render_trace=render_trace)

    def stabilize_output(self, audio: np.ndarray) -> tuple[np.ndarray, dict[str, object]]:
        stereo = ensure_stereo(audio)
        peak = float(np.max(np.abs(stereo))) if stereo.size else 0.0
        rms = float(np.sqrt(np.mean(np.square(stereo))) + EPSILON) if stereo.size else 1e-9
        output_gain, limiter_reduction_db, notes = 1.0, 0.0, []
        if peak > 0.0:
            peak_gain = min(1.0, 0.93 / peak)
            output_gain *= peak_gain
            if peak_gain < 0.999:
                limiter_reduction_db = float(-20.0 * np.log10(max(peak_gain, 1e-6)))
                notes.append(f"Output peak control applied: {limiter_reduction_db:.2f} dB reduction.")
        if rms < 0.10 and peak < 0.70:
            output_gain *= min(1.08, 0.14 / max(rms, 1e-6))
            notes.append("Low-level render received gentle makeup gain.")
        stabilized = np.clip(stereo * output_gain, -0.98, 0.98).astype(np.float32, copy=False)
        final_peak = float(np.max(np.abs(stabilized))) if stabilized.size else 0.0
        final_rms = float(np.sqrt(np.mean(np.square(stabilized))) + EPSILON) if stabilized.size else 1e-9
        return stabilized, {"peak_db": float(20.0 * np.log10(max(final_peak, 1e-6))), "rms_db": float(20.0 * np.log10(max(final_rms, 1e-6))), "headroom_db": float(-20.0 * np.log10(max(final_peak, 1e-6))), "output_gain": float(output_gain), "limiter_reduction_db": limiter_reduction_db, "notes": notes}

    def _build_render_context(self, audio_a: np.ndarray, metadata_a: TrackMetadata, plan: TransitionPlan, audio_b: np.ndarray, metadata_b: TrackMetadata) -> OfflineRenderContext:
        prep_a = prepare_track_for_mix(audio_a, metadata_a, self.sample_rate, plan.target_bpm, provider=self.time_stretch_provider)
        prep_b = prepare_track_for_mix(audio_b, metadata_b, self.sample_rate, plan.target_bpm, provider=self.time_stretch_provider)
        transition_start_frame = self._clamp_frame(int(plan.mix_start_time * self.sample_rate), len(prep_a.audio))
        overlap_frames = max(beats_to_frames(plan.overlap_duration_beats, plan.target_bpm, self.sample_rate), self.block_size)
        alignment, frames = build_sync_alignment_result(metadata_a, metadata_b, plan, prep_a, prep_b, self.sample_rate, transition_start_frame)
        phase_correction_frames = self._resolve_phase_correction_frames(plan, alignment)
        corrected_anchor_timeline_frame_b = max(frames["anchor_timeline_frame_b"] + phase_correction_frames, 0)
        deck_a = OfflineDeckState("A", prep_a.audio, transition_start_frame, frames["anchor_frame_a"], prep_a.playback_rate)
        deck_b = OfflineDeckState("B", prep_b.audio, frames["anchor_frame_b"] - corrected_anchor_timeline_frame_b, frames["anchor_frame_b"], prep_b.playback_rate)
        remaining_a = max(len(prep_a.audio) - deck_a.source_start_frame, 0)
        remaining_b = max(len(prep_b.audio) - max(deck_b.source_start_frame, 0), 0) + max(-deck_b.source_start_frame, 0)
        timeline_frames = max(overlap_frames, remaining_a, remaining_b, corrected_anchor_timeline_frame_b + self.block_size)
        prefix = ensure_stereo(prep_a.audio[:transition_start_frame])
        master_duration_beats = timeline_frames / self.sample_rate * (plan.target_bpm / 60.0)
        effective_phase_correction_frames = corrected_anchor_timeline_frame_b - frames["anchor_timeline_frame_a"]
        effective_phase_correction_beats = effective_phase_correction_frames / self.sample_rate * (plan.target_bpm / 60.0)
        alignment.effective_phase_offset_beats = effective_phase_correction_beats
        alignment.applied_phase_offset_beats = effective_phase_correction_beats
        alignment.timeline_anchor_time_b = corrected_anchor_timeline_frame_b / self.sample_rate
        return OfflineRenderContext(prep_a, prep_b, deck_a, deck_b, prefix, timeline_frames, overlap_frames, transition_start_frame, master_duration_beats, effective_phase_correction_frames, frames["anchor_timeline_frame_a"], corrected_anchor_timeline_frame_b, alignment, effective_phase_correction_beats, effective_phase_correction_frames)

    def _render_timeline(self, context: OfflineRenderContext, metadata_a: TrackMetadata, metadata_b: TrackMetadata, plan: TransitionPlan) -> tuple[np.ndarray, dict[str, object], list[dict[str, float | int | str | bool]]]:
        fx = MixerFX(sample_rate=self.sample_rate)
        handoff = self._resolve_band_handoff(metadata_a, metadata_b, plan)
        conflict_value = self._conflict_strength(metadata_a, metadata_b, plan)
        loudness_delta, loudness_notes = self._loudness_adjustments(metadata_a, metadata_b, plan)
        blocks: list[np.ndarray] = []
        render_trace: list[dict[str, float | int | str | bool]] = []
        for start in range(0, context.timeline_frames, self.block_size):
            end = min(start + self.block_size, context.timeline_frames)
            beat_position = start / self.sample_rate * (plan.target_bpm / 60.0)
            fx.apply_automation(plan.automation, beat_position)
            self._apply_band_automation(fx, beat_position, plan.overlap_duration_beats, handoff)
            block_a = self._read_synced_block(context.deck_a, start, end)
            block_b = self._read_synced_block(context.deck_b, start, end)
            processed_a = fx.process_deck("A", block_a * handoff.gain_a)
            processed_b = fx.process_deck("B", block_b * handoff.gain_b)
            blocks.append(self._smooth_loudness(fx.mix(processed_a, processed_b, fx.master_noise_level()), loudness_delta))
            render_trace.append({
                "block_index": int(start // self.block_size),
                "start_frame": int(start),
                "end_frame": int(end),
                "beat_position": float(beat_position),
                "progress": float(1.0 if plan.overlap_duration_beats <= 0.0 else np.clip(beat_position / plan.overlap_duration_beats, 0.0, 1.0)),
                "gain_a": float(handoff.gain_a),
                "gain_b": float(handoff.gain_b),
                "low_a": float(fx.automation_state.values["A"].get(FXType.LOW_EQ, 1.0)),
                "low_b": float(fx.automation_state.values["B"].get(FXType.LOW_EQ, 1.0)),
                "mid_a": float(fx.automation_state.values["A"].get(FXType.MID_EQ, 1.0)),
                "mid_b": float(fx.automation_state.values["B"].get(FXType.MID_EQ, 1.0)),
                "high_a": float(fx.automation_state.values["A"].get(FXType.HIGH_EQ, 1.0)),
                "high_b": float(fx.automation_state.values["B"].get(FXType.HIGH_EQ, 1.0)),
                "source_start_a": int(context.deck_a.source_frame_at(start)),
                "source_start_b": int(context.deck_b.source_frame_at(start)),
                "anchor_delta_beats": float(context.alignment.anchor_delta_beats),
                "effective_phase_correction_beats": float(context.effective_phase_correction_beats),
                "phase_error_estimate": float(context.alignment.estimated_phase_error_beats),
                "drift_risk": float(context.alignment.drift_risk),
                "long_overlap_safe": bool(context.alignment.long_overlap_safe),
                "long_blend_safe": bool(context.alignment.long_blend_safe),
                "handoff_profile": plan.handoff_profile,
                "sync_backend": context.prep_a.provider_name,
            })
        anchor_delta_beats = context.alignment.anchor_delta_beats
        diagnostics = {
            "sync_backend": context.prep_a.provider_name,
            "sync_backend_a": context.prep_a.provider_name,
            "sync_backend_b": context.prep_b.provider_name,
            "sync_source_bpm_a": context.prep_a.source_bpm,
            "sync_source_bpm_b": context.prep_b.source_bpm,
            "sync_playback_rate_a": context.prep_a.playback_rate,
            "sync_playback_rate_b": context.prep_b.playback_rate,
            "spectral_conflict": conflict_value, "loudness_delta_db": loudness_delta,
            "gain_a": handoff.gain_a, "gain_b": handoff.gain_b,
            "low_a": handoff.low_a, "low_b": handoff.low_b,
            "mid_a": handoff.mid_a, "mid_b": handoff.mid_b,
            "high_a": handoff.high_a, "high_b": handoff.high_b,
            "anchor_time_a": context.alignment.anchor_time_a,
            "anchor_time_b": context.alignment.anchor_time_b,
            "start_time_a": context.deck_a.source_start_frame / self.sample_rate,
            "start_time_b": context.deck_b.source_start_frame / self.sample_rate,
            "anchor_timeline_time_a": context.alignment.timeline_anchor_time_a,
            "anchor_timeline_time_b": context.alignment.timeline_anchor_time_b,
            "anchor_delta_beats": anchor_delta_beats,
            "effective_phase_correction_beats": context.effective_phase_correction_beats,
            "requested_phase_offset_beats": context.alignment.requested_phase_offset_beats,
            "phase_offset_beats_applied": context.alignment.applied_phase_offset_beats,
            "phase_error_estimate": context.alignment.estimated_phase_error_beats,
            "drift_risk": context.alignment.drift_risk,
            "long_overlap_safe": context.alignment.long_overlap_safe,
            "long_blend_safe": context.alignment.long_blend_safe,
            "recommended_max_overlap_beats": context.alignment.recommended_max_overlap_beats,
            "sync_warning_count": len(context.alignment.notes),
            "master_duration_beats": context.master_duration_beats,
            "notes": loudness_notes + context.alignment.notes + self._render_alignment_notes(context, plan) + [f"Sync backend {context.prep_a.provider_name} prepared deck A at {context.prep_a.source_bpm:.3f}->{plan.target_bpm:.3f} BPM and deck B at {context.prep_b.source_bpm:.3f}->{plan.target_bpm:.3f} BPM.", f"Anchor-true alignment placed deck B anchor at {anchor_delta_beats:.2f} beats relative to deck A.", f"Band-aware handoff low/mid/high = A({handoff.low_a:.2f}/{handoff.mid_a:.2f}/{handoff.high_a:.2f}) B({handoff.low_b:.2f}/{handoff.mid_b:.2f}/{handoff.high_b:.2f}).", f"Timeline render used {context.timeline_frames} frames across {context.master_duration_beats:.2f} beats."],
        }
        return np.vstack(blocks).astype(np.float32, copy=False), diagnostics, render_trace

    def _objective_transition_metrics(
        self,
        stabilized: np.ndarray,
        context: OfflineRenderContext,
        metadata_a: TrackMetadata,
        metadata_b: TrackMetadata,
        plan: TransitionPlan,
    ) -> dict[str, object]:
        stereo = ensure_stereo(stabilized)
        overlap_start = int(np.clip(context.transition_start_frame, 0, len(stereo)))
        overlap_end = int(np.clip(context.transition_start_frame + context.overlap_frames, overlap_start, len(stereo)))
        overlap = stereo[overlap_start:overlap_end]
        analysis_window_frames = max(self.block_size, beats_to_frames(min(plan.overlap_duration_beats, 2.0), plan.target_bpm, self.sample_rate))
        pre_window = self._slice_window(stereo, overlap_start - analysis_window_frames, overlap_start)
        post_window = self._slice_window(stereo, overlap_end, overlap_end + analysis_window_frames)
        if len(post_window) == 0:
            post_window = self._slice_window(stereo, max(overlap_end - analysis_window_frames, overlap_start), overlap_end)
        if len(pre_window) == 0:
            pre_window = self._slice_window(stereo, overlap_start, overlap_start + analysis_window_frames)

        overlap_mono = self._mono(overlap)
        pre_mono = self._mono(pre_window)
        post_mono = self._mono(post_window)
        low_energy_overlap = self._band_energy(overlap_mono, 20.0, 180.0)
        full_energy_overlap = self._band_energy(overlap_mono, 20.0, 12000.0)
        low_ratio = low_energy_overlap / max(full_energy_overlap, EPSILON)

        band_a = metadata_a.band_at_bar(plan.track_a_exit_bar) or BandDescriptor(bar=plan.track_a_exit_bar)
        band_b = metadata_b.band_at_bar(plan.track_b_entry_bar) or BandDescriptor(bar=plan.track_b_entry_bar)
        bass_overlap_indicator = float(np.clip(min(band_a.sub + band_a.bass, band_b.sub + band_b.bass) * np.clip(low_ratio / 0.42, 0.0, 1.2), 0.0, 1.0))
        low_band_conflict = float(np.clip(0.65 * bass_overlap_indicator + 0.35 * np.clip(low_ratio / 0.55, 0.0, 1.0), 0.0, 1.0))

        pre_transient = self._transient_activity(pre_mono)
        post_transient = self._transient_activity(post_mono)
        overlap_transient = self._transient_activity(overlap_mono)
        baseline_transient = max(pre_transient, post_transient, EPSILON)
        transient_loss_indicator = float(np.clip((baseline_transient - overlap_transient) / baseline_transient, 0.0, 1.0))

        descriptor_transient = max(band_a.transient_density, band_b.transient_density, 0.2)
        groove_softening_indicator = float(np.clip(0.6 * transient_loss_indicator + 0.4 * np.clip(descriptor_transient - overlap_transient, 0.0, 1.0), 0.0, 1.0))

        vocal_descriptor_overlap = min(1.0, band_a.vocal_presence + band_b.vocal_presence)
        vocal_mid_energy = self._band_energy(overlap_mono, 300.0, 3000.0) / max(full_energy_overlap, EPSILON)
        vocal_overlap_risk = float(np.clip(0.7 * vocal_descriptor_overlap + 0.3 * np.clip(vocal_mid_energy / 0.45, 0.0, 1.0), 0.0, 1.0))

        pre_rms_db = self._rms_db(pre_window)
        post_rms_db = self._rms_db(post_window)
        loudness_delta_db = float(post_rms_db - pre_rms_db)

        return {
            "loudness_delta_db": loudness_delta_db,
            "low_band_conflict": low_band_conflict,
            "bass_overlap_indicator": bass_overlap_indicator,
            "transient_loss_indicator": transient_loss_indicator,
            "groove_softening_indicator": groove_softening_indicator,
            "vocal_overlap_risk": vocal_overlap_risk,
            "notes": [
                f"Objective overlap low-band conflict estimated at {low_band_conflict:.2f} from rendered overlap energy and bar descriptors.",
                f"Objective transient loss estimated at {transient_loss_indicator:.2f} relative to adjacent rendered sections.",
                f"Objective vocal overlap risk estimated at {vocal_overlap_risk:.2f} using vocal_presence descriptors plus overlap mid-band energy.",
            ],
        }

    def _render_alignment_notes(self, context: OfflineRenderContext, plan: TransitionPlan) -> list[str]:
        notes: list[str] = []
        if context.alignment.recommended_max_overlap_beats is not None and plan.overlap_duration_beats > context.alignment.recommended_max_overlap_beats:
            notes.append(
                f"Overlap exceeds recommended max: {plan.overlap_duration_beats:.1f} beats requested vs {context.alignment.recommended_max_overlap_beats} beats recommended."
            )
        if context.prep_a.prototype_only or context.prep_b.prototype_only:
            notes.append("Provider is prototype-only for long blend on at least one deck.")
        if context.alignment.drift_risk >= 0.65:
            notes.append(f"Drift risk is elevated for this render ({context.alignment.drift_risk:.2f}).")
        if abs(context.effective_phase_correction_beats - context.alignment.requested_phase_offset_beats) > 0.05:
            notes.append(
                f"Effective phase correction settled at {context.effective_phase_correction_beats:.2f} beats for a requested {context.alignment.requested_phase_offset_beats:.2f} beats."
            )
        return notes

    def _resolve_phase_correction_frames(self, plan: TransitionPlan, alignment: SyncAlignmentResult) -> int:
        requested_frames = beats_to_frames(plan.phase_offset_beats, plan.target_bpm, self.sample_rate)
        effective_frames = beats_to_frames(alignment.effective_phase_offset_beats, plan.target_bpm, self.sample_rate)
        frame_delta = requested_frames - effective_frames
        if abs(frame_delta) <= 1:
            return 0
        correction = int(round(frame_delta * 0.5))
        max_correction = beats_to_frames(0.25, plan.target_bpm, self.sample_rate)
        return int(np.clip(correction, -max_correction, max_correction))

    def _read_synced_block(self, deck: OfflineDeckState, start: int, end: int) -> np.ndarray:
        output = np.zeros((end - start, 2), dtype=np.float32)
        source_start, source_end = deck.source_frame_at(start), deck.source_frame_at(end)
        copy_start, copy_end = max(source_start, 0), min(source_end, len(deck.audio))
        if copy_end <= copy_start:
            return output
        out_start = copy_start - source_start
        output[out_start:out_start + (copy_end - copy_start)] = ensure_stereo(deck.audio[copy_start:copy_end])
        return output

    def _apply_band_automation(self, fx: MixerFX, beat_position: float, overlap_beats: float, handoff: BandHandoffState) -> None:
        progress = 1.0 if overlap_beats <= 0.0 else float(np.clip(beat_position / overlap_beats, 0.0, 1.0))
        smooth = progress * progress * (3.0 - 2.0 * progress)
        fx.automation_state.values["A"][FXType.LOW_EQ] = handoff.low_a + (1.0 - handoff.low_a) * (1.0 - smooth)
        fx.automation_state.values["A"][FXType.MID_EQ] = handoff.mid_a + (1.0 - handoff.mid_a) * (1.0 - smooth)
        fx.automation_state.values["A"][FXType.HIGH_EQ] = handoff.high_a + (1.0 - handoff.high_a) * (1.0 - smooth)
        fx.automation_state.values["B"][FXType.LOW_EQ] = handoff.low_b + (1.0 - handoff.low_b) * smooth
        fx.automation_state.values["B"][FXType.MID_EQ] = handoff.mid_b + (1.0 - handoff.mid_b) * smooth
        fx.automation_state.values["B"][FXType.HIGH_EQ] = handoff.high_b + (1.0 - handoff.high_b) * smooth

    def _resolve_band_handoff(self, metadata_a: TrackMetadata, metadata_b: TrackMetadata, plan: TransitionPlan) -> BandHandoffState:
        band_a = metadata_a.band_at_bar(plan.track_a_exit_bar) or BandDescriptor(bar=plan.track_a_exit_bar)
        band_b = metadata_b.band_at_bar(plan.track_b_entry_bar) or BandDescriptor(bar=plan.track_b_entry_bar)
        bass_conflict = min(band_a.sub + band_a.bass, band_b.sub + band_b.bass)
        mid_conflict = min(band_a.low_mid + band_a.mid + band_a.vocal_presence, band_b.low_mid + band_b.mid + band_b.vocal_presence)
        high_conflict = min(band_a.high, band_b.high)
        if plan.handoff_profile == "reset_cut":
            return BandHandoffState(0.92, 1.0, 0.18, 1.0, 0.55, 0.95, 0.72, 1.0)
        if plan.handoff_profile == "bass_swap":
            return BandHandoffState(float(np.clip(1.0 - bass_conflict * 0.18, 0.78, 1.0)), 1.0, float(np.clip(0.18 - bass_conflict * 0.10, 0.0, 0.22)), 1.0, float(np.clip(0.90 - mid_conflict * 0.12, 0.62, 1.0)), float(np.clip(0.92 - mid_conflict * 0.08, 0.70, 1.0)), float(np.clip(0.94 - high_conflict * 0.08, 0.72, 1.0)), float(np.clip(0.98 - high_conflict * 0.06, 0.78, 1.0)))
        return BandHandoffState(float(np.clip(1.0 - bass_conflict * 0.12 - mid_conflict * 0.05, 0.80, 1.0)), float(np.clip(1.0 - high_conflict * 0.04, 0.88, 1.0)), float(np.clip(0.45 - bass_conflict * 0.12, 0.18, 0.55)), float(np.clip(0.88 - bass_conflict * 0.06, 0.70, 1.0)), float(np.clip(0.82 - mid_conflict * 0.10, 0.58, 0.92)), float(np.clip(0.88 - mid_conflict * 0.06, 0.68, 1.0)), float(np.clip(0.92 - high_conflict * 0.08, 0.70, 1.0)), float(np.clip(0.94 - high_conflict * 0.05, 0.76, 1.0)))

    def _conflict_strength(self, metadata_a: TrackMetadata, metadata_b: TrackMetadata, plan: TransitionPlan) -> float:
        band_a = metadata_a.band_at_bar(plan.track_a_exit_bar) or BandDescriptor(bar=plan.track_a_exit_bar)
        band_b = metadata_b.band_at_bar(plan.track_b_entry_bar) or BandDescriptor(bar=plan.track_b_entry_bar)
        bass = min(band_a.sub + band_a.bass, band_b.sub + band_b.bass) * 0.5
        vocal = min(band_a.vocal_presence, band_b.vocal_presence) * 0.25
        high = min(band_a.high, band_b.high) * 0.15
        return float(min(bass + vocal + high, 1.0))

    def _loudness_adjustments(self, metadata_a: TrackMetadata, metadata_b: TrackMetadata, plan: TransitionPlan) -> tuple[float, list[str]]:
        loud_a = metadata_a.loudness_at_bar(plan.track_a_exit_bar) or LoudnessPoint(bar=plan.track_a_exit_bar)
        loud_b = metadata_b.loudness_at_bar(plan.track_b_entry_bar) or LoudnessPoint(bar=plan.track_b_entry_bar)
        delta_db = float(loud_b.rms_db - loud_a.rms_db)
        return delta_db, [f"Render loudness smoothing target delta: {delta_db:.2f} dB."]

    def _smooth_loudness(self, mixed: np.ndarray, loudness_delta_db: float) -> np.ndarray:
        if abs(loudness_delta_db) < 1.0:
            return mixed
        return np.clip(mixed * float(np.clip(1.0 - loudness_delta_db / 24.0, 0.85, 1.12)), -1.0, 1.0).astype(np.float32, copy=False)

    def _slice_window(self, audio: np.ndarray, start: int, end: int) -> np.ndarray:
        if len(audio) == 0:
            return np.zeros((0, 2), dtype=np.float32)
        clamped_start = int(np.clip(start, 0, len(audio)))
        clamped_end = int(np.clip(end, clamped_start, len(audio)))
        return ensure_stereo(audio[clamped_start:clamped_end])

    def _mono(self, audio: np.ndarray) -> np.ndarray:
        stereo = ensure_stereo(audio)
        if len(stereo) == 0:
            return np.zeros(0, dtype=np.float32)
        return np.mean(stereo, axis=1).astype(np.float32, copy=False)

    def _rms_db(self, audio: np.ndarray) -> float:
        stereo = ensure_stereo(audio)
        if len(stereo) == 0:
            return -120.0
        rms = float(np.sqrt(np.mean(np.square(stereo))) + EPSILON)
        return float(20.0 * np.log10(max(rms, 1e-6)))

    def _transient_activity(self, mono: np.ndarray) -> float:
        if len(mono) < 4:
            return 0.0
        diff = np.abs(np.diff(mono))
        peak = float(np.max(np.abs(mono)) + EPSILON)
        return float(np.clip(np.mean(diff) / peak, 0.0, 1.0))

    def _band_energy(self, mono: np.ndarray, low_hz: float, high_hz: float) -> float:
        if len(mono) < 32:
            return 0.0
        spectrum = np.fft.rfft(mono)
        freqs = np.fft.rfftfreq(len(mono), d=1.0 / self.sample_rate)
        mask = (freqs >= low_hz) & (freqs < high_hz)
        if not np.any(mask):
            return 0.0
        return float(np.mean(np.abs(spectrum[mask]) ** 2))

    def _clamp_frame(self, frame: int, length: int) -> int:
        return max(0, min(frame, length))
