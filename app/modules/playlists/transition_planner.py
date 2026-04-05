from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

try:
    import librosa  # type: ignore
except Exception:  # pragma: no cover - optional dependency in lightweight envs
    librosa = None

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None


@dataclass
class TrackFeature:
    song_id: int
    bpm: Optional[float]
    camelot_key: Optional[str]
    duration: float


@dataclass
class TransitionTimingPlan:
    entry_beat: int
    exit_beat: int
    entry_time_sec: float
    exit_time_sec: float
    from_beat_interval_sec: float
    to_beat_interval_sec: float
    phase_anchor_sec: float
    crossfade_sec: float
    technique: str


def _normalize_camelot(key: str | None) -> str | None:
    if not key:
        return None
    s = key.strip().upper()
    if len(s) < 2:
        return None
    num, mode = s[:-1], s[-1]
    if not num.isdigit() or mode not in {'A', 'B'}:
        return None
    n = int(num)
    if n < 1 or n > 12:
        return None
    return f'{n}{mode}'


def camelot_relation(a: str | None, b: str | None) -> str:
    ka = _normalize_camelot(a)
    kb = _normalize_camelot(b)
    if not ka or not kb:
        return 'unknown'

    na, ma = int(ka[:-1]), ka[-1]
    nb, mb = int(kb[:-1]), kb[-1]
    if ka == kb:
        return 'same-key'
    if na == nb and ma != mb:
        return 'relative'
    if ma == mb and ((na % 12) + 1 == nb or (nb % 12) + 1 == na):
        return 'neighbor'
    return 'clash'


def harmonic_compatible(a: str | None, b: str | None, strict: bool) -> bool:
    rel = camelot_relation(a, b)
    if rel in {'same-key', 'relative', 'neighbor'}:
        return True
    return not strict


def _tempo_score(from_bpm: Optional[float], to_bpm: Optional[float], max_shift: float) -> tuple[float, float]:
    if not from_bpm or not to_bpm or from_bpm <= 0 or to_bpm <= 0:
        return 0.35, 1.0

    ratio = to_bpm / from_bpm
    candidates = [ratio, ratio / 2.0, ratio * 2.0]
    ratio = min(candidates, key=lambda x: abs(1.0 - x))
    diff = abs(1.0 - ratio)
    score = max(0.0, 1.0 - (diff / max(max_shift, 1e-6)))
    return score, float(ratio)


def within_tempo_shift(from_bpm: Optional[float], to_bpm: Optional[float], max_shift: float) -> bool:
    if not from_bpm or not to_bpm or from_bpm <= 0 or to_bpm <= 0:
        return True
    _, ratio = _tempo_score(from_bpm, to_bpm, max_shift)
    return abs(1.0 - ratio) <= max_shift + 1e-6


def _energy_score(from_energy: Optional[str], to_energy: Optional[str]) -> float:
    levels = {'low': 0, 'medium': 1, 'high': 2}
    if not from_energy or not to_energy:
        return 0.5
    fa = levels.get(from_energy.lower().strip())
    tb = levels.get(to_energy.lower().strip())
    if fa is None or tb is None:
        return 0.5
    return max(0.0, 1.0 - abs(fa - tb) / 2.0)


def _phrase_score(from_duration: float, to_duration: float, crossfade_sec: float) -> float:
    if from_duration <= 0 or to_duration <= 0:
        return 0.3
    tail_room = max(0.0, from_duration - crossfade_sec * 2.0)
    return min(1.0, 0.4 + min(tail_room / 32.0, 0.6))


def _nearest_beat_index(beat_points: list[float], target_sec: float) -> int:
    if not beat_points:
        return 1
    best_i = 0
    best_dist = float("inf")
    for i, sec in enumerate(beat_points):
        d = abs(sec - target_sec)
        if d < best_dist:
            best_dist = d
            best_i = i
    return best_i + 1


def _estimate_beat_interval(beat_points: list[float] | None, fallback_bpm: Optional[float]) -> float:
    beats = beat_points or []
    if len(beats) >= 4:
        deltas = []
        for i in range(1, len(beats)):
            d = beats[i] - beats[i - 1]
            if 0.2 <= d <= 1.6:
                deltas.append(d)
        if deltas:
            deltas.sort()
            return float(deltas[len(deltas) // 2])
    if fallback_bpm and fallback_bpm > 0:
        return float(60.0 / fallback_bpm)
    return 0.5


def _round_to_phrase(beat_number: int, phrase_beats: int) -> int:
    if beat_number <= 1:
        return 1
    rounded = int(round((beat_number - 1) / phrase_beats) * phrase_beats) + 1
    return max(1, rounded)


def _section_label_at(cue_points: list[dict] | None, target_sec: float) -> str:
    if not cue_points:
        return ""
    cues = sorted(cue_points, key=lambda c: float(c.get("time", 0.0)))
    active = ""
    for cue in cues:
        csec = float(cue.get("time", 0.0))
        if csec <= target_sec:
            active = str(cue.get("label") or "").strip().lower()
        else:
            break
    return active


def plan_phrase_transition(
    from_track: TrackFeature,
    to_track: TrackFeature,
    crossfade_sec: float,
    from_beat_points: list[float] | None = None,
    to_beat_points: list[float] | None = None,
    from_cue_points: list[dict] | None = None,
) -> TransitionTimingPlan:
    from_beats = from_beat_points or []
    to_beats = to_beat_points or []
    base_bpm = from_track.bpm or to_track.bpm or 120.0
    phrase_beats = 32 if base_bpm >= 96 else 16

    ideal_exit_time = max(crossfade_sec + 8.0, from_track.duration - max(16.0, crossfade_sec + 4.0))
    if from_cue_points:
        outro_like = []
        for cue in from_cue_points:
            label = str(cue.get("label") or "").lower()
            if label in {"outro", "break", "bridge", "chorus", "drop"}:
                t = float(cue.get("time") or 0.0)
                if from_track.duration * 0.45 <= t <= from_track.duration - crossfade_sec - 2.0:
                    outro_like.append((abs(t - ideal_exit_time), t))
        if outro_like:
            ideal_exit_time = min(outro_like, key=lambda x: x[0])[1]

    exit_beat = _nearest_beat_index(from_beats, ideal_exit_time)
    exit_beat = _round_to_phrase(exit_beat, phrase_beats)

    if from_beats and 1 <= exit_beat <= len(from_beats):
        exit_time_sec = float(from_beats[exit_beat - 1])
    else:
        exit_time_sec = max(0.0, ideal_exit_time)

    exit_time_sec = min(exit_time_sec, max(0.0, from_track.duration - 0.25))

    entry_beat = 1
    if to_beats:
        entry_beat = _round_to_phrase(1, phrase_beats)
        entry_beat = max(1, min(entry_beat, len(to_beats)))
        entry_time_sec = float(to_beats[entry_beat - 1])
    else:
        entry_time_sec = 0.0

    section = _section_label_at(from_cue_points, exit_time_sec)
    if section in {"outro", "break", "bridge"}:
        technique = "eq_bass_swap"
    elif section in {"chorus", "drop"}:
        technique = "echo_style_cross"
    else:
        technique = "phrase_crossfade"

    if from_track.duration > 0:
        max_xf = max(1.5, min(16.0, from_track.duration * 0.15))
    else:
        max_xf = 8.0
    xf = max(1.0, min(crossfade_sec, max_xf))
    from_interval = _estimate_beat_interval(from_beats, from_track.bpm)
    to_interval = _estimate_beat_interval(to_beats, to_track.bpm)
    phase_anchor = max(0.0, exit_time_sec - xf)

    return TransitionTimingPlan(
        entry_beat=entry_beat,
        exit_beat=max(1, exit_beat),
        entry_time_sec=round(entry_time_sec, 3),
        exit_time_sec=round(exit_time_sec, 3),
        from_beat_interval_sec=round(from_interval, 4),
        to_beat_interval_sec=round(to_interval, 4),
        phase_anchor_sec=round(phase_anchor, 3),
        crossfade_sec=round(xf, 3),
        technique=technique,
    )


@lru_cache(maxsize=2048)
def _estimate_bpm(path: str) -> Optional[float]:
    if librosa is None:
        return None
    try:
        y, sr = librosa.load(path, sr=22050, mono=True, duration=120)
        bpm, _ = librosa.beat.beat_track(y=y, sr=sr)
        return float(bpm) if bpm else None
    except Exception:
        return None


@lru_cache(maxsize=2048)
def _estimate_camelot(path: str) -> Optional[str]:
    try:
        import essentia.standard as es  # type: ignore

        loader = es.MonoLoader(filename=path, sampleRate=44100)
        audio = loader()
        key, scale, _ = es.KeyExtractor()(audio)
        return _to_camelot(f'{key} {scale}')
    except Exception:
        pass

    if librosa is None or np is None:
        return None

    try:
        y, sr = librosa.load(path, sr=22050, mono=True, duration=120)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        profile = chroma.mean(axis=1)
        idx = int(np.argmax(profile))
        major = bool(profile[idx] >= np.median(profile))
        note = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'][idx]
        return _to_camelot(f"{note} {'major' if major else 'minor'}")
    except Exception:
        return None


def _to_camelot(key_scale: str) -> Optional[str]:
    mapping = {
        'C major': '8B',
        'G major': '9B',
        'D major': '10B',
        'A major': '11B',
        'E major': '12B',
        'B major': '1B',
        'F# major': '2B',
        'Gb major': '2B',
        'C# major': '3B',
        'Db major': '3B',
        'Ab major': '4B',
        'G# major': '4B',
        'Eb major': '5B',
        'D# major': '5B',
        'Bb major': '6B',
        'A# major': '6B',
        'F major': '7B',
        'A minor': '8A',
        'E minor': '9A',
        'B minor': '10A',
        'F# minor': '11A',
        'C# minor': '12A',
        'G# minor': '1A',
        'D# minor': '2A',
        'A# minor': '3A',
        'F minor': '4A',
        'C minor': '5A',
        'G minor': '6A',
        'D minor': '7A',
    }
    return mapping.get(key_scale.strip())


def build_features(
    song_id: int,
    duration: Optional[float],
    bpm: Optional[int | float],
    camelot_key: Optional[str],
    processed_file: str,
    allow_audio_estimation: bool = True,
) -> TrackFeature:
    audio_path = Path(processed_file)
    feature_bpm = float(bpm) if bpm else None
    feature_key = _normalize_camelot(camelot_key)
    feature_duration = float(duration or 0)

    if allow_audio_estimation and audio_path.is_file():
        if feature_bpm is None:
            feature_bpm = _estimate_bpm(str(audio_path))
        if feature_key is None:
            feature_key = _estimate_camelot(str(audio_path))
        if feature_duration <= 0 and librosa is not None:
            try:
                feature_duration = float(librosa.get_duration(path=str(audio_path)))
            except Exception:
                pass

    return TrackFeature(
        song_id=song_id,
        bpm=feature_bpm,
        camelot_key=feature_key,
        duration=max(0.0, feature_duration),
    )


def score_transition(
    from_track: TrackFeature,
    to_track: TrackFeature,
    from_energy: Optional[str],
    to_energy: Optional[str],
    strict_harmonic: bool,
    max_tempo_shift: float,
    crossfade_sec: float,
) -> tuple[float, float, str]:
    krel = camelot_relation(from_track.camelot_key, to_track.camelot_key)
    key_score = 1.0 if harmonic_compatible(from_track.camelot_key, to_track.camelot_key, strict_harmonic) else 0.0
    tempo_score, tempo_ratio = _tempo_score(from_track.bpm, to_track.bpm, max_tempo_shift)
    phrase_score = _phrase_score(from_track.duration, to_track.duration, crossfade_sec)
    energy_score = _energy_score(from_energy, to_energy)

    total = (
        0.35 * phrase_score
        + 0.30 * tempo_score
        + 0.25 * key_score
        + 0.10 * energy_score
    )
    return total, tempo_ratio, krel


def build_fx_automation(
    crossfade_sec: float,
    energy_target: str | None,
    technique: str | None = None,
) -> list[dict[str, float | str]]:
    e = (energy_target or 'medium').lower()
    gain_peak = 1.6 if e == 'high' else 1.0 if e == 'medium' else 0.6
    lowpass_end = 17000.0 if e == 'high' else 14000.0 if e == 'medium' else 11000.0
    t = (technique or '').lower()
    is_bass_swap = t in {'eq_bass_swap', 'echo_style_cross'}

    return [
        {
            'target': 'from',
            'time_sec': 0.0,
            'gain_db': 0.0,
            'lowpass_hz': 18000.0,
            'highpass_hz': 35.0,
            'eq_low_db': 0.0,
            'eq_mid_db': 0.0,
            'eq_high_db': 0.0,
        },
        {
            'target': 'from',
            'time_sec': round(crossfade_sec * (0.45 if is_bass_swap else 0.55), 3),
            'gain_db': -2.0,
            'lowpass_hz': 15000.0,
            'highpass_hz': 80.0,
            'eq_low_db': -7.0 if is_bass_swap else -5.0,
            'eq_mid_db': -1.5,
            'eq_high_db': -1.0,
        },
        {
            'target': 'from',
            'time_sec': round(crossfade_sec, 3),
            'gain_db': -8.0,
            'lowpass_hz': 9000.0,
            'highpass_hz': 140.0,
            'eq_low_db': -8.0,
            'eq_mid_db': -3.0,
            'eq_high_db': -3.0,
        },
        {
            'target': 'to',
            'time_sec': 0.0,
            'gain_db': -5.0,
            'lowpass_hz': 12000.0,
            'highpass_hz': 90.0,
            'eq_low_db': -7.0 if is_bass_swap else -2.0,
            'eq_mid_db': -1.0,
            'eq_high_db': -2.0,
        },
        {
            'target': 'to',
            'time_sec': round(crossfade_sec * (0.65 if is_bass_swap else 0.5), 3),
            'gain_db': gain_peak,
            'lowpass_hz': 15000.0,
            'highpass_hz': 80.0,
            'eq_low_db': 4.5 if is_bass_swap else 3.0,
            'eq_mid_db': 0.8,
            'eq_high_db': 1.2,
        },
        {
            'target': 'to',
            'time_sec': round(crossfade_sec, 3),
            'gain_db': 0.0,
            'lowpass_hz': lowpass_end,
            'highpass_hz': 65.0,
            'eq_low_db': 0.0,
            'eq_mid_db': 0.0,
            'eq_high_db': 0.0,
        },
    ]
