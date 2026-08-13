"""Reference renderer for the default automatic DJ path.

The offline default-mix bundle renders a short transition with independent
low/mid/high curves, then playback resumes inside the next song.  This module
keeps that behaviour behind the ``default_mix`` branch so manual cuts can keep
using the existing section_match + eq_band_mix path.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np


NAS_DEFAULT_ROOT = Path("/mnt/nas/harbeat/dj-control/default-mix/pair-cache")
LOCAL_DEFAULT_ROOT = Path("data/default-mix/pair-cache")
RENDERER_VERSION = "three_band_default_v9_fast_phase_window"
FAST_CUT_RENDERER_VERSION = "three_band_default_v7_standalone_curve_no_energy_floor"


class DefaultRenderError(RuntimeError):
    """Raised when a default render cannot be generated."""


def pair_cache_root() -> Path:
    configured = os.environ.get("HARBEAT_DEFAULT_MIX_PAIR_CACHE_DIR", "").strip()
    if configured:
        return Path(configured)
    if NAS_DEFAULT_ROOT.parent.exists():
        return NAS_DEFAULT_ROOT
    return LOCAL_DEFAULT_ROOT


def pair_dir(pair_id: str) -> Path:
    safe = "".join(ch for ch in pair_id if ch.isalnum() or ch in ("-", "_"))
    if not safe:
        raise DefaultRenderError("empty default_mix pair_id")
    return pair_cache_root() / safe


def ensure_reference_render(prev_song: Any, next_song: Any, plan: dict[str, Any]) -> dict[str, Any]:
    """Render and cache the default transition for ``plan``.

    Returns a metadata dict containing local paths.  The caller is responsible
    for exposing these paths as URLs.
    """
    default_meta = plan.get("default_mix")
    if not isinstance(default_meta, dict):
        default_meta = plan
    renderer_version = _renderer_version_for(default_meta, plan)
    pair_id = str(plan.get("pair_id") or default_meta.get("pair_id") or "").strip()
    if not pair_id:
        raise DefaultRenderError("transition plan missing pair_id")

    out_dir = pair_dir(pair_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / "transition_render.wav"
    json_path = out_dir / "transition_render.json"

    prev_mtime = _mtime(getattr(prev_song, "source_path", ""))
    next_mtime = _mtime(getattr(next_song, "source_path", ""))
    current_meta = _read_json(json_path)
    if (
        wav_path.is_file()
        and wav_path.stat().st_size > 0
        and current_meta.get("pair_id") == pair_id
        and current_meta.get("render_strategy") == "three_band_default"
        and current_meta.get("renderer_version") == renderer_version
        and current_meta.get("prev_source_mtime") == prev_mtime
        and current_meta.get("next_source_mtime") == next_mtime
    ):
        return {
            **current_meta,
            "transition_render_path": str(wav_path),
            "transition_render_meta_path": str(json_path),
            "cached": True,
        }

    prev_path = getattr(prev_song, "source_path", "") or ""
    next_path = getattr(next_song, "source_path", "") or ""
    if not prev_path or not Path(prev_path).is_file():
        raise DefaultRenderError(f"previous song audio missing: {prev_path}")
    if not next_path or not Path(next_path).is_file():
        raise DefaultRenderError(f"next song audio missing: {next_path}")

    try:
        import librosa
        import soundfile as sf
        from scipy import signal
    except Exception as exc:  # pragma: no cover - environment dependent
        raise DefaultRenderError(f"default render dependencies unavailable: {exc}") from exc

    if renderer_version == FAST_CUT_RENDERER_VERSION:
        return _ensure_fast_cut_v7_render(
            prev_song,
            next_song,
            plan=plan,
            default_meta=default_meta,
            pair_id=pair_id,
            wav_path=wav_path,
            json_path=json_path,
            prev_mtime=prev_mtime,
            next_mtime=next_mtime,
            librosa_mod=librosa,
            soundfile_mod=sf,
            signal_mod=signal,
        )

    render_started = time.perf_counter()
    sr = 44100
    requested_from_at = float(default_meta.get("from_at_sec") or plan.get("from_at_sec") or 0.0)
    requested_to_at = float(default_meta.get("to_at_sec") or plan.get("to_at_sec") or 0.0)
    fade_sec = float(default_meta.get("duration_sec") or plan.get("duration_sec") or 6.5)
    fade_sec = max(3.0, min(12.0, fade_sec))
    samples = max(1, int(round(fade_sec * sr)))
    tempo_sync = _tempo_sync_plan(prev_song, next_song)
    next_source_sec = fade_sec * (float(tempo_sync.get("rate") or 1.0) if tempo_sync.get("enabled") else 1.0)
    prev_audio, prev_origin, prev_load = _load_mono_window(
        prev_path,
        start_sec=max(0.0, requested_from_at - 0.75),
        end_sec=requested_from_at + fade_sec + 1.0,
        target_sr=sr,
        soundfile_mod=sf,
        librosa_mod=librosa,
    )
    next_audio, next_origin, next_load = _load_mono_window(
        next_path,
        start_sec=max(0.0, requested_to_at - 0.75),
        end_sec=requested_to_at + next_source_sec + 3.6,
        target_sr=sr,
        soundfile_mod=sf,
        librosa_mod=librosa,
    )

    window_loaded_at = time.perf_counter()
    from_at, to_at, phase_alignment = _align_transition_points(
        prev_audio,
        next_audio,
        sr,
        requested_from_at,
        requested_to_at,
        prev_song=prev_song,
        next_song=next_song,
        librosa_mod=librosa,
        prev_origin_sec=prev_origin,
        next_origin_sec=next_origin,
    )

    phase_aligned_at = time.perf_counter()
    prev_start = max(0, int(round((from_at - prev_origin) * sr)))
    next_start = max(0, int(round((to_at - next_origin) * sr)))
    region_a = _slice_with_pad(prev_audio, prev_start, samples)
    next_source_samples = samples
    if tempo_sync["enabled"]:
        next_source_samples = max(1, int(round(samples * float(tempo_sync["rate"]))))
    region_b_source = _slice_with_pad(next_audio, next_start, next_source_samples)
    region_b, tempo_sync = _apply_overlap_tempo_sync(
        region_b_source,
        sr,
        target_samples=samples,
        tempo_sync=tempo_sync,
        librosa_mod=librosa,
    )

    tempo_synced_at = time.perf_counter()
    # Match the local transition energy without a fade-back envelope.  The old
    # envelope made the transition feel like it dipped and swelled; this keeps
    # the overlap steady, closer to the standalone adaptive module.
    region_b, gain_db, gain_envelope = _match_head_energy(region_a, region_b, sr)

    low_a, mid_a, high_a = _separate_bands(region_a, sr, signal)
    low_b, mid_b, high_b = _separate_bands(region_b, sr, signal)
    curves = _curves(samples, _bpm(prev_song), _bpm(next_song))
    mixed = (
        low_a * curves["a_low"]
        + mid_a * curves["a_mid"]
        + high_a * curves["a_high"]
        + low_b * curves["b_low"]
        + mid_b * curves["b_mid"]
        + high_b * curves["b_high"]
    )
    bands_mixed_at = time.perf_counter()
    # Keep the production render closer to the standalone module: after
    # three-band summing, do not apply an additional whole-transition energy
    # floor/envelope. The previous smoothing used zero-padded convolution at
    # the edges, which could make the transition feel like it briefly faded out.
    energy_floor = {"enabled": 0.0, "mode": "disabled_for_standalone_curve_parity"}
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    if peak > 0.98:
        mixed = mixed * (0.98 / peak)
    base_resume_at = to_at + next_source_samples / sr
    resume_at, resume_search = _find_resume_at(
        mixed,
        next_audio,
        sr,
        base_resume_at=base_resume_at,
        next_song=next_song,
        search_sec=2.5,
        audio_origin_sec=next_origin,
    )
    mixed, tail_energy_match = _match_resume_tail_energy(mixed, resume_search)
    resume_search = {**resume_search, "tail_energy_match": tail_energy_match}
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    if peak > 0.98:
        mixed = mixed * (0.98 / peak)

    tmp_wav = wav_path.with_name(f"{wav_path.stem}.tmp{wav_path.suffix}")
    sf.write(tmp_wav, mixed.astype(np.float32), sr)
    os.replace(tmp_wav, wav_path)
    written_at = time.perf_counter()

    meta = {
        "source": "default_mix_reference_renderer_v1",
        "mode": default_meta.get("mode") or "default_mix",
        "playback_mode": default_meta.get("playback_mode") or plan.get("playback_mode") or "default_mix",
        "planner_version": default_meta.get("planner_version"),
        "audio_feature_source": default_meta.get("audio_feature_source"),
        "required_renderer_version": default_meta.get("required_renderer_version"),
        "pair_id": pair_id,
        "from_song_id": str(getattr(prev_song, "id", "")),
        "to_song_id": str(getattr(next_song, "id", "")),
        "requested_exit_time_sec": default_meta.get("requested_exit_time_sec"),
        "from_at_sec": round(from_at, 3),
        "to_at_sec": round(to_at, 3),
        "requested_from_at_sec": round(requested_from_at, 3),
        "requested_to_at_sec": round(requested_to_at, 3),
        "duration_sec": round(samples / sr, 3),
        "track2_source_duration_sec": round(next_source_samples / sr, 3),
        "resume_at_sec": round(resume_at, 3),
        "base_resume_at_sec": round(base_resume_at, 3),
        "render_strategy": "three_band_default",
        "renderer_version": RENDERER_VERSION,
        "transition_render_path": str(wav_path),
        "transition_render_meta_path": str(json_path),
        "exit_selection_reason": default_meta.get("exit_selection_reason"),
        "entry_selection_reason": default_meta.get("entry_selection_reason"),
        "phrase_anchor_used": bool(default_meta.get("phrase_anchor_used", False)),
        "beat_alignment_shift_ms": default_meta.get("beat_alignment_shift_ms"),
        "vocal_penalty_score": default_meta.get("vocal_penalty_score"),
        "cut_point_policy": default_meta.get("cut_point_policy") or {},
        "exit_candidate": default_meta.get("exit_candidate") or {},
        "entry_candidate": default_meta.get("entry_candidate") or {},
        "alignment": default_meta.get("alignment") or {},
        "render_phase_alignment": phase_alignment,
        "overlap_tempo_sync": tempo_sync,
        "fast_cut": default_meta.get("fast_cut") or plan.get("fast_cut") or {},
        "energy_match_gain_db": round(float(gain_db), 3),
        "energy_match_gain_envelope": gain_envelope,
        "transition_energy_floor": energy_floor,
        "resume_continuity_search": resume_search,
        "audio_window_loading": {
            "mode": "random_access_local_window_v1",
            "track1": prev_load,
            "track2": next_load,
        },
        "render_timing_ms": {
            "window_load": round((window_loaded_at - render_started) * 1000.0, 1),
            "phase_alignment": round((phase_aligned_at - window_loaded_at) * 1000.0, 1),
            "tempo_sync": round((tempo_synced_at - phase_aligned_at) * 1000.0, 1),
            "band_mix_and_resume": round((written_at - tempo_synced_at) * 1000.0, 1),
            "total": round((written_at - render_started) * 1000.0, 1),
        },
        "prev_source_mtime": prev_mtime,
        "next_source_mtime": next_mtime,
    }
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**meta, "cached": False}


def _renderer_version_for(default_meta: dict[str, Any], plan: dict[str, Any]) -> str:
    requested = (
        default_meta.get("required_renderer_version")
        or default_meta.get("renderer_version")
        or plan.get("required_renderer_version")
        or plan.get("renderer_version")
    )
    if requested == FAST_CUT_RENDERER_VERSION:
        return FAST_CUT_RENDERER_VERSION
    return RENDERER_VERSION


def _ensure_fast_cut_v7_render(
    prev_song: Any,
    next_song: Any,
    *,
    plan: dict[str, Any],
    default_meta: dict[str, Any],
    pair_id: str,
    wav_path: Path,
    json_path: Path,
    prev_mtime: float | None,
    next_mtime: float | None,
    librosa_mod: Any,
    soundfile_mod: Any,
    signal_mod: Any,
) -> dict[str, Any]:
    """Render the July 23 verified fast-cut three-band path.

    This path intentionally does not use the later v9 drum-anchor refinement
    or overlap time-stretch.  It preserves the precomputed candidate times,
    mixes the same three bands, and searches only the Track2 resume point for
    continuity.
    """
    render_started = time.perf_counter()
    sr = 44100
    prev_path = str(getattr(prev_song, "source_path", "") or "")
    next_path = str(getattr(next_song, "source_path", "") or "")
    from_at = float(default_meta.get("from_at_sec") or plan.get("from_at_sec") or 0.0)
    to_at = float(default_meta.get("to_at_sec") or plan.get("to_at_sec") or 0.0)
    fade_sec = float(default_meta.get("duration_sec") or plan.get("duration_sec") or 6.5)
    fade_sec = max(3.0, min(12.0, fade_sec))
    samples = max(1, int(round(fade_sec * sr)))
    resume_search_sec = 2.5
    prev_audio, prev_origin, prev_load = _load_mono_window(
        prev_path,
        start_sec=max(0.0, from_at - 0.25),
        end_sec=from_at + fade_sec + 0.5,
        target_sr=sr,
        soundfile_mod=soundfile_mod,
        librosa_mod=librosa_mod,
    )
    next_audio, next_origin, next_load = _load_mono_window(
        next_path,
        start_sec=max(0.0, to_at - 0.25),
        end_sec=to_at + fade_sec + resume_search_sec + 0.8,
        target_sr=sr,
        soundfile_mod=soundfile_mod,
        librosa_mod=librosa_mod,
    )
    loaded_at = time.perf_counter()

    prev_start = max(0, int(round((from_at - prev_origin) * sr)))
    next_start = max(0, int(round((to_at - next_origin) * sr)))
    region_a = _slice_with_pad(prev_audio, prev_start, samples)
    region_b = _slice_with_pad(next_audio, next_start, samples)
    region_b, gain_db, gain_envelope = _match_head_energy(region_a, region_b, sr)

    low_a, mid_a, high_a = _separate_bands(region_a, sr, signal_mod)
    low_b, mid_b, high_b = _separate_bands(region_b, sr, signal_mod)
    curves = _curves(samples, _bpm(prev_song), _bpm(next_song))
    mixed = (
        low_a * curves["a_low"]
        + mid_a * curves["a_mid"]
        + high_a * curves["a_high"]
        + low_b * curves["b_low"]
        + mid_b * curves["b_mid"]
        + high_b * curves["b_high"]
    )
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    if peak > 0.98:
        mixed = mixed * (0.98 / peak)

    base_resume_at = to_at + samples / sr
    resume_at, resume_search = _find_resume_at(
        mixed,
        next_audio,
        sr,
        base_resume_at=base_resume_at,
        next_song=next_song,
        search_sec=resume_search_sec,
        audio_origin_sec=next_origin,
    )
    resume_search = {
        **resume_search,
        "tail_energy_match": {
            "applied": 0.0,
            "mode": "disabled_for_standalone_curve_parity",
        },
    }
    mixed_at = time.perf_counter()

    tmp_wav = wav_path.with_name(f"{wav_path.stem}.tmp{wav_path.suffix}")
    soundfile_mod.write(tmp_wav, mixed.astype(np.float32), sr)
    os.replace(tmp_wav, wav_path)
    written_at = time.perf_counter()

    meta = {
        "source": "default_mix_reference_renderer_v1",
        "mode": default_meta.get("mode") or "default_mix",
        "playback_mode": default_meta.get("playback_mode") or plan.get("playback_mode") or "fast_cut",
        "planner_version": default_meta.get("planner_version"),
        "audio_feature_source": default_meta.get("audio_feature_source"),
        "required_renderer_version": FAST_CUT_RENDERER_VERSION,
        "pair_id": pair_id,
        "from_song_id": str(getattr(prev_song, "id", "")),
        "to_song_id": str(getattr(next_song, "id", "")),
        "requested_exit_time_sec": default_meta.get("requested_exit_time_sec"),
        "from_at_sec": round(from_at, 3),
        "to_at_sec": round(to_at, 3),
        "requested_from_at_sec": round(from_at, 3),
        "requested_to_at_sec": round(to_at, 3),
        "duration_sec": round(samples / sr, 3),
        "track2_source_duration_sec": round(samples / sr, 3),
        "resume_at_sec": round(resume_at, 3),
        "base_resume_at_sec": round(base_resume_at, 3),
        "render_strategy": "three_band_default",
        "renderer_version": FAST_CUT_RENDERER_VERSION,
        "transition_render_path": str(wav_path),
        "transition_render_meta_path": str(json_path),
        "exit_selection_reason": default_meta.get("exit_selection_reason"),
        "entry_selection_reason": default_meta.get("entry_selection_reason"),
        "phrase_anchor_used": bool(default_meta.get("phrase_anchor_used", False)),
        "beat_alignment_shift_ms": default_meta.get("beat_alignment_shift_ms"),
        "vocal_penalty_score": default_meta.get("vocal_penalty_score"),
        "cut_point_policy": default_meta.get("cut_point_policy") or {},
        "exit_candidate": default_meta.get("exit_candidate") or {},
        "entry_candidate": default_meta.get("entry_candidate") or {},
        "alignment": default_meta.get("alignment") or {},
        "render_phase_alignment": {"enabled": 0.0, "mode": "v7_precomputed_candidate_times"},
        "overlap_tempo_sync": {"enabled": 0.0, "mode": "disabled_for_v7_parity"},
        "fast_cut": default_meta.get("fast_cut") or plan.get("fast_cut") or {},
        "energy_match_gain_db": round(float(gain_db), 3),
        "energy_match_gain_envelope": gain_envelope,
        "transition_energy_floor": {
            "enabled": 0.0,
            "mode": "disabled_for_standalone_curve_parity",
        },
        "resume_continuity_search": resume_search,
        "audio_window_loading": {
            "mode": "random_access_local_window_v7",
            "track1": prev_load,
            "track2": next_load,
        },
        "render_timing_ms": {
            "audio_load": round((loaded_at - render_started) * 1000.0, 1),
            "band_mix_and_resume": round((mixed_at - loaded_at) * 1000.0, 1),
            "total": round((written_at - render_started) * 1000.0, 1),
        },
        "prev_source_mtime": prev_mtime,
        "next_source_mtime": next_mtime,
    }
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**meta, "cached": False}


def _align_transition_points(
    prev_audio: np.ndarray,
    next_audio: np.ndarray,
    sr: int,
    from_at: float,
    to_at: float,
    *,
    prev_song: Any,
    next_song: Any,
    librosa_mod: Any,
    prev_origin_sec: float = 0.0,
    next_origin_sec: float = 0.0,
) -> tuple[float, float, dict[str, Any]]:
    local_from_at = max(0.0, from_at - prev_origin_sec)
    local_to_at = max(0.0, to_at - next_origin_sec)
    from_refined, from_offset = _refine_to_drum_anchor(
        prev_audio,
        sr,
        local_from_at,
        _bpm(prev_song),
        librosa_mod,
        before_sec=0.08,
        after_sec=0.10,
    )
    to_seed = _nearest_grid_time(
        to_at,
        getattr(next_song, "downbeats", None),
        max_delta=0.18,
    )
    if to_seed is None:
        to_seed = _nearest_grid_time(
            to_at,
            getattr(next_song, "beat_points", None),
            max_delta=0.12,
        )
    if to_seed is None:
        to_seed = to_at
    local_to_seed = max(0.0, float(to_seed) - next_origin_sec)
    to_refined, to_anchor_offset = _refine_to_drum_anchor(
        next_audio,
        sr,
        local_to_seed,
        _bpm(next_song),
        librosa_mod,
        before_sec=0.08,
        after_sec=0.12,
    )
    to_final, phrase_offset, phrase_score = _refine_cross_track_drum_alignment(
        prev_audio,
        next_audio,
        sr,
        from_refined,
        to_refined,
        _bpm(prev_song),
        librosa_mod,
    )
    absolute_from = from_refined + prev_origin_sec
    absolute_to = to_final + next_origin_sec
    return absolute_from, absolute_to, {
        "enabled": 1.0,
        "mode": "local_drum_phase_precomputed_grid_v1",
        "requested_from_at_sec": round(float(from_at), 3),
        "aligned_from_at_sec": round(float(absolute_from), 3),
        "from_anchor_offset_ms": round(float(from_offset * 1000.0), 1),
        "requested_to_at_sec": round(float(to_at), 3),
        "grid_seed_to_at_sec": round(float(to_seed), 3),
        "drum_refined_to_at_sec": round(float(to_refined + next_origin_sec), 3),
        "aligned_to_at_sec": round(float(absolute_to), 3),
        "to_anchor_offset_ms": round(float(to_anchor_offset * 1000.0), 1),
        "cross_track_offset_ms": round(float(phrase_offset * 1000.0), 1),
        "cross_track_score": round(float(phrase_score), 4),
    }


def _tempo_sync_plan(prev_song: Any, next_song: Any) -> dict[str, Any]:
    prev_bpm = _bpm(prev_song)
    next_bpm = _bpm(next_song)
    if prev_bpm <= 1e-6 or next_bpm <= 1e-6:
        return {
            "enabled": 0.0,
            "reason": "missing_bpm",
            "prev_bpm": round(float(prev_bpm), 3),
            "next_bpm": round(float(next_bpm), 3),
        }
    rate = float(prev_bpm / next_bpm)
    delta = abs(rate - 1.0)
    if delta < 0.015:
        return {
            "enabled": 0.0,
            "reason": "tempo_delta_below_threshold",
            "rate": round(rate, 6),
            "prev_bpm": round(float(prev_bpm), 3),
            "next_bpm": round(float(next_bpm), 3),
        }
    if delta > 0.06:
        return {
            "enabled": 0.0,
            "reason": "tempo_delta_above_overlap_stretch_limit",
            "rate": round(rate, 6),
            "prev_bpm": round(float(prev_bpm), 3),
            "next_bpm": round(float(next_bpm), 3),
        }
    return {
        "enabled": 1.0,
        "mode": "track2_overlap_only_time_stretch",
        "rate": round(rate, 6),
        "prev_bpm": round(float(prev_bpm), 3),
        "next_bpm": round(float(next_bpm), 3),
    }


def _apply_overlap_tempo_sync(
    audio: np.ndarray,
    sr: int,
    *,
    target_samples: int,
    tempo_sync: dict[str, Any],
    librosa_mod: Any,
) -> tuple[np.ndarray, dict[str, Any]]:
    if not tempo_sync.get("enabled"):
        return _fit_samples(audio, target_samples), {**tempo_sync, "target_samples": target_samples}
    rate = float(tempo_sync.get("rate") or 1.0)
    try:
        stretched = librosa_mod.effects.time_stretch(np.asarray(audio, dtype=np.float32), rate=rate)
        out = _fit_samples(stretched, target_samples)
        return out, {
            **tempo_sync,
            "applied": 1.0,
            "source_samples": int(len(audio)),
            "target_samples": int(target_samples),
        }
    except Exception as exc:
        return _fit_samples(audio, target_samples), {
            **tempo_sync,
            "enabled": 0.0,
            "applied": 0.0,
            "reason": f"time_stretch_failed:{exc}",
            "source_samples": int(len(audio)),
            "target_samples": int(target_samples),
        }


def _fit_samples(audio: np.ndarray, samples: int) -> np.ndarray:
    data = np.asarray(audio, dtype=np.float32)
    if len(data) >= samples:
        return data[:samples]
    return np.pad(data, (0, samples - len(data)))


def _nearest_grid_time(target: float, values: Any, *, max_delta: float) -> float | None:
    if not isinstance(values, list) or not values:
        return None
    best: float | None = None
    best_delta = float(max_delta)
    for value in values:
        try:
            t = float(value)
        except (TypeError, ValueError):
            continue
        delta = abs(t - target)
        if delta <= best_delta:
            best = t
            best_delta = delta
    return best


def _refine_to_drum_anchor(
    audio: np.ndarray,
    sr: int,
    reference_time: float,
    tempo: float,
    librosa_mod: Any,
    *,
    before_sec: float,
    after_sec: float,
) -> tuple[float, float]:
    if len(audio) == 0:
        return reference_time, 0.0
    beat_duration = 60.0 / max(float(tempo), 1e-6)
    search_before = min(before_sec, beat_duration * 0.2)
    search_after = min(after_sec, beat_duration * 0.24)
    start_time = max(0.0, float(reference_time) - search_before)
    end_time = min(len(audio) / float(sr), float(reference_time) + search_after)
    start_sample = int(round(start_time * sr))
    end_sample = int(round(end_time * sr))
    segment = audio[start_sample:end_sample]
    if len(segment) < 1024:
        return reference_time, 0.0
    try:
        percussive = librosa_mod.effects.percussive(segment)
        onset_env = librosa_mod.onset.onset_strength(y=percussive, sr=sr)
        onset_frames = librosa_mod.onset.onset_detect(
            onset_envelope=onset_env,
            sr=sr,
            units="frames",
            backtrack=False,
        )
    except Exception:
        return reference_time, 0.0
    if len(onset_frames) == 0:
        return reference_time, 0.0
    onset_times = librosa_mod.frames_to_time(onset_frames, sr=sr) + start_time
    onset_strengths = onset_env[onset_frames]
    best_score = -1e9
    refined_time = float(reference_time)
    for onset_time, onset_strength in zip(onset_times, onset_strengths):
        delta = float(onset_time - reference_time)
        proximity_penalty = abs(delta) / max(search_after, search_before, 1e-6)
        forward_penalty = max(0.0, delta - 0.03) / max(search_after, 1e-6)
        score = float(onset_strength) - 1.6 * proximity_penalty - 0.8 * forward_penalty
        if score > best_score:
            best_score = score
            refined_time = float(onset_time)
    return refined_time, refined_time - float(reference_time)


def _refine_cross_track_drum_alignment(
    prev_audio: np.ndarray,
    next_audio: np.ndarray,
    sr: int,
    from_at: float,
    to_at: float,
    tempo: float,
    librosa_mod: Any,
) -> tuple[float, float, float]:
    beat_duration = 60.0 / max(float(tempo), 1e-6)
    phrase_window_sec = min(max(beat_duration * 4.0, 1.8), 3.5)
    before_sec = min(0.12, beat_duration * 0.25)
    after_sec = 0.18
    ref_start = max(0.0, from_at - before_sec)
    env_a = _onset_env_window(prev_audio, sr, ref_start, phrase_window_sec, librosa_mod)
    if env_a.size == 0:
        return to_at, 0.0, 0.0

    # Extract the percussive/onset envelope once for the whole candidate range.
    # The old implementation ran HPSS + onset detection for every offset (16
    # times), which made a manual cut spend most of its live window in analysis.
    next_ref_start = max(0.0, to_at - before_sec)
    env_b = _onset_env_window(
        next_audio,
        sr,
        next_ref_start,
        phrase_window_sec + before_sec + after_sec,
        librosa_mod,
    )
    if env_b.size == 0:
        return to_at, 0.0, 0.0
    hop_length = 512
    best_score = -1.0
    best_offset = 0.0
    for offset in np.linspace(-before_sec, after_sec, 16):
        # Both envelopes use librosa's default hop. Slicing the single broad
        # target envelope is equivalent to the previous repeated-window scan,
        # while avoiding repeated STFT/HPSS work.
        start_frame = max(0, int(round((before_sec + float(offset)) * sr / hop_length)))
        candidate_env = env_b[start_frame : start_frame + len(env_a)]
        min_len = min(len(env_a), len(candidate_env))
        if min_len < 4:
            continue
        a = env_a[:min_len]
        b = candidate_env[:min_len]
        denom = float(np.linalg.norm(a) * np.linalg.norm(b)) + 1e-10
        score = float(np.dot(a, b) / denom)
        distance_penalty = abs(float(offset)) / 0.18 * 0.08
        score -= distance_penalty
        if score > best_score:
            best_score = score
            best_offset = float(offset)
    return max(0.0, float(to_at) + best_offset), best_offset, max(0.0, best_score)


def _onset_env_window(
    audio: np.ndarray,
    sr: int,
    start_time: float,
    duration: float,
    librosa_mod: Any,
) -> np.ndarray:
    start_sample = max(0, int(round(start_time * sr)))
    end_sample = min(len(audio), int(round((start_time + duration) * sr)))
    segment = audio[start_sample:end_sample]
    if len(segment) < 2048:
        return np.asarray([], dtype=np.float32)
    try:
        percussive = librosa_mod.effects.percussive(segment)
        return np.asarray(librosa_mod.onset.onset_strength(y=percussive, sr=sr), dtype=np.float32)
    except Exception:
        return np.asarray([], dtype=np.float32)


def _slice_with_pad(audio: np.ndarray, start: int, samples: int) -> np.ndarray:
    segment = audio[start : start + samples]
    if len(segment) >= samples:
        return np.asarray(segment[:samples], dtype=np.float32)
    return np.pad(np.asarray(segment, dtype=np.float32), (0, samples - len(segment)))


def _separate_bands(audio: np.ndarray, sr: int, signal_mod: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    b_low, a_low = signal_mod.butter(4, 250 / (sr * 0.5), btype="low")
    low = signal_mod.filtfilt(b_low, a_low, audio)
    b_mid, a_mid = signal_mod.butter(4, [250 / (sr * 0.5), 4000 / (sr * 0.5)], btype="band")
    mid = signal_mod.filtfilt(b_mid, a_mid, audio)
    b_high, a_high = signal_mod.butter(4, 4000 / (sr * 0.5), btype="high")
    high = signal_mod.filtfilt(b_high, a_high, audio)
    return low, mid, high


def _curves(samples: int, bpm_a: float, bpm_b: float) -> dict[str, np.ndarray]:
    x = np.linspace(0.0, 1.0, samples, dtype=np.float32)
    bpm_diff = abs(bpm_a - bpm_b)
    # Standalone adaptive module behavior, but kept deterministic/lightweight:
    # low frequencies overlap longer, mids hand off around the center, highs
    # swap smoothly with equal-power style curves.  This avoids the obvious
    # global fade-down/fade-up feel of a plain crossfade.
    low_a_base = _sigmoid(x, steepness=5.5, center=0.68, reverse=False)
    low_b_base = _sigmoid(x, steepness=5.5, center=0.32, reverse=True)
    low_a = np.maximum(low_a_base, 0.22 * (1.0 - x))
    low_b = np.maximum(low_b_base, 0.22 * x)

    width = 0.08 if bpm_diff > 30 else (0.12 if bpm_diff > 15 else 0.18)
    mid_a = _step(x, switch_point=0.54, blend_width=width, reverse=False)
    mid_b = _step(x, switch_point=0.46, blend_width=width, reverse=True)

    high_a = np.cos(x * math.pi * 0.5).astype(np.float32) * 0.92
    high_b = np.sin(x * math.pi * 0.5).astype(np.float32) * 0.92
    return {
        "a_low": low_a,
        "b_low": low_b,
        "a_mid": mid_a,
        "b_mid": mid_b,
        "a_high": high_a,
        "b_high": high_b,
    }


def _cosine(x: np.ndarray, *, reverse: bool) -> np.ndarray:
    fade = 0.5 * (1.0 - np.cos(np.pi * x))
    return fade if reverse else 1.0 - fade


def _sigmoid(x: np.ndarray, *, steepness: float, center: float, reverse: bool) -> np.ndarray:
    fade = 1.0 / (1.0 + np.exp(-steepness * (x - center)))
    return fade if reverse else 1.0 - fade


def _smootherstep(x: np.ndarray, *, reverse: bool) -> np.ndarray:
    fade = x * x * x * (x * (x * 6.0 - 15.0) + 10.0)
    return fade if reverse else 1.0 - fade


def _step(x: np.ndarray, *, switch_point: float, blend_width: float, reverse: bool) -> np.ndarray:
    steepness = 20.0 / max(0.01, blend_width)
    fade = 1.0 / (1.0 + np.exp(-steepness * (x - switch_point)))
    return fade if reverse else 1.0 - fade


def _match_head_energy(a: np.ndarray, b: np.ndarray, sr: int) -> tuple[np.ndarray, float, dict[str, float]]:
    win = max(1, int(min(2.0, max(1.0, len(a) / sr * 0.35)) * sr))
    tail = a[-win:]
    head = b[:win]
    rms_a = _rms(tail)
    rms_b = _rms(head)
    if rms_a <= 1e-8 or rms_b <= 1e-8:
        return b, 0.0, {
            "start_gain": 1.0,
            "end_gain": 1.0,
            "target_rms": round(float(rms_a), 6),
            "source_rms": round(float(rms_b), 6),
        }
    gain = float(np.clip(rms_a / rms_b, 0.85, 1.2))
    gain_db = 20.0 * math.log10(max(gain, 1e-10))
    return b * gain, gain_db, {
        "start_gain": round(float(gain), 6),
        "end_gain": round(float(gain), 6),
        "mode": "constant_no_duck",
        "target_rms": round(float(rms_a), 6),
        "source_rms": round(float(rms_b), 6),
    }


def _apply_transition_energy_floor(
    mixed: np.ndarray,
    region_a: np.ndarray,
    region_b: np.ndarray,
    sr: int,
    *,
    max_gain: float,
) -> tuple[np.ndarray, dict[str, float]]:
    if len(mixed) == 0:
        return mixed, {"enabled": 0.0}
    frame = max(1024, int(round(0.25 * sr)))
    hop = max(256, int(round(0.05 * sr)))
    n = len(mixed)
    centers: list[int] = []
    gains: list[float] = []
    max_observed = 1.0
    boosted_frames = 0
    for start in range(0, n, hop):
        end = min(n, start + frame)
        if end <= start:
            continue
        cur = _rms(mixed[start:end])
        ref_a = _rms(region_a[start:end])
        ref_b = _rms(region_b[start:end])
        # The overlap should not feel quieter than both incoming materials.
        # Use a conservative floor so the mix breathes without pumping.
        target = max(ref_a, ref_b) * 0.82
        gain = 1.0
        if cur > 1e-8 and target > cur:
            gain = float(np.clip(target / cur, 1.0, max_gain))
        if gain > 1.01:
            boosted_frames += 1
        max_observed = max(max_observed, gain)
        centers.append((start + end) // 2)
        gains.append(gain)
        if end == n:
            break
    if not centers or max_observed <= 1.01:
        return mixed, {
            "enabled": 0.0,
            "max_gain": round(float(max_observed), 6),
            "boosted_frames": float(boosted_frames),
        }
    if centers[0] != 0:
        centers.insert(0, 0)
        gains.insert(0, gains[0])
    if centers[-1] != n - 1:
        centers.append(n - 1)
        gains.append(gains[-1])
    envelope = np.interp(np.arange(n), np.asarray(centers), np.asarray(gains)).astype(np.float32)
    smooth = max(3, int(round(0.12 * sr)))
    if smooth % 2 == 0:
        smooth += 1
    kernel = np.hanning(smooth).astype(np.float32)
    kernel_sum = float(np.sum(kernel))
    if kernel_sum > 0:
        kernel = kernel / kernel_sum
        envelope = np.convolve(envelope, kernel, mode="same")
    return mixed * envelope, {
        "enabled": 1.0,
        "max_gain": round(float(max_observed), 6),
        "max_gain_db": round(float(20.0 * math.log10(max(max_observed, 1e-10))), 3),
        "boosted_frames": float(boosted_frames),
        "frame_sec": round(frame / sr, 3),
        "hop_sec": round(hop / sr, 3),
    }


def _find_resume_at(
    mixed: np.ndarray,
    next_audio: np.ndarray,
    sr: int,
    *,
    base_resume_at: float,
    next_song: Any,
    search_sec: float,
    audio_origin_sec: float = 0.0,
) -> tuple[float, dict[str, Any]]:
    if len(mixed) == 0 or len(next_audio) == 0:
        return base_resume_at, {"enabled": 0.0}
    win = max(1, int(round(0.5 * sr)))
    render_tail_rms = _rms(mixed[-win:])
    duration = audio_origin_sec + len(next_audio) / float(sr)
    lower = max(audio_origin_sec, base_resume_at - search_sec)
    upper = min(duration - 0.6, base_resume_at + search_sec)
    if upper <= lower:
        return base_resume_at, {"enabled": 0.0, "reason": "empty_search_window"}
    candidates = {round(base_resume_at, 3)}
    step = 0.05
    count = int(round((upper - lower) / step))
    for idx in range(count + 1):
        candidates.add(round(lower + idx * step, 3))
    for grid_name in ("downbeats", "beat_points"):
        values = getattr(next_song, grid_name, None) or []
        if isinstance(values, list):
            for value in values:
                try:
                    t = float(value)
                except (TypeError, ValueError):
                    continue
                if lower <= t <= upper:
                    candidates.add(round(t, 3))
    best_time = base_resume_at
    best_score = float("inf")
    best_rms = 0.0
    for candidate in sorted(candidates):
        start = int(round((float(candidate) - audio_origin_sec) * sr))
        head = next_audio[start : start + win]
        if len(head) < max(1024, win // 4):
            continue
        head_rms = _rms(head)
        rms_jump = abs(head_rms - render_tail_rms) / max(head_rms, render_tail_rms, 1e-9)
        distance_penalty = abs(float(candidate) - base_resume_at) / max(search_sec, 1e-6) * 0.08
        grid_bonus = 0.0
        if _near_grid(candidate, getattr(next_song, "downbeats", None), tolerance=0.04):
            grid_bonus = -0.02
        elif _near_grid(candidate, getattr(next_song, "beat_points", None), tolerance=0.04):
            grid_bonus = -0.01
        score = rms_jump + distance_penalty + grid_bonus
        if score < best_score:
            best_score = score
            best_time = float(candidate)
            best_rms = head_rms
    return best_time, {
        "enabled": 1.0,
        "base_resume_at_sec": round(base_resume_at, 3),
        "selected_resume_at_sec": round(best_time, 3),
        "search_sec": round(float(search_sec), 3),
        "render_tail_rms": round(float(render_tail_rms), 6),
        "selected_head_rms": round(float(best_rms), 6),
        "relative_jump": round(abs(best_rms - render_tail_rms) / max(best_rms, render_tail_rms, 1e-9), 4),
        "shift_sec": round(float(best_time - base_resume_at), 3),
    }


def _load_mono_window(
    path: str,
    *,
    start_sec: float,
    end_sec: float,
    target_sr: int,
    soundfile_mod: Any,
    librosa_mod: Any,
) -> tuple[np.ndarray, float, dict[str, Any]]:
    info = soundfile_mod.info(path)
    source_sr = int(info.samplerate)
    duration = float(info.duration)
    start = max(0.0, min(float(start_sec), duration))
    end = max(start, min(float(end_sec), duration))
    start_frame = int(round(start * source_sr))
    frames = max(1, int(round((end - start) * source_sr)))
    audio, read_sr = soundfile_mod.read(
        path,
        start=start_frame,
        frames=frames,
        dtype="float32",
        always_2d=True,
    )
    mono = np.mean(np.asarray(audio, dtype=np.float32), axis=1)
    if int(read_sr) != int(target_sr):
        mono = librosa_mod.resample(mono, orig_sr=int(read_sr), target_sr=int(target_sr))
    return np.asarray(mono, dtype=np.float32), start, {
        "start_sec": round(start, 3),
        "end_sec": round(end, 3),
        "duration_sec": round(end - start, 3),
        "source_sample_rate": int(source_sr),
        "target_sample_rate": int(target_sr),
        "source_format": str(info.format),
    }


def _match_resume_tail_energy(
    mixed: np.ndarray,
    resume_search: dict[str, Any],
) -> tuple[np.ndarray, dict[str, Any]]:
    if len(mixed) == 0 or not resume_search or not resume_search.get("enabled"):
        return mixed, {"applied": 0.0}
    tail_rms = float(resume_search.get("render_tail_rms") or 0.0)
    head_rms = float(resume_search.get("selected_head_rms") or 0.0)
    if tail_rms <= 1e-8 or head_rms <= 1e-8:
        return mixed, {"applied": 0.0}
    relative_jump = abs(head_rms - tail_rms) / max(head_rms, tail_rms, 1e-9)
    if relative_jump <= 0.12:
        return mixed, {"applied": 0.0, "relative_jump": round(float(relative_jump), 4)}
    gain = float(np.clip(head_rms / tail_rms, 0.9, 1.18))
    adjusted_tail = tail_rms * gain
    adjusted_jump = abs(head_rms - adjusted_tail) / max(head_rms, adjusted_tail, 1e-9)
    resume_search["render_tail_rms"] = round(float(adjusted_tail), 6)
    resume_search["relative_jump"] = round(float(adjusted_jump), 4)
    return mixed * gain, {
        "applied": 1.0,
        "mode": "constant_transition_gain_no_fade",
        "gain": round(float(gain), 6),
        "gain_db": round(float(20.0 * math.log10(max(gain, 1e-10))), 3),
        "before_relative_jump": round(float(relative_jump), 4),
        "after_relative_jump": round(float(adjusted_jump), 4),
    }


def _near_grid(t: float, values: Any, *, tolerance: float) -> bool:
    if not isinstance(values, list):
        return False
    for value in values:
        try:
            if abs(float(value) - float(t)) <= tolerance:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _rms(audio: np.ndarray) -> float:
    if len(audio) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio))))


def _bpm(song: Any) -> float:
    music_features = getattr(song, "music_features", None) or {}
    return float(getattr(song, "bpm", None) or music_features.get("bpm") or 120.0)


def _mtime(path: str) -> float | None:
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
