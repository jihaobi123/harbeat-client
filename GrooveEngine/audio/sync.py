"""Offline sync helpers for dual-deck rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import librosa
import numpy as np

from core.datatypes import SyncAlignmentResult, TrackMetadata, TransitionPlan

DEFAULT_TIME_STRETCH_PROVIDER = "librosa"

ProviderQualityTier = Literal["preview", "standard", "hq"]


@dataclass(slots=True)
class SyncPreparation:
    """Prepared audio aligned to target BPM for offline rendering."""

    audio: np.ndarray
    sample_rate: int
    target_bpm: float
    playback_rate: float
    provider_name: str
    source_bpm: float
    quality_tier: str
    suitable_for_long_blend: bool
    provider_quality_tier: ProviderQualityTier = "standard"
    suitable_for_short_transition: bool = True
    suitable_for_long_transition: bool = False
    prototype_only: bool = False
    recommended_max_overlap_beats: int = 8
    notes: list[str] | None = None

    def __post_init__(self) -> None:
        if self.notes is None:
            self.notes = []



class TimeStretchProvider(Protocol):
    """Simple offline time-stretch provider interface."""

    provider_name: str

    def stretch(self, audio: np.ndarray, rate: float) -> np.ndarray: ...


class LibrosaTimeStretchProvider:
    """Current default librosa-based offline stretch implementation."""

    provider_name = "librosa"

    def stretch(self, audio: np.ndarray, rate: float) -> np.ndarray:
        return _librosa_time_stretch_stereo(audio, rate)


class IdentityTimeStretchProvider:
    """Preview provider that only passes through already-close tempos."""

    provider_name = "identity"

    def stretch(self, audio: np.ndarray, rate: float) -> np.ndarray:
        stereo = ensure_stereo(audio)
        if abs(rate - 1.0) <= 0.08:
            return stereo
        return _librosa_time_stretch_stereo(stereo, rate)


class OfflineHQTimeStretchProvider:
    """Experimental HQ-ish provider using rate-aware dry/stretched blending."""

    provider_name = "offline_hq"

    def stretch(self, audio: np.ndarray, rate: float) -> np.ndarray:
        stereo = ensure_stereo(audio)
        delta = abs(rate - 1.0)
        if delta <= 0.02:
            return stereo
        stretched = _librosa_time_stretch_stereo(stereo, rate)
        if delta > 0.10:
            return stretched
        blend = float(np.clip((delta - 0.02) / 0.08, 0.0, 1.0))
        dry_mix = 0.35 * (1.0 - blend)
        return _blend_with_reference(stereo, stretched, dry_mix=dry_mix)


def ensure_stereo(audio: np.ndarray) -> np.ndarray:
    """Return audio as stereo float32 array in frame-major layout."""

    if audio.ndim == 1:
        audio = audio[:, np.newaxis]
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    return audio.astype(np.float32, copy=False)


def _resolve_playback_rate(source_bpm: float, target_bpm: float) -> float:
    """Return playback rate needed to reach target tempo."""

    return source_bpm / max(target_bpm, 1.0)


def _match_sample_rate(audio: np.ndarray, source_sample_rate: int, target_sample_rate: int) -> np.ndarray:
    """Resample stereo audio only when sample rates differ."""

    stereo = ensure_stereo(audio)
    if source_sample_rate == target_sample_rate:
        return stereo
    return np.stack(
        [
            librosa.resample(stereo[:, channel], orig_sr=source_sample_rate, target_sr=target_sample_rate)
            for channel in range(stereo.shape[1])
        ],
        axis=1,
    ).astype(np.float32)


def _blend_with_reference(reference: np.ndarray, processed: np.ndarray, dry_mix: float) -> np.ndarray:
    """Blend stretched audio with dry reference while preserving processed length."""

    wet_mix = 1.0 - dry_mix
    wet = ensure_stereo(processed)
    target_len = len(wet)
    if target_len <= 0:
        return wet
    dry = ensure_stereo(reference)
    if len(dry) == 0:
        return wet
    if len(dry) == target_len:
        aligned_dry = dry
    else:
        aligned_dry = np.stack(
            [
                librosa.resample(dry[:, channel], orig_sr=len(dry), target_sr=target_len)
                for channel in range(dry.shape[1])
            ],
            axis=1,
        ).astype(np.float32)
    return (aligned_dry[:target_len] * dry_mix + wet[:target_len] * wet_mix).astype(np.float32, copy=False)


def _librosa_time_stretch_stereo(audio: np.ndarray, rate: float) -> np.ndarray:
    """Apply librosa offline time stretch to stereo audio."""

    stereo = ensure_stereo(audio)
    if abs(rate - 1.0) <= 0.01:
        return stereo
    channels: list[np.ndarray] = []
    for index in range(stereo.shape[1]):
        stretched = librosa.effects.time_stretch(stereo[:, index], rate=rate)
        channels.append(stretched.astype(np.float32))
    min_len = min(len(channel) for channel in channels)
    return np.stack([channel[:min_len] for channel in channels], axis=1)


def _provider_capability_defaults(provider_name: str, playback_rate: float) -> tuple[ProviderQualityTier, bool, bool, bool, int, float, list[str]]:
    """Return simple heuristic capability flags for a provider."""

    rate_delta = abs(playback_rate - 1.0)
    notes: list[str] = []
    if provider_name == "identity":
        notes.append("identity provider is intended for near-unity tempo adjustments.")
        if rate_delta > 0.08:
            notes.append("Requested tempo change exceeds identity comfort zone; quality may degrade.")
        return "preview", rate_delta <= 0.05, False, False, 8, 0.42, notes
    if provider_name == "offline_hq":
        notes.append("offline_hq provider is more suitable for longer offline overlaps.")
        notes.append("offline_hq remains prototype-oriented and should stay offline-only.")
        return "hq", True, True, True, 32, 0.82, notes
    notes.append("librosa provider offers general-purpose offline time stretching.")
    notes.append("Long transitions should stay conservative with librosa provider.")
    return "standard", True, False, False, 16, 0.64, notes


def _merge_unique_notes(*note_groups: list[str]) -> list[str]:
    """Return notes with stable order and duplicates removed."""

    merged: list[str] = []
    for group in note_groups:
        for note in group:
            if note not in merged:
                merged.append(note)
    return merged


def _recommended_overlap_limit(metadata: TrackMetadata, provider_limit: int) -> int:
    """Combine analyzer and provider overlap guidance."""

    return max(1, min(metadata.beat_analysis.recommended_max_overlap_beats, provider_limit))


def _stretched_time_for_bar(metadata: TrackMetadata, preparation: SyncPreparation, bar: int) -> float:
    """Return anchor time in prepared-track seconds for a bar."""

    return bar_start_time(metadata, bar) / max(preparation.playback_rate, 1e-6)


def get_time_stretch_provider(provider: str | TimeStretchProvider | None = None) -> TimeStretchProvider:
    """Resolve a named provider or return the provided provider instance."""

    if provider is None:
        return LibrosaTimeStretchProvider()
    if hasattr(provider, "stretch") and hasattr(provider, "provider_name"):
        return provider
    name = str(provider).strip().lower()
    if name in {"librosa", "default"}:
        return LibrosaTimeStretchProvider()
    if name in {"identity", "preview", "passthrough"}:
        return IdentityTimeStretchProvider()
    if name in {"offline_hq", "offline-hq", "hq"}:
        return OfflineHQTimeStretchProvider()
    raise ValueError(f"Unknown time stretch provider: {provider}")


def time_stretch_stereo(audio: np.ndarray, rate: float, provider: str | TimeStretchProvider | None = None) -> np.ndarray:
    """Apply offline time stretch using the requested provider."""

    resolved_provider = get_time_stretch_provider(provider)
    return resolved_provider.stretch(audio, rate)


def prepare_track_for_mix(
    audio: np.ndarray,
    metadata: TrackMetadata,
    sample_rate: int,
    target_bpm: float,
    provider: str | TimeStretchProvider | None = None,
) -> SyncPreparation:
    """Prepare audio for offline deck rendering at the target tempo."""

    resolved_provider = get_time_stretch_provider(provider)
    source_audio = ensure_stereo(audio)
    playback_rate = _resolve_playback_rate(metadata.beatgrid.bpm, target_bpm)
    stretched = resolved_provider.stretch(source_audio, playback_rate)
    prepared_audio = _match_sample_rate(stretched, metadata.sample_rate, sample_rate)
    capability_tier, suitable_short, suitable_long, prototype_only, provider_overlap_limit, provider_sync_score, capability_notes = _provider_capability_defaults(
        resolved_provider.provider_name,
        playback_rate,
    )
    recommended_max_overlap = _recommended_overlap_limit(metadata, provider_overlap_limit)
    notes = _merge_unique_notes(capability_notes, metadata.beat_analysis.sync_warnings)
    return SyncPreparation(
        audio=prepared_audio,
        sample_rate=sample_rate,
        target_bpm=target_bpm,
        playback_rate=playback_rate,
        provider_name=resolved_provider.provider_name,
        source_bpm=metadata.beatgrid.bpm,
        quality_tier=capability_tier,
        suitable_for_long_blend=metadata.beat_analysis.long_blend_usable and suitable_long,
        provider_quality_tier=capability_tier,
        suitable_for_short_transition=suitable_short,
        suitable_for_long_transition=metadata.beat_analysis.long_blend_usable and suitable_long,
        prototype_only=prototype_only,
        recommended_max_overlap_beats=recommended_max_overlap,
        notes=notes,
    )


def describe_time_stretch_provider(provider: str | TimeStretchProvider | None = None, playback_rate: float = 1.0) -> dict[str, object]:
    """Return normalized provider capability diagnostics."""

    resolved_provider = get_time_stretch_provider(provider)
    quality_tier, suitable_short, suitable_long, prototype_only, recommended_overlap, sync_score, notes = _provider_capability_defaults(
        resolved_provider.provider_name,
        playback_rate,
    )
    return {
        "provider_name": resolved_provider.provider_name,
        "provider_quality_tier": quality_tier,
        "suitable_for_short_transition": suitable_short,
        "suitable_for_long_transition": suitable_long,
        "prototype_only": prototype_only,
        "recommended_max_overlap_beats": recommended_overlap,
        "sync_quality_score": sync_score,
        "notes": list(notes),
    }


def anchor_frame_for_bar(metadata: TrackMetadata, preparation: SyncPreparation, bar: int, sample_rate: int) -> int:
    """Return the stretched frame index for a bar anchor."""

    time = _stretched_time_for_bar(metadata, preparation, bar)
    frame = int(round(time * sample_rate))
    return max(0, min(frame, len(preparation.audio)))


def bar_start_time(metadata: TrackMetadata, bar: int) -> float:
    """Return the source-time start of a bar."""

    for beat in metadata.beatgrid.beats:
        if beat.bar == bar and beat.beat_in_bar == 1:
            return beat.time
    return 0.0


def beats_to_frames(beats: float, bpm: float, sample_rate: int) -> int:
    """Convert beats to frame count."""

    return int(round(beats * 60.0 / max(bpm, 1.0) * sample_rate))


def build_sync_alignment_result(
    metadata_a: TrackMetadata,
    metadata_b: TrackMetadata,
    plan: TransitionPlan,
    prep_a: SyncPreparation,
    prep_b: SyncPreparation,
    sample_rate: int,
    transition_start_frame: int,
) -> tuple[SyncAlignmentResult, dict[str, int]]:
    """Build normalized render-time alignment diagnostics."""

    anchor_time_a = _stretched_time_for_bar(metadata_a, prep_a, plan.track_a_exit_bar)
    anchor_time_b = _stretched_time_for_bar(metadata_b, prep_b, plan.track_b_entry_bar)
    anchor_frame_a = int(round(anchor_time_a * sample_rate))
    anchor_frame_b = int(round(anchor_time_b * sample_rate))
    requested_phase_frames = beats_to_frames(plan.phase_offset_beats, plan.target_bpm, sample_rate)
    anchor_timeline_frame_a = max(anchor_frame_a - transition_start_frame, 0)
    anchor_timeline_frame_b = max(anchor_timeline_frame_a + requested_phase_frames, 0)
    effective_phase_frames = anchor_timeline_frame_b - anchor_timeline_frame_a
    effective_phase_beats = effective_phase_frames / sample_rate * (plan.target_bpm / 60.0)
    anchor_delta_beats = (anchor_time_b - anchor_time_a) * (plan.target_bpm / 60.0)
    recommended_max_overlap = min(prep_a.recommended_max_overlap_beats, prep_b.recommended_max_overlap_beats)
    estimated_phase_error = max(
        metadata_a.beat_analysis.estimated_phase_error_beats,
        metadata_b.beat_analysis.estimated_phase_error_beats,
        abs(plan.phase_offset_beats - effective_phase_beats),
    )
    drift_risk = max(metadata_a.beat_analysis.phase_drift_risk, metadata_b.beat_analysis.phase_drift_risk)
    long_overlap_safe = (
        prep_a.suitable_for_long_transition
        and prep_b.suitable_for_long_transition
        and plan.overlap_duration_beats <= recommended_max_overlap
    )
    notes = _merge_unique_notes(prep_a.notes, prep_b.notes, metadata_a.beat_analysis.sync_warnings, metadata_b.beat_analysis.sync_warnings)
    if plan.overlap_duration_beats > recommended_max_overlap:
        notes.append(
            f"Overlap {int(plan.overlap_duration_beats)} exceeds recommended max {recommended_max_overlap} beats for current prep/provider stability."
        )
    if metadata_a.beat_analysis.ambiguous_bar_phase or metadata_b.beat_analysis.ambiguous_bar_phase:
        notes.append("Track A or B has ambiguous bar phase; long overlap may drift.")
    if min(metadata_a.beat_analysis.sub_beat_confidence, metadata_b.beat_analysis.sub_beat_confidence) < 0.55:
        notes.append("Low sub-beat confidence; phase offset kept conservative.")
    if prep_a.prototype_only or prep_b.prototype_only:
        notes.append("At least one preparation path is prototype/offline oriented.")
    alignment = SyncAlignmentResult(
        anchor_bar_a=plan.track_a_exit_bar,
        anchor_bar_b=plan.track_b_entry_bar,
        anchor_time_a=anchor_frame_a / sample_rate,
        anchor_time_b=anchor_frame_b / sample_rate,
        timeline_anchor_time_a=anchor_timeline_frame_a / sample_rate,
        timeline_anchor_time_b=anchor_timeline_frame_b / sample_rate,
        requested_phase_offset_beats=plan.phase_offset_beats,
        effective_phase_offset_beats=effective_phase_beats,
        anchor_delta_beats=anchor_delta_beats,
        estimated_phase_error_beats=estimated_phase_error,
        drift_risk=drift_risk,
        long_overlap_safe=long_overlap_safe,
        recommended_max_overlap_beats=recommended_max_overlap,
        notes=notes,
        applied_phase_offset_beats=effective_phase_beats,
        estimated_drift_risk=drift_risk,
        long_blend_safe=long_overlap_safe,
    )
    return alignment, {
        "anchor_frame_a": anchor_frame_a,
        "anchor_frame_b": anchor_frame_b,
        "anchor_timeline_frame_a": anchor_timeline_frame_a,
        "anchor_timeline_frame_b": anchor_timeline_frame_b,
        "phase_offset_frames": effective_phase_frames,
    }
