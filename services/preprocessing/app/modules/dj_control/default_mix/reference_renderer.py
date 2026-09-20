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
from pathlib import Path
from typing import Any

import numpy as np


NAS_DEFAULT_ROOT = Path("/mnt/nas/harbeat/dj-control/default-mix/pair-cache")
LOCAL_DEFAULT_ROOT = Path("data/default-mix/pair-cache")


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

    sr = 44100
    prev_audio, _ = librosa.load(prev_path, sr=sr, mono=True)
    next_audio, _ = librosa.load(next_path, sr=sr, mono=True)
    from_at = float(default_meta.get("from_at_sec") or plan.get("from_at_sec") or 0.0)
    to_at = float(default_meta.get("to_at_sec") or plan.get("to_at_sec") or 0.0)
    fade_sec = float(default_meta.get("duration_sec") or plan.get("duration_sec") or 6.5)
    fade_sec = max(3.0, min(12.0, fade_sec))
    samples = max(1, int(round(fade_sec * sr)))

    prev_start = max(0, int(round(from_at * sr)))
    next_start = max(0, int(round(to_at * sr)))
    region_a = _slice_with_pad(prev_audio, prev_start, samples)
    region_b = _slice_with_pad(next_audio, next_start, samples)

    # Match only the transition entrance.  This avoids the big volume collapse
    # caused by global normalization while still reducing head/tail mismatch.
    region_b, gain_db = _match_head_energy(region_a, region_b, sr)

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
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    if peak > 0.98:
        mixed = mixed * (0.98 / peak)

    tmp_wav = wav_path.with_name(f"{wav_path.stem}.tmp{wav_path.suffix}")
    sf.write(tmp_wav, mixed.astype(np.float32), sr)
    os.replace(tmp_wav, wav_path)

    meta = {
        "source": "default_mix_reference_renderer_v1",
        "pair_id": pair_id,
        "from_song_id": str(getattr(prev_song, "id", "")),
        "to_song_id": str(getattr(next_song, "id", "")),
        "from_at_sec": round(from_at, 3),
        "to_at_sec": round(to_at, 3),
        "duration_sec": round(samples / sr, 3),
        "resume_at_sec": round(to_at + samples / sr, 3),
        "render_strategy": "three_band_default",
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
        "energy_match_gain_db": round(float(gain_db), 3),
        "prev_source_mtime": prev_mtime,
        "next_source_mtime": next_mtime,
    }
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**meta, "cached": False}


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
    low_a = _smootherstep(x, reverse=False)
    low_b = _smootherstep(x, reverse=True)
    # Low frequencies overlap a little longer, matching the offline default
    # strategy while keeping total level additive instead of volume-ducked.
    low_a = 0.45 * low_a + 0.55 * _sigmoid(x, steepness=6.0, center=0.58, reverse=False)
    low_b = 0.45 * low_b + 0.55 * _sigmoid(x, steepness=6.0, center=0.42, reverse=True)
    width = 0.10 if bpm_diff > 30 else (0.16 if bpm_diff > 15 else 0.24)
    mid_a = _step(x, switch_point=0.5, blend_width=width, reverse=False)
    mid_b = _step(x, switch_point=0.5, blend_width=width, reverse=True)
    high_a = _cosine(x, reverse=False) * 0.9
    high_b = _cosine(x, reverse=True) * 0.9
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


def _match_head_energy(a: np.ndarray, b: np.ndarray, sr: int) -> tuple[np.ndarray, float]:
    win = max(1, int(min(2.0, max(1.0, len(a) / sr * 0.35)) * sr))
    tail = a[-win:]
    head = b[:win]
    rms_a = _rms(tail)
    rms_b = _rms(head)
    if rms_a <= 1e-8 or rms_b <= 1e-8:
        return b, 0.0
    gain = float(np.clip(rms_a / rms_b, 0.75, 1.35))
    gain_db = 20.0 * math.log10(max(gain, 1e-10))
    return b * gain, gain_db


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
