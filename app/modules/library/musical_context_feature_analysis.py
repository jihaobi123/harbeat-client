"""Vocal delivery, harmony and production features used by style analysis."""
from __future__ import annotations

from typing import Any

import librosa
import numpy as np

from app.modules.library.style_feature_evidence import make_feature_evidence, unavailable_feature


MUSICAL_CONTEXT_VERSION = "musical_context_features_v2"
VOCAL_FEATURES = (
    "rap_delivery", "singing", "vocal_chop", "vocal_density",
    "syllabic_activity", "pitch_sustain_ratio", "melodic_contour",
    "vocal_chop_repetition",
)
HARMONY_FEATURES = ("harmonic_complexity", "jazz_soul_harmony", "chord_change_activity")
PRODUCTION_FEATURES = (
    "brightness", "dark_timbre", "distortion", "lofi_texture", "sample_texture",
    "electronic_production", "acoustic_production", "rage_synth",
    "rage_synth_candidate",
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
    method = "vocal_activity_pitch_rhythm_v2"
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
    valid_runs = []
    run = 0
    for value in valid:
        if value:
            run += 1
        elif run:
            valid_runs.append(run)
            run = 0
    if run:
        valid_runs.append(run)
    sustained_voiced_frames = sum(value for value in valid_runs if value * hop / sr >= 0.25)
    pitch_sustain_ratio = sustained_voiced_frames / max(int(np.sum(active[:len(valid)])), 1)
    syllabic_activity = _clamp(articulation_rate / 6.5)
    melodic_contour = _clamp(
        0.62 * _clamp(melodic_range / 12.0)
        + 0.38 * _clamp(pitch_motion / 2.5)
    )
    quality = _clamp(activity / 0.35) * _clamp(len(vocals) / (sr * 20.0))
    evidence = {
        "vocal_activity_fraction": round(activity, 4),
        "articulation_onsets_per_active_second": round(articulation_rate, 4),
        "voiced_fraction": round(voiced_fraction, 4),
        "voiced_confidence": round(voiced_confidence, 4),
        "melodic_range_semitones": round(melodic_range, 4),
        "median_pitch_motion_semitones": round(pitch_motion, 4),
        "pitch_sustain_ratio": round(pitch_sustain_ratio, 4),
    }
    return ({
        "rap_delivery": make_feature_evidence(
            rap, threshold=0.58, confidence=quality, sources=["vocals_stem"],
            source_quality=0.75, estimator_quality=0.70,
            analysis_method=method, time_ranges=active_ranges, evidence=evidence,
        ),
        "singing": make_feature_evidence(
            singing, threshold=0.58, confidence=quality, sources=["vocals_stem"],
            source_quality=0.75, estimator_quality=0.78,
            analysis_method=method, time_ranges=active_ranges, evidence=evidence,
        ),
        "vocal_chop": make_feature_evidence(
            vocal_chop, threshold=0.60, confidence=quality, sources=["vocals_stem", "beat_grid"],
            source_quality=0.75, estimator_quality=0.64,
            analysis_method=method, time_ranges=short_ranges,
            evidence={
                "active_region_count": len(active_ranges),
                "short_region_count": len(short_ranges),
                "maximum_short_region_sec": 0.75,
                "repetition_score": round(repetition, 4),
            },
        ),
        "vocal_density": make_feature_evidence(
            _clamp(activity / 0.70), threshold=0.55, confidence=quality,
            source_quality=0.75, estimator_quality=0.82,
            sources=["vocals_stem"], analysis_method=method,
            time_ranges=active_ranges, evidence=evidence,
        ),
        "syllabic_activity": make_feature_evidence(
            syllabic_activity, threshold=0.55, confidence=quality,
            source_quality=0.75, estimator_quality=0.72,
            sources=["vocals_stem"], analysis_method=method,
            time_ranges=active_ranges, evidence=evidence,
        ),
        "pitch_sustain_ratio": make_feature_evidence(
            pitch_sustain_ratio, threshold=0.55, confidence=quality,
            source_quality=0.75, estimator_quality=0.80,
            sources=["vocals_stem"], analysis_method=method,
            time_ranges=active_ranges, evidence=evidence,
        ),
        "melodic_contour": make_feature_evidence(
            melodic_contour, threshold=0.55, confidence=quality,
            source_quality=0.75, estimator_quality=0.76,
            sources=["vocals_stem"], analysis_method=method,
            time_ranges=active_ranges, evidence=evidence,
        ),
        "vocal_chop_repetition": make_feature_evidence(
            vocal_chop, threshold=0.60, confidence=quality,
            source_quality=0.75, estimator_quality=0.64,
            sources=["vocals_stem", "beat_grid"], analysis_method=method,
            time_ranges=short_ranges,
            evidence={"short_region_fraction": round(short_fraction, 4), "repetition_score": round(repetition, 4)},
        ),
    }, quality, evidence)


def _harmony_features(
    source: np.ndarray | None,
    sr: int,
    key_profile: dict | None,
    beat_points: list[float] | np.ndarray | None = None,
) -> tuple[dict[str, dict], float]:
    method = "beat_synchronous_chroma_harmony_v2"
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
    hop = 512
    chroma = librosa.feature.chroma_stft(y=harmonic, sr=sr, n_fft=4096, hop_length=hop)
    normalized = chroma / (np.sum(chroma, axis=0, keepdims=True) + 1e-10)
    entropy = -np.sum(normalized * np.log2(normalized + 1e-10), axis=0) / np.log2(12.0)
    active_pitch_classes = np.sum(normalized >= 0.10, axis=0)
    complexity = _clamp(
        0.55 * float(np.mean(entropy))
        + 0.45 * _clamp((float(np.mean(active_pitch_classes)) - 2.0) / 4.5)
    )
    beat_array = np.asarray([] if beat_points is None else beat_points, dtype=float)
    beat_array = beat_array[np.isfinite(beat_array)]
    beat_frames = np.unique(np.clip(
        librosa.time_to_frames(beat_array, sr=sr, hop_length=hop), 0, chroma.shape[1] - 1,
    )) if len(beat_array) else np.asarray([], dtype=int)
    synchronous = []
    if len(beat_frames) >= 4:
        for start, end in zip(beat_frames[:-1], beat_frames[1:]):
            if end > start:
                synchronous.append(np.mean(normalized[:, start:end], axis=1))
        sampling_mode = "beat_synchronous"
        change_reliability_cap = 1.0
    else:
        block_frames = max(1, int(round(0.5 * sr / hop)))
        for start in range(0, normalized.shape[1] - block_frames + 1, block_frames):
            synchronous.append(np.mean(normalized[:, start:start + block_frames], axis=1))
        sampling_mode = "fixed_500ms_fallback"
        change_reliability_cap = 0.72
    synchronous_array = np.asarray(synchronous, dtype=float).T if synchronous else np.empty((12, 0))
    if synchronous_array.shape[1] >= 2:
        differences = 1.0 - np.sum(
            synchronous_array[:, 1:] * synchronous_array[:, :-1], axis=0,
        ) / (
            np.linalg.norm(synchronous_array[:, 1:], axis=0)
            * np.linalg.norm(synchronous_array[:, :-1], axis=0)
            + 1e-10
        )
        mean_change = float(np.mean(differences))
        upper_change = float(np.percentile(differences, 75))
        # Beat-local timbre and voicing create a non-zero chroma distance even
        # without a harmonic transition.  Subtract that floor and use a broad
        # continuous range so ordinary arrangements do not saturate at 1.0.
        change_activity = _clamp(
            0.60 * _clamp((mean_change - 0.06) / 0.30)
            + 0.40 * _clamp((upper_change - 0.10) / 0.45)
        )
        change_coverage = _clamp(len(differences) / 24.0)
        change_stability = _clamp(1.0 - float(np.std(differences)) / 0.35)
    else:
        differences = np.asarray([])
        mean_change = 0.0
        upper_change = 0.0
        change_activity = 0.0
        change_coverage = 0.0
        change_stability = 0.0
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
        "mean_adjacent_chord_distance": round(mean_change, 4),
        "upper_quartile_chord_distance": round(upper_change, 4),
        "chord_distance_noise_floor": {"mean": 0.06, "upper_quartile": 0.10},
        "harmony_sampling_mode": sampling_mode,
        "harmonic_state_count": int(synchronous_array.shape[1]),
        "existing_key_tonal_clarity": round(tonal_clarity, 4),
        "semantic_rule": "jazz_soul_harmony is a harmonic-language candidate, not a chord-name transcription",
    }
    sources = ["other_stem", "full_mix", "key_analysis"]
    return ({
        "harmonic_complexity": make_feature_evidence(
            complexity, threshold=0.60, confidence=quality, sources=sources,
            source_quality=0.75, estimator_quality=0.70,
            analysis_method=method, evidence=evidence,
        ),
        "jazz_soul_harmony": make_feature_evidence(
            jazz_soul, threshold=0.64, confidence=quality, sources=sources,
            source_quality=0.75, estimator_quality=0.58,
            analysis_method=method, evidence=evidence,
        ),
        "chord_change_activity": make_feature_evidence(
            change_activity, threshold=0.58, confidence=quality, sources=sources,
            source_quality=0.75, estimator_quality=0.72,
            coverage=change_coverage, stability=change_stability,
            reliability_cap=change_reliability_cap,
            analysis_method=method, evidence=evidence,
        ),
    }, quality)


def _production_features(
    source: np.ndarray | None,
    other: np.ndarray | None,
    sr: int,
    beat_points: list[float] | np.ndarray | None = None,
) -> tuple[dict[str, dict], float]:
    method = "beat_synchronous_production_profile_v3"
    audio = source if source is not None and len(source) >= sr else other
    if audio is None or len(audio) < sr:
        return ({
            name: unavailable_feature(
                "full_mix_and_other_stem_unavailable", sources=["full_mix", "other_stem"],
                analysis_method=method,
            ) for name in PRODUCTION_FEATURES
        }, 0.0)
    audio = np.asarray(audio, dtype=float)
    trim_offset_sec = 0.0
    if len(audio) > sr * 90:
        trim_start = (len(audio) - sr * 90) // 2
        trim_offset_sec = trim_start / sr
        audio = audio[trim_start:][:sr * 90]
    n_fft = min(2048, 2 ** int(np.floor(np.log2(max(len(audio), 512)))))
    production_hop = max(128, n_fft // 4)
    spectrum = np.abs(librosa.stft(audio, n_fft=n_fft, hop_length=production_hop)) + 1e-10
    centroid = float(np.mean(librosa.feature.spectral_centroid(S=spectrum, sr=sr)))
    rolloff = float(np.mean(librosa.feature.spectral_rolloff(S=spectrum, sr=sr, roll_percent=0.85)))
    flatness = float(np.mean(librosa.feature.spectral_flatness(S=spectrum)))
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(audio)))
    crest = float(np.max(np.abs(audio)) / (np.sqrt(np.mean(np.square(audio))) + 1e-8))
    absolute = np.abs(audio)
    clipping_ratio = float(np.mean(absolute >= max(0.98 * float(np.max(absolute)), 1e-8)))
    frame_rms = librosa.feature.rms(y=audio, frame_length=2048, hop_length=512)[0]
    noise_floor_ratio = float(np.percentile(frame_rms, 10) / (np.median(frame_rms) + 1e-8))
    onset_envelope = librosa.onset.onset_strength(y=audio, sr=sr, hop_length=512)
    transient_contrast = float(
        np.percentile(onset_envelope, 95) / (np.mean(onset_envelope) + 1e-8)
    ) if len(onset_envelope) else 0.0
    harmonic, percussive = librosa.effects.hpss(audio)
    harmonic_ratio = float(np.sqrt(np.mean(np.square(harmonic))) / (np.sqrt(np.mean(np.square(audio))) + 1e-8))
    brightness = _clamp((centroid - 900.0) / 3300.0)
    dark = _clamp((1800.0 - centroid) / 1200.0)
    distortion = _clamp(
        0.25 * _clamp(flatness / 0.18)
        + 0.25 * _clamp((4.6 - crest) / 3.2)
        + 0.20 * _clamp(zcr / 0.18)
        + 0.18 * _clamp(clipping_ratio / 0.08)
        + 0.12 * _clamp(noise_floor_ratio / 0.55)
    )
    lofi = _clamp(
        0.34 * (1.0 - _clamp(rolloff / min(8500.0, sr * 0.46)))
        + 0.22 * _clamp(flatness / 0.16)
        + 0.18 * _clamp(noise_floor_ratio / 0.55)
        + 0.14 * _clamp((3.5 - transient_contrast) / 2.5)
        + 0.12 * _clamp(zcr / 0.16)
    )

    mfcc_hop = 1024
    mfcc = librosa.feature.mfcc(y=audio, sr=sr, n_mfcc=13, hop_length=mfcc_hop)
    beat_array = np.asarray([] if beat_points is None else beat_points, dtype=float) - trim_offset_sec
    beat_array = beat_array[
        np.isfinite(beat_array) & (beat_array >= 0.0) & (beat_array <= len(audio) / sr)
    ]
    beat_frames = np.unique(np.clip(
        librosa.time_to_frames(beat_array, sr=sr, hop_length=mfcc_hop), 0, mfcc.shape[1] - 1,
    )) if len(beat_array) else np.asarray([], dtype=int)
    beat_vectors = []
    if len(beat_frames) >= 12:
        for start, end in zip(beat_frames[:-1], beat_frames[1:]):
            if end > start:
                beat_vectors.append(np.mean(mfcc[1:, start:end], axis=1))
        repeat_sampling_mode = "beat_synchronous_lags_4_8_16"
        repeat_reliability_cap = 1.0
    else:
        block_frames = max(1, int(round(2.0 * sr / mfcc_hop)))
        for start in range(0, mfcc.shape[1] - block_frames + 1, block_frames):
            beat_vectors.append(np.mean(mfcc[1:, start:start + block_frames], axis=1))
        repeat_sampling_mode = "fixed_2s_fallback"
        repeat_reliability_cap = 0.65
    if len(beat_vectors) >= 8:
        vectors = np.asarray(beat_vectors, dtype=float).T
        vectors -= np.mean(vectors, axis=1, keepdims=True)
        vectors /= np.linalg.norm(vectors, axis=0, keepdims=True) + 1e-10
        requested_lags = (4, 8, 16) if repeat_sampling_mode.startswith("beat_") else (1, 2, 4)
        lag_similarities = {
            lag: np.sum(vectors[:, lag:] * vectors[:, :-lag], axis=0)
            for lag in requested_lags if vectors.shape[1] > lag + 3
        }
        all_similarities = np.concatenate(list(lag_similarities.values())) if lag_similarities else np.asarray([])
        lag_medians = [float(np.median(values)) for values in lag_similarities.values() if len(values)]
        repeat_similarity = float(np.percentile(all_similarities, 75)) if len(all_similarities) else 0.0
        recurrence_coverage = float(np.mean(all_similarities >= 0.72)) if len(all_similarities) else 0.0
        repeat_stability = _clamp(
            1.0 - float(np.std(lag_medians)) / 0.35
        ) if len(lag_medians) >= 2 else 0.5
        sample_texture = _clamp((repeat_similarity - 0.42) / 0.42)
        sample_texture *= _clamp(recurrence_coverage / 0.40)
        # A single favourable lag is common in ordinary arrangements.  Loop
        # texture requires recurrence to persist across bar-scale lags.
        sample_texture *= 0.35 + 0.65 * repeat_stability
        envelope_variance = _clamp(float(np.mean(np.std(vectors, axis=1))) / 0.35)
        repeat_coverage = _clamp(len(all_similarities) / 48.0)
    else:
        sample_texture = 0.0
        repeat_similarity = 0.0
        recurrence_coverage = 0.0
        repeat_stability = 0.0
        repeat_coverage = 0.0
        lag_medians = []
        envelope_variance = 0.0
    acoustic = _clamp(
        0.36 * harmonic_ratio
        + 0.24 * envelope_variance
        + 0.20 * (1.0 - _clamp(repeat_similarity))
        + 0.20 * (1.0 - distortion)
    )
    electronic = _clamp(
        0.30 * brightness
        + 0.25 * _clamp(flatness / 0.20)
        + 0.25 * _clamp(repeat_similarity)
        + 0.20 * (1.0 - acoustic)
    )
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
        "clipping_candidate_ratio": round(clipping_ratio, 5),
        "noise_floor_ratio": round(noise_floor_ratio, 4),
        "transient_contrast": round(transient_contrast, 4),
        "sample_repeat_similarity": round(repeat_similarity, 4),
        "sample_recurrence_coverage": round(recurrence_coverage, 4),
        "sample_repeat_stability": round(repeat_stability, 4),
        "sample_repeat_lag_medians": [round(value, 4) for value in lag_medians],
        "sample_repeat_sampling_mode": repeat_sampling_mode,
        "spectral_envelope_variance": round(envelope_variance, 4),
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
        "rage_synth_candidate": rage,
    }
    return ({
        name: make_feature_evidence(
            score, threshold=0.60, confidence=quality, sources=["full_mix", "other_stem"],
            source_quality=0.75,
            estimator_quality=(
                0.58 if name in {"distortion", "lofi_texture", "rage_synth", "rage_synth_candidate"}
                else 0.68
            ),
            coverage=repeat_coverage if name == "sample_texture" else 1.0,
            stability=repeat_stability if name == "sample_texture" else 1.0,
            reliability_cap=repeat_reliability_cap if name == "sample_texture" else 1.0,
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
    native_other: np.ndarray | None = None,
    native_original_audio: np.ndarray | None = None,
    native_sr: int | None = None,
    beat_points: list[float] | np.ndarray | None = None,
) -> dict[str, Any]:
    vocal, vocal_quality, vocal_summary = _vocal_features(vocals, sr)
    harmonic_source = other if other is not None and len(other) >= sr else original_audio
    harmony, harmony_quality = _harmony_features(
        harmonic_source, sr, key_profile, beat_points,
    )
    production_source = native_other if native_other is not None else other
    production_sr = int(native_sr or sr)
    production, production_quality = _production_features(
        native_original_audio, production_source, production_sr, beat_points,
    )
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
