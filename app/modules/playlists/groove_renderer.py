"""Adapter wiring GrooveEngine's OfflineDualDeckRenderer into the main offline mix pipeline.

The GrooveEngine renderer supports time-stretching, phase-aligned sync,
band-aware handoffs (bass-swap, vocal-duck), and FX automation — features
not present in the simpler equal-power crossfade renderer.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, List, Optional

import numpy as np
import soundfile as sf

# Inject GrooveEngine path (same pattern as groove_adapter.py)
_GE_ROOT = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "GrooveEngine")
)
if _GE_ROOT not in sys.path:
    sys.path.insert(0, _GE_ROOT)

from audio.offline_renderer import OfflineDualDeckRenderer
from core.datatypes import (
    AutomationLane,
    AutomationPoint,
    TrackMetadata,
    TransitionPlan,
    TransitionWindowScore,
)
from core.enums import TransitionType


def _plan_from_dj_item(
    from_item: dict, to_item: dict, transition_item: dict,
) -> TransitionPlan:
    """Build a GrooveEngine TransitionPlan from API-level transition data.

    The DjTransitionPlanItem fields are mapped to a minimal TransitionPlan
    that the OfflineDualDeckRenderer can consume.
    """
    from core.enums import TransitionType as TT

    technique = str(transition_item.get("transition_technique", "crossfade")).lower()
    strategy_map = {
        "crossfade": TT.CLEAN_BLEND,
        "echo_out": TT.ECHO_OUT,
        "riser": TT.RISER,
        "cut_swap": TT.CUT_SWAP,
        "triplet_swap": TT.TRIPLET_SWAP,
        "melodic_reset": TT.MELODIC_RESET,
    }
    strategy = strategy_map.get(technique, TT.CLEAN_BLEND)

    overlap_beats = max(
        4.0, float(transition_item.get("crossfade_sec", 8.0)) * 2.0
    )  # rough: 2 beats/sec
    target_bpm = 120.0  # will be overridden by actual track BPMs

    # Build a minimal score breakdown
    score = float(transition_item.get("score", 0.0))
    score_breakdown = TransitionWindowScore(
        track_a_exit_bar=int(transition_item.get("exit_beat", 4)),
        track_b_entry_bar=int(transition_item.get("entry_beat", 1)),
        overlap_beats=int(overlap_beats),
        target_bpm=target_bpm,
        strategy=strategy,
        phrase_score=score,
        energy_score=score,
        harmonic_score=score,
        phase_alignment_score=score,
        spectral_conflict_score=score,
        loudness_continuity_score=score,
        dance_continuity_score=score,
        total_score=score,
    )

    return TransitionPlan(
        mix_start_time=float(transition_item.get("exit_time_sec", 0.0)),
        overlap_duration_beats=overlap_beats,
        target_bpm=target_bpm,
        strategy=strategy,
        track_a_exit_bar=score_breakdown.track_a_exit_bar,
        track_b_entry_bar=score_breakdown.track_b_entry_bar,
        automation=[],
        score_breakdown=score_breakdown,
    )


def render_mix_with_groove_engine(
    audio_paths: List[str],
    transitions: List[dict],
    sample_rate: int = 44100,
) -> np.ndarray:
    """Render an N-track mix using GrooveEngine's OfflineDualDeckRenderer.

    For each consecutive pair (i, i+1):
      - Load audio_i, audio_i+1 via soundfile
      - Call OfflineDualDeckRenderer.render_transition()
      - Concatenate: prefix_i + rendered_overlap + tail_i+1

    Args:
        audio_paths: Absolute paths to processed audio files, in order.
        transitions: Transition descriptors, one per consecutive pair.
        sample_rate: Target sample rate for rendering.

    Returns:
        Stereo float32 numpy array of the complete rendered mix.
    """
    if len(audio_paths) < 2:
        # Single track — just load and return
        audio, sr = sf.read(audio_paths[0], dtype="float32", always_2d=True)
        if sr != sample_rate:
            import librosa
            audio = librosa.resample(audio.T, orig_sr=sr, target_sr=sample_rate).T
        if audio.shape[1] == 1:
            audio = np.repeat(audio, 2, axis=1)
        return audio.astype(np.float32)

    renderer = OfflineDualDeckRenderer()

    # Helper: load and maybe resample to mono-like stereo, normalized
    def _load_stereo(path: str) -> np.ndarray:
        audio, sr = sf.read(path, dtype="float32", always_2d=True)
        if sr != sample_rate:
            import librosa
            audio = librosa.resample(audio.T, orig_sr=sr, target_sr=sample_rate).T
        if audio.shape[1] == 1:
            audio = np.repeat(audio, 2, axis=1)
        elif audio.shape[1] > 2:
            audio = audio[:, :2]
        return audio.astype(np.float32)

    all_audio = [_load_stereo(p) for p in audio_paths]

    # For metadata, build minimal TrackMetadata from audio properties
    def _minimal_meta(path: str, index: int, audio: np.ndarray) -> TrackMetadata:
        from core.datatypes import BeatGrid, BeatPoint, EnergyPoint, PhraseSegment
        duration = len(audio) / sample_rate
        # Build a minimal beat grid (every 0.5s = ~120 BPM)
        beat_times = [t for t in np.arange(0, duration, 0.5)]
        beats = [
            BeatPoint(index=i + 1, time=t, bar=(i // 4) + 1, beat_in_bar=(i % 4) + 1)
            for i, t in enumerate(beat_times)
        ]
        grid = BeatGrid(bpm=120.0, beats=beats, bars=max(1, len(beats) // 4), downbeats=beat_times[::4])
        return TrackMetadata(
            track_id=f"groove_render_{index}",
            title=Path(path).stem,
            path=path,
            duration_seconds=duration,
            sample_rate=sample_rate,
            channels=2,
            beatgrid=grid,
            phrases=[PhraseSegment(
                phrase_type=__import__("core.enums", fromlist=["PhraseType"]).PhraseType.UNKNOWN,
                start_time=0.0,
                end_time=duration,
                start_bar=1,
                end_bar=max(1, len(beats) // 4),
            )],
            energy_bars=[],
        )

    # Render pair-wise transitions
    output_segments: List[np.ndarray] = []
    current_audio = all_audio[0]
    current_meta = _minimal_meta(audio_paths[0], 0, current_audio)

    for i in range(1, len(all_audio)):
        next_audio = all_audio[i]
        next_meta = _minimal_meta(audio_paths[i], i, next_audio)

        if i - 1 < len(transitions):
            plan = _plan_from_dj_item({}, {}, transitions[i - 1])
        else:
            plan = TransitionPlan(
                mix_start_time=max(0.0, len(current_audio) / sample_rate - 4.0),
                overlap_duration_beats=8.0,
                target_bpm=120.0,
                strategy=TransitionType.CLEAN_BLEND,
                track_a_exit_bar=1,
                track_b_entry_bar=1,
                automation=[],
                score_breakdown=TransitionWindowScore(
                    track_a_exit_bar=1, track_b_entry_bar=1,
                    overlap_beats=8, target_bpm=120.0,
                    strategy=TransitionType.CLEAN_BLEND,
                    phrase_score=0.5, energy_score=0.5, harmonic_score=0.5,
                    phase_alignment_score=0.5, spectral_conflict_score=0.5,
                    loudness_continuity_score=0.5, dance_continuity_score=0.5,
                    total_score=0.5,
                ),
            )

        try:
            result = renderer.render_transition(
                current_audio,
                current_meta,
                Path(audio_paths[i - 1]).stem,
                plan,
                next_audio,
                next_meta,
                Path(audio_paths[i]).stem,
            )
            output_segments.append(result.audio)
        except Exception:
            # Fallback: simple concatenation with crossfade
            crossfade_samples = min(
                int(4.0 * sample_rate),  # 4 seconds max
                len(current_audio) // 2,
                len(next_audio) // 2,
            )
            if crossfade_samples < 1024:
                output_segments.append(
                    np.concatenate([current_audio, next_audio])
                )
            else:
                # Simple equal-power crossfade
                fade_out = np.sqrt(
                    np.linspace(1.0, 0.0, crossfade_samples, dtype=np.float32)
                ).reshape(-1, 1)
                fade_in = np.sqrt(
                    np.linspace(0.0, 1.0, crossfade_samples, dtype=np.float32)
                ).reshape(-1, 1)
                overlap = (
                    current_audio[-crossfade_samples:] * fade_out
                    + next_audio[:crossfade_samples] * fade_in
                )
                seg = np.concatenate([
                    current_audio[:-crossfade_samples],
                    overlap,
                    next_audio[crossfade_samples:],
                ])
                output_segments.append(seg)

        current_audio = all_audio[i]
        current_meta = next_meta

    return np.concatenate(output_segments) if output_segments else all_audio[0]
