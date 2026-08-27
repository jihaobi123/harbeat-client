"""Vocal delivery, harmony and production features used by style analysis."""
from __future__ import annotations

from typing import Any

import librosa
import numpy as np

from app.modules.library.style_feature_evidence import make_feature_evidence, unavailable_feature


MUSICAL_CONTEXT_VERSION = "musical_context_features_v1"
VOCAL_FEATURES = ("rap_delivery", "singing", "vocal_chop")
HARMONY_FEATURES = ("harmonic_complexity", "jazz_soul_harmony", "chord_change_activity")
PRODUCTION_FEATURES = (
    "brightness", "dark_timbre", "distortion", "lofi_texture", "sample_texture",
    "electronic_production", "acoustic_production", "rage_synth",
)


def _clamp(value: float) -> float:
    return float(np.clip(float(value), 0.0, 1.0))


def _ranges(mask: np.ndarray, hop: int, sr: int, minimum_frames: int = 1) -> list[dict[str, float]]:
    ranges = []
    start = None
    for index, active in enumerate(np.r_[mask, False]):
        if active and start is None:
            start = index
        elif not active and start is not None:
            if index - start >= minimum_frames:
                ranges.append({
                    "start": round(start * hop / sr, 4),
                    "end": round(index * hop / sr, 4),
                })
            start = None
    return ranges[:48]


def _vocal_features(vocals: np.ndarray | None, sr: int) -> tuple[dict[str, dict], float, dict]:
    method = "vocal_activity_pitch_rhythm_v1"
    if vocals is None or len(vocals) < sr:
        return ({
            name: unavailable_feature(
                "vocals_stem_unavailable", sources=["vocals_stem"], analysis_method=method
            ) for name in VOCAL_FEATURES
        }, 0.0, {"status": "unavailable"})
    vocals = np.asarray(vocals, dtype=float)
    hop = 256
    rms = librosa.feature.rms(y=vocals, frame_length=1024, hop_length=hop)[0]
    gate = max(float(np.percentile(rms, 58)) * 0.35, 1e-7)
    active = rms >= gate
    activity = float(np.mean(active))
    onset_envelope = librosa.onset.onset_strength(y=vocals, sr=sr, hop_length=hop)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_envelope, sr=sr, hop_length=hop, units="frames"
    )
    active_duration = max(activity * len(vocals) / sr, 1e-6)
    articulation_rate = len(onset_frames) / active_duration

    f0, voiced_flag, voiced_probability = librosa.pyin(
        vocals,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
        sr=sr,
        frame_length=2048,
        hop_length=hop,
    )
    valid = np.isfinite(f0) & active[:len(f0)]
    voiced_fraction = float(np.mean(valid[active[:len(f0)]])) if np.any(active[:len(f0)]) else 0.0
    if np.sum(valid) >= 4:
        midi = librosa.hz_to_midi(f0[valid])
        melodic_range = float(np.percentile(midi, 90) - np.percentile(midi, 10))
        pitch_motion = float(np.median(np.abs(np.diff(midi)))) if len(midi) >= 2 else 0.0
    else:
        melodic_range = 0.0
        pitch_motion = 0.0
    voiced_confidence = float(np.nanmean(voiced_probability[valid])) if np.any(valid) else 0.0
    singing = _clamp(
        0.46 * _clamp(voiced_fraction / 0.72)
        + 0.24 * _clamp(melodic_range / 10.0)
        + 0.18 * _clamp(voiced_confidence / 0.75)
        + 0.12 * _clamp((4.5 - articulation_rate) / 3.0)
    )
    rap = _clamp(
        0.46 * _clamp((articulation_rate - 2.0) / 4.5)
        + 0.27 * _clamp((0.62 - voiced_fraction) / 0.50)
        + 0.17 * _clamp(pitch_motion / 2.8)
        + 0.10 * _clamp(activity / 0.65)
    )
    active_ranges = _ranges(active, hop, sr, minimum_frames=2)
    short_ranges = [item for item in active_ranges if item["end"] - item["start"] <= 0.75]
    short_fraction = len(short_ranges) / max(len(active_ranges), 1)
    starts = np.asarray([item["start"] for item in short_ranges], dtype=float)
    intervals = np.diff(starts)
    repetition = 0.0
    if len(intervals) >= 3:
        repetition = _clamp(1.0 - float(np.std(intervals)) / max(float(np.mean(intervals)), 1e-6))
    vocal_chop = _clamp(0.62 * short_fraction + 0.38 * repetition)
    quality = _clamp(activity / 0.35) * _clamp(len(vocals) / (sr * 20.0))
    evidence = {
        "vocal_activity_fraction": round(activity, 4),
        "articulation_onsets_per_active_second": round(articulation_rate, 4),
        "voiced_fraction": round(voiced_fraction, 4),
        "voiced_confidence": round(voiced_confidence, 4),
        "melodic_range_semitones": round(melodic_range, 4),
        "median_pitch_motion_semitones": round(pitch_motion, 4),
    }
    return ({
        "rap_delivery": make_feature_evidence(
            rap, threshold=0.58, confidence=quality, sources=["vocals_stem"],
            analysis_method=method, time_ranges=active_ranges, evidence=evidence,
        ),
        "singing": make_feature_evidence(
            singing, threshold=0.58, confidence=quality, sources=["vocals_stem"],
            analysis_method=method, time_ranges=active_ranges, evidence=evidence,
        ),
        "vocal_chop": make_feature_evidence(
            vocal_chop, threshold=0.60, confidence=quality, sources=["vocals_stem", "beat_grid"],
            analysis_method=method, time_ranges=short_ranges,
            evidence={
                "active_region_count": len(active_ranges),
                "short_region_count": len(short_ranges),
                "maximum_short_region_sec": 0.75,
                "repetition_score": round(repetition, 4),
            },
        ),
    }, quality, evidence)


def _harmony_features(source: np.ndarray | None, sr: int, key_profile: dict | None) -> tuple[dict[str, dict], float]:
    method = "chroma_harmony_activity_v1"
    if source is None or len(source) < sr:
        return ({
            name: unavailable_feature(
                "harmonic_audio_unavailable", sources=["other_stem", "full_mix", "key_analysis"],
                analysis_method=method,
            ) for name in HARMONY_FEATURES
        }, 0.0)
    source = np.asarray(source, dtype=float)
    harmonic, _ = librosa.effects.hpss(source)
    # STFT chroma remains valid at low deployment sample rates where the
    # default high-octave CQT basis can exceed Nyquist.
    chroma = librosa.feature.chroma_stft(y=harmonic, sr=sr, n_fft=4096, hop_length=512)
    normalized = chroma / (np.sum(chroma, axis=0, keepdims=True) + 1e-10)
    entropy = -np.sum(normalized * np.log2(normalized + 1e-10), axis=0) / np.log2(12.0)
    active_pitch_classes = np.sum(normalized >= 0.10, axis=0)
    complexity = _clamp(
        0.55 * float(np.mean(entropy))
        + 0.45 * _clamp((float(np.mean(active_pitch_classes)) - 2.0) / 4.5)
    )
    differences = 1.0 - np.sum(normalized[:, 1:] * normalized[:, :-1], axis=0) / (
        np.linalg.norm(normalized[:, 1:], axis=0) * np.linalg.norm(normalized[:, :-1], axis=0) + 1e-10
    )
    change_activity = _clamp(float(np.mean(differences)) / 0.42) if len(differences) else 0.0
    extended_chord_fraction = float(np.mean(active_pitch_classes >= 4))
    tonal_clarity = _clamp(float((key_profile or {}).get("tonal_clarity", 0.5) or 0.5))
    jazz_soul = _clamp(
        0.44 * complexity + 0.34 * _clamp(extended_chord_fraction / 0.55)
        + 0.22 * change_activity
    )
    quality = _clamp(len(source) / (sr * 20.0)) * _clamp(float(np.mean(np.sum(chroma, axis=0) > 1e-5)) / 0.75)
    evidence = {
        "mean_chroma_entropy": round(float(np.mean(entropy)), 4),
        "mean_active_pitch_classes": round(float(np.mean(active_pitch_classes)), 4),
        "extended_chord_frame_fraction": round(extended_chord_fraction, 4),
        "chroma_change_activity": round(change_activity, 4),
        "existing_key_tonal_clarity": round(tonal_clarity, 4),
        "semantic_rule": "jazz_soul_harmony is a harmonic-language candidate, not a chord-name transcription",
    }
    sources = ["other_stem", "full_mix", "key_analysis"]
    return ({
        "harmonic_complexity": make_feature_evidence(
            complexity, threshold=0.60, confidence=quality, sources=sources,
            analysis_method=method, evidence=evidence,
        ),
        "jazz_soul_harmony": make_feature_evidence(
            jazz_soul, threshold=0.64, confidence=quality, sources=sources,
            analysis_method=method, evidence=evidence,
        ),
        "chord_change_activity": make_feature_evidence(
            change_activity, threshold=0.58, confidence=quality, sources=sources,
            analysis_method=method, evidence=evidence,
        ),
    }, quality)


def _production_features(source: np.ndarray | None, other: np.ndarray | None, sr: int) -> tuple[dict[str, dict], float]:
    method = "spectral_production_profile_v1"
    audio = source if source is not None and len(source) >= sr else other
    if audio is None or len(audio) < sr:
        return ({
            name: unavailable_feature(
                "full_mix_and_other_stem_unavailable", sources=["full_mix", "other_stem"],
                analysis_method=method,
            ) for name in PRODUCTION_FEATURES
        }, 0.0)
    audio = np.asarray(audio, dtype=float)
    if len(audio) > sr * 90:
        audio = audio[(len(audio) - sr * 90) // 2:][:sr * 90]
    spectrum = np.abs(librosa.stft(audio, n_fft=2048, hop_length=512)) + 1e-10
    centroid = float(np.mean(librosa.feature.spectral_centroid(S=spectrum, sr=sr)))
    rolloff = float(np.mean(librosa.feature.spectral_rolloff(S=spectrum, sr=sr, roll_percent=0.85)))
    flatness = float(np.mean(librosa.feature.spectral_flatness(S=spectrum)))
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(audio)))
    crest = float(np.max(np.abs(audio)) / (np.sqrt(np.mean(np.square(audio))) + 1e-8))
    harmonic, percussive = librosa.effects.hpss(audio)
    harmonic_ratio = float(np.sqrt(np.mean(np.square(harmonic))) / (np.sqrt(np.mean(np.square(audio))) + 1e-8))
    brightness = _clamp((centroid - 900.0) / 3300.0)
    dark = _clamp((1800.0 - centroid) / 1200.0)
    distortion = _clamp(0.42 * _clamp(flatness / 0.18) + 0.38 * _clamp((4.6 - crest) / 3.2) + 0.20 * _clamp(zcr / 0.18))
    lofi = _clamp(0.48 * (1.0 - _clamp(rolloff / 8500.0)) + 0.28 * _clamp(flatness / 0.16) + 0.24 * _clamp(zcr / 0.16))
    acoustic = _clamp(0.58 * harmonic_ratio + 0.24 * (1.0 - _clamp(flatness / 0.20)) + 0.18 * (1.0 - distortion))
    electronic = _clamp(0.46 * brightness + 0.30 * _clamp(flatness / 0.20) + 0.24 * (1.0 - acoustic))

    mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13, hop_length=1024)
    if mfcc.shape[1] >= 8:
        normalized = mfcc / (np.linalg.norm(mfcc, axis=0, keepdims=True) + 1e-10)
        lag_frames = max(1, int(round(2.0 * sr / 1024)))
        similarities = np.sum(normalized[:, lag_frames:] * normalized[:, :-lag_frames], axis=0)
        sample_texture = _clamp((float(np.percentile(similarities, 90)) - 0.55) / 0.38)
    else:
        sample_texture = 0.0
    other_audio = np.asarray(other, dtype=float) if other is not None and len(other) >= sr else audio
    other_centroid = float(np.mean(librosa.feature.spectral_centroid(y=other_audio, sr=sr)))
    other_flatness = float(np.mean(librosa.feature.spectral_flatness(y=other_audio)))
    rage = _clamp(
        0.36 * _clamp((other_centroid - 1900.0) / 2600.0)
        + 0.30 * _clamp(other_flatness / 0.16)
        + 0.34 * distortion
    )
    quality = _clamp(len(audio) / (sr * 20.0))
    evidence = {
        "spectral_centroid_hz": round(centroid, 3),
        "spectral_rolloff_85_hz": round(rolloff, 3),
        "spectral_flatness": round(flatness, 5),
        "zero_crossing_rate": round(zcr, 5),
        "crest_factor": round(crest, 4),
        "harmonic_energy_ratio": round(harmonic_ratio, 4),
        "other_stem_centroid_hz": round(other_centroid, 3),
    }
    scores = {
        "brightness": brightness,
        "dark_timbre": dark,
        "distortion": distortion,
        "lofi_texture": lofi,
        "sample_texture": sample_texture,
        "electronic_production": electronic,
        "acoustic_production": acoustic,
        "rage_synth": rage,
    }
    return ({
        name: make_feature_evidence(
            score, threshold=0.60, confidence=quality, sources=["full_mix", "other_stem"],
            analysis_method=method, evidence=evidence,
        ) for name, score in scores.items()
    }, quality)


def analyze_musical_context_features(
    *,
    vocals: np.ndarray | None,
    other: np.ndarray | None,
    original_audio: np.ndarray | None,
    sr: int,
    key_profile: dict | None = None,
) -> dict[str, Any]:
    vocal, vocal_quality, vocal_summary = _vocal_features(vocals, sr)
    harmonic_source = other if other is not None and len(other) >= sr else original_audio
    harmony, harmony_quality = _harmony_features(harmonic_source, sr, key_profile)
    production, production_quality = _production_features(original_audio, other, sr)
    quality = float(np.mean([vocal_quality, harmony_quality, production_quality]))
    flags = []
    if vocal_quality == 0:
        flags.append("vocals_stem_unavailable")
    if harmony_quality == 0:
        flags.append("harmonic_audio_unavailable")
    if production_quality == 0:
        flags.append("production_audio_unavailable")
    return {
        "version": MUSICAL_CONTEXT_VERSION,
        "status": "ready" if quality >= 0.55 else "degraded",
        "vocal_delivery": vocal,
        "harmony": harmony,
        "production": production,
        "vocal_summary": vocal_summary,
        "confidence": {
            "overall": round(quality, 4),
            "vocal": round(vocal_quality, 4),
            "harmony": round(harmony_quality, 4),
            "production": round(production_quality, 4),
        },
        "quality_flags": flags,
    }
