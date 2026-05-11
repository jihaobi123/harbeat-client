from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

import librosa
import numpy as np
import soundfile as sf

from app.modules.playlists.schemas import DjTransitionPlanItem

STEM_NAMES = ("vocals", "drums", "bass", "other")


@dataclass
class OfflineRenderTrackInput:
    song_id: int
    audio_path: str
    entry_time_sec: float = 0.0
    stems: dict[str, str] | None = None


@dataclass
class _PreparedTrack:
    song_id: int
    entry_time_sec: float
    mix: np.ndarray
    stems: dict[str, np.ndarray]


def _load_audio_mono(path: str, sample_rate: int, cache: dict[str, np.ndarray]) -> np.ndarray:
    normalized = os.path.normpath(path)
    cached = cache.get(normalized)
    if cached is not None:
        return cached
    audio, _ = librosa.load(normalized, sr=sample_rate, mono=True)
    if audio.ndim != 1:
        audio = np.asarray(audio).reshape(-1)
    out = audio.astype(np.float32, copy=False)
    cache[normalized] = out
    return out


def _slice_with_padding(audio: np.ndarray, start: int, length: int) -> np.ndarray:
    if length <= 0:
        return np.zeros(0, dtype=np.float32)
    if start < 0:
        start = 0
    end = start + length
    if start >= audio.size:
        return np.zeros(length, dtype=np.float32)
    if end <= audio.size:
        return audio[start:end].astype(np.float32, copy=False)
    out = np.zeros(length, dtype=np.float32)
    piece = audio[start:audio.size]
    out[: piece.size] = piece
    return out


def _rms(audio: np.ndarray) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float32), dtype=np.float64)))


def _match_rms(audio: np.ndarray, target: np.ndarray, lower: float = 0.35, upper: float = 2.8) -> np.ndarray:
    src = _rms(audio)
    dst = _rms(target)
    if src <= 1e-8 or dst <= 1e-8:
        return audio
    scale = max(lower, min(upper, dst / src))
    return audio * scale


def _equal_power_curves(length: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if length <= 0:
        empty = np.zeros(0, dtype=np.float32)
        return empty, empty, empty
    t = np.linspace(0.0, 1.0, num=length, endpoint=False, dtype=np.float32)
    from_curve = np.cos(t * (np.pi / 2.0)).astype(np.float32)
    to_curve = np.sin(t * (np.pi / 2.0)).astype(np.float32)
    return t, from_curve, to_curve


def _render_overlap(
    from_track: _PreparedTrack,
    to_track: _PreparedTrack,
    from_start_sample: int,
    overlap_samples: int,
    tempo_ratio: float,
    stem_aware: bool,
) -> tuple[np.ndarray, list[str]]:
    t, from_curve, to_curve = _equal_power_curves(overlap_samples)
    from_seg = _slice_with_padding(from_track.mix, from_start_sample, overlap_samples)
    to_seg = _slice_with_padding(to_track.mix, 0, overlap_samples)

    default_mix = (from_seg * from_curve) + (to_seg * to_curve)
    if not stem_aware:
        return default_mix.astype(np.float32, copy=False), []

    from_stems = from_track.stems
    to_stems = to_track.stems
    if not from_stems or not to_stems:
        return default_mix.astype(np.float32, copy=False), []

    from_gains = {name: from_curve.copy() for name in from_stems}
    to_gains = {name: to_curve.copy() for name in to_stems}
    applied: list[str] = []

    if "bass" in from_stems and "bass" in to_stems:
        # Bass-swap: outgoing bass exits early, incoming bass enters later.
        from_gains["bass"] *= np.clip(1.0 - (t * 1.8), 0.10, 1.0)
        to_bass_shape = np.where(
            t < 0.35,
            0.22,
            0.22 + (((t - 0.35) / 0.65) * 0.78),
        ).astype(np.float32)
        to_gains["bass"] *= np.clip(to_bass_shape, 0.0, 1.0)
        applied.append("bass_swap")

    if "vocals" in from_stems and "vocals" in to_stems:
        # Vocal-ducking to avoid obvious lyric clashes in overlap.
        from_gains["vocals"] *= 0.42
        to_vocal_shape = np.where(
            t < 0.55,
            0.35,
            0.35 + (((t - 0.55) / 0.45) * 0.65),
        ).astype(np.float32)
        to_gains["vocals"] *= np.clip(to_vocal_shape, 0.0, 1.0)
        applied.append("vocal_ducking")

    if "drums" in to_stems and abs(tempo_ratio - 1.0) > 0.04:
        # If BPM correction is larger, soften incoming drums in the first half.
        to_drum_shape = np.where(t < 0.45, 0.55, 1.0).astype(np.float32)
        to_gains["drums"] *= to_drum_shape
        applied.append("drum_soft_entry")

    if not applied:
        return default_mix.astype(np.float32, copy=False), []

    from_mix = np.zeros(overlap_samples, dtype=np.float32)
    to_mix = np.zeros(overlap_samples, dtype=np.float32)

    for stem_name, stem_audio in from_stems.items():
        from_mix += _slice_with_padding(stem_audio, from_start_sample, overlap_samples) * from_gains.get(stem_name, from_curve)
    for stem_name, stem_audio in to_stems.items():
        to_mix += _slice_with_padding(stem_audio, 0, overlap_samples) * to_gains.get(stem_name, to_curve)

    from_mix = _match_rms(from_mix, from_seg * from_curve)
    to_mix = _match_rms(to_mix, to_seg * to_curve)
    return (from_mix + to_mix).astype(np.float32, copy=False), applied


def render_offline_mix(
    tracks: list[OfflineRenderTrackInput],
    transitions: list[DjTransitionPlanItem],
    output_wav_path: str,
    sample_rate: int = 44100,
    stem_aware: bool = True,
) -> dict[str, Any]:
    if not tracks:
        raise ValueError("tracks must not be empty")

    cache: dict[str, np.ndarray] = {}
    prepared: list[_PreparedTrack] = []

    for track in tracks:
        if not track.audio_path or not os.path.isfile(track.audio_path):
            continue
        base_audio = _load_audio_mono(track.audio_path, sample_rate, cache)
        if base_audio.size == 0:
            continue
        entry_samples = max(0, int(round(max(0.0, float(track.entry_time_sec)) * sample_rate)))
        if entry_samples >= base_audio.size:
            continue
        trimmed_audio = base_audio[entry_samples:].astype(np.float32, copy=False)

        prepared_stems: dict[str, np.ndarray] = {}
        if stem_aware and track.stems:
            for stem_name in STEM_NAMES:
                stem_path = track.stems.get(stem_name)
                if not stem_path or not os.path.isfile(stem_path):
                    continue
                stem_audio = _load_audio_mono(stem_path, sample_rate, cache)
                if stem_audio.size <= entry_samples:
                    continue
                prepared_stems[stem_name] = stem_audio[entry_samples:].astype(np.float32, copy=False)
            # Require at least 2 stems to reduce risk of extreme artifacts.
            if len(prepared_stems) < 2:
                prepared_stems = {}

        prepared.append(
            _PreparedTrack(
                song_id=track.song_id,
                entry_time_sec=max(0.0, float(track.entry_time_sec)),
                mix=trimmed_audio,
                stems=prepared_stems,
            )
        )

    if not prepared:
        raise ValueError("no decodable track available for offline mix")

    # Keep transitions aligned to available tracks.
    usable_transitions = transitions[: max(0, len(prepared) - 1)]
    final_parts: list[np.ndarray] = []
    stem_rule_events: list[dict[str, Any]] = []
    consumed_prefix_samples = 0

    for idx, transition in enumerate(usable_transitions):
        from_track = prepared[idx]
        to_track = prepared[idx + 1]

        if consumed_prefix_samples >= from_track.mix.size:
            consumed_prefix_samples = 0
        from_remaining = from_track.mix[consumed_prefix_samples:]
        if from_remaining.size <= 0:
            consumed_prefix_samples = 0
            continue

        overlap_samples_requested = int(round(max(0.6, float(transition.crossfade_sec)) * sample_rate))
        max_overlap = min(from_remaining.size, to_track.mix.size)
        if max_overlap <= 0:
            final_parts.append(from_remaining.astype(np.float32, copy=False))
            consumed_prefix_samples = 0
            continue
        overlap_samples = max(1, min(overlap_samples_requested, max_overlap))

        trigger_in_remaining: int
        if transition.exit_time_sec is not None and transition.exit_time_sec > 0:
            exit_rel_sec = max(0.0, float(transition.exit_time_sec) - from_track.entry_time_sec)
            transition_start_total = int(round(exit_rel_sec * sample_rate)) - overlap_samples
            trigger_in_remaining = transition_start_total - consumed_prefix_samples
        else:
            trigger_in_remaining = from_remaining.size - overlap_samples

        trigger_in_remaining = max(0, min(trigger_in_remaining, max(0, from_remaining.size - overlap_samples)))
        if trigger_in_remaining > 0:
            final_parts.append(from_remaining[:trigger_in_remaining].astype(np.float32, copy=False))

        from_overlap_start = consumed_prefix_samples + trigger_in_remaining
        overlap_mix, applied_rules = _render_overlap(
            from_track=from_track,
            to_track=to_track,
            from_start_sample=from_overlap_start,
            overlap_samples=overlap_samples,
            tempo_ratio=float(transition.tempo_ratio or 1.0),
            stem_aware=stem_aware,
        )
        final_parts.append(overlap_mix)

        if applied_rules:
            stem_rule_events.append(
                {
                    "transition_index": idx,
                    "from_song_id": from_track.song_id,
                    "to_song_id": to_track.song_id,
                    "rules": applied_rules,
                    "crossfade_sec": round(overlap_samples / sample_rate, 3),
                }
            )

        # The first overlap chunk of next track has been consumed.
        consumed_prefix_samples = overlap_samples

    tail = prepared[-1].mix[consumed_prefix_samples:]
    if tail.size > 0:
        final_parts.append(tail.astype(np.float32, copy=False))

    if not final_parts:
        final_mix = np.zeros(1, dtype=np.float32)
    elif len(final_parts) == 1:
        final_mix = final_parts[0]
    else:
        final_mix = np.concatenate(final_parts).astype(np.float32, copy=False)

    peak = float(np.max(np.abs(final_mix))) if final_mix.size else 0.0
    if peak > 0.98:
        final_mix = final_mix / (peak + 1e-8) * 0.98

    os.makedirs(os.path.dirname(output_wav_path), exist_ok=True)
    sf.write(output_wav_path, final_mix, sample_rate, subtype="PCM_16")

    return {
        "sample_rate": sample_rate,
        "duration_sec": round(final_mix.size / sample_rate, 3),
        "stem_rule_events": stem_rule_events,
    }


def _detect_mp3_encoders(ffmpeg: str) -> list[str]:
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        text = f"{proc.stdout}\n{proc.stderr}".lower()
    except Exception:
        return ["libmp3lame", "libshine", "mp3"]

    ordered = []
    for name in ("libmp3lame", "libshine", "mp3"):
        if name in text:
            ordered.append(name)
    if not ordered:
        ordered = ["libmp3lame", "libshine", "mp3"]
    return ordered


def convert_wav_to_mp3(wav_path: str, mp3_path: str) -> tuple[bool, str | None]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False, "mp3 export skipped: ffmpeg not found (wav exported successfully)"

    os.makedirs(os.path.dirname(mp3_path), exist_ok=True)
    last_err = ""
    for encoder in _detect_mp3_encoders(ffmpeg):
        proc = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                wav_path,
                "-codec:a",
                encoder,
                "-q:a",
                "2",
                mp3_path,
            ],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0 and os.path.isfile(mp3_path):
            return True, None
        last_err = (proc.stderr or proc.stdout or "").strip()

    brief = last_err.splitlines()[-1] if last_err else "no mp3 encoder available in ffmpeg build"
    return False, f"mp3 export skipped: {brief} (install ffmpeg build with libmp3lame)"


# ── Loop rendering ───────────────────────────────────────────────────


def render_looped_section(
    audio: np.ndarray,
    loop_start_samples: int,
    loop_end_samples: int,
    repeat_count: int,
    crossfade_samples: int = 2048,
    sample_rate: int = 44100,
) -> np.ndarray:
    """Render a repeated audio segment with crossfade at loop boundaries.

    Concatenates [prefix] + [loop * repeat_count with crossfades] + [suffix].
    Each loop iteration crossfades the tail with the next iteration's head
    to avoid audible clicks (~46 ms at 44.1 kHz).

    Args:
        audio: Mono or stereo float32 numpy array.
        loop_start_samples: Start of the loop region (sample index).
        loop_end_samples: End of the loop region (sample index).
        repeat_count: How many times to repeat the loop.
        crossfade_samples: Crossfade length in samples.
        sample_rate: For reference only (not used).

    Returns:
        Float32 numpy array with the looped result.
    """
    is_mono = audio.ndim == 1
    if is_mono:
        audio = audio.reshape(-1, 1)

    prefix = audio[:loop_start_samples]
    loop_body = audio[loop_start_samples:loop_end_samples]
    suffix = audio[loop_end_samples:]

    if len(loop_body) < crossfade_samples * 2:
        # Loop is too short for crossfade; just repeat without it
        repeated = np.tile(loop_body, (repeat_count, 1))
    else:
        chunks = []
        for i in range(repeat_count):
            if i == 0:
                chunks.append(loop_body)
            else:
                # Crossfade: tail of previous iteration + head of this iteration
                tail = chunks[-1][-crossfade_samples:]
                head = loop_body[:crossfade_samples]
                # Equal-power crossfade curves
                fade_out = np.sqrt(
                    np.linspace(1.0, 0.0, crossfade_samples, dtype=np.float32)
                ).reshape(-1, 1)
                fade_in = np.sqrt(
                    np.linspace(0.0, 1.0, crossfade_samples, dtype=np.float32)
                ).reshape(-1, 1)
                blended = tail * fade_out + head * fade_in
                # Replace the tail of the previous chunk
                chunks[-1] = np.concatenate([chunks[-1][:-crossfade_samples], blended])
                chunks.append(loop_body[crossfade_samples:])

        repeated = np.concatenate(chunks)

    result = np.concatenate([prefix, repeated, suffix])

    if is_mono:
        return result.flatten().astype(np.float32)
    return result.astype(np.float32)
