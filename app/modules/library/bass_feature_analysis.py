"""Event-level Bass, 808 and Log Drum feature analysis.

The analyser uses the Bass stem for pitched body, the Drums stem/event list for
the attack, and the full mix only as a consistency check.  A bass slide is kept
separate from 808 identity so either observation can exist without the other.
"""
from __future__ import annotations

from typing import Any

import librosa
import numpy as np

from app.modules.library.style_feature_evidence import (
    make_feature_evidence,
    unavailable_feature,
)


BASS_FEATURE_VERSION = "bass_features_v1"
BASS_FEATURE_NAMES = (
    "sub_bass",
    "bass_pitch_stability",
    "bass_slide",
    "kick_bass_alignment",
    "sub_808",
    "sliding_808",
    "log_drum",
)


def _clamp(value: float) -> float:
    return float(np.clip(float(value), 0.0, 1.0))


def _event_times(drum_analysis: dict | None, name: str) -> np.ndarray:
    values = []
    for event in ((drum_analysis or {}).get("events") or {}).get(name, []):
        try:
            values.append(float(event.get("time", event)))
        except (AttributeError, TypeError, ValueError):
            continue
    return np.sort(np.asarray(values, dtype=float))


def _bass_onsets(audio: np.ndarray, sr: int) -> np.ndarray:
    envelope = librosa.onset.onset_strength(y=audio, sr=sr, hop_length=256)
    frames = librosa.onset.onset_detect(
        onset_envelope=envelope,
        sr=sr,
        hop_length=256,
        backtrack=True,
        units="frames",
    )
    times = np.unique(librosa.frames_to_time(frames, sr=sr, hop_length=256))
    # Bass envelopes often create a second onset at the note tail. Keep one
    # analysis anchor per perceptual event instead of counting detector echoes.
    retained = []
    for value in times:
        if not retained or float(value) - retained[-1] >= 0.40:
            retained.append(float(value))
    return np.asarray(retained, dtype=float)


def _nearest_distance(value: float, references: np.ndarray) -> float | None:
    if not len(references):
        return None
    return float(np.min(np.abs(references - value)))


def _band_energy(power: np.ndarray, frequencies: np.ndarray, low: float, high: float) -> float:
    mask = (frequencies >= low) & (frequencies < high)
    return float(np.sum(power[mask]))


def _pitch_track(clip: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    n_fft = 4096
    hop = 256
    spectrum = np.abs(librosa.stft(clip, n_fft=n_fft, hop_length=hop))
    frequencies = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    mask = (frequencies >= 28.0) & (frequencies <= 220.0)
    low = spectrum[mask]
    if not low.size:
        return np.asarray([]), np.asarray([])
    strengths = np.max(low, axis=0)
    pitches = frequencies[mask][np.argmax(low, axis=0)]
    gate = max(float(np.percentile(strengths, 45)), 1e-8)
    voiced = strengths >= gate
    return pitches[voiced], strengths[voiced]


def _event_descriptor(
    bass: np.ndarray,
    drums: np.ndarray | None,
    mix: np.ndarray | None,
    sr: int,
    time_sec: float,
    kick_times: np.ndarray,
) -> dict[str, Any] | None:
    start = max(0, int((time_sec - 0.015) * sr))
    end = min(len(bass), start + int(0.9 * sr))
    clip = np.asarray(bass[start:end], dtype=float)
    if len(clip) < int(0.20 * sr):
        return None

    windowed = clip * np.hanning(len(clip))
    magnitude = np.abs(np.fft.rfft(windowed))
    power = magnitude ** 2
    frequencies = np.fft.rfftfreq(len(clip), 1.0 / sr)
    reference_energy = _band_energy(power, frequencies, 20.0, 1000.0) + 1e-12
    sub_ratio = _band_energy(power, frequencies, 25.0, 95.0) / reference_energy

    pitches, strengths = _pitch_track(clip, sr)
    if len(pitches) >= 3:
        midi = 69.0 + 12.0 * np.log2(np.maximum(pitches, 1e-6) / 440.0)
        fundamental = float(np.median(pitches))
        pitch_spread = float(np.median(np.abs(midi - np.median(midi))))
        pitch_stability = _clamp(1.0 - pitch_spread / 1.6)
        positions = np.arange(len(midi), dtype=float)
        slope = float(np.polyfit(positions, midi, 1)[0]) if len(midi) >= 4 else 0.0
        pitch_motion = slope * max(len(midi) - 1, 0)
        voiced_strength = _clamp(float(np.mean(strengths)) / (float(np.max(magnitude)) + 1e-12))
    else:
        fundamental = 0.0
        pitch_stability = 0.0
        pitch_motion = 0.0
        voiced_strength = 0.0

    harmonic_energy = 0.0
    if fundamental > 0:
        for multiple in (1, 2, 3, 4, 5):
            center = fundamental * multiple
            width = max(4.0, center * 0.045)
            harmonic_energy += _band_energy(power, frequencies, center - width, center + width)
    harmonic_ratio = _clamp(harmonic_energy / reference_energy)

    frame_length = min(1024, len(clip))
    rms = librosa.feature.rms(y=clip, frame_length=frame_length, hop_length=128, center=False)[0]
    peak = float(np.max(rms)) if len(rms) else 0.0
    peak_index = int(np.argmax(rms)) if len(rms) else 0
    active = np.where(rms >= peak * 0.22)[0] if peak > 0 else np.asarray([])
    decay_sec = float((active[-1] - peak_index + 1) * 128 / sr) if len(active) else 0.0
    early_end = min(len(clip), int(0.075 * sr))
    body_end = min(len(clip), int(0.32 * sr))
    early_rms = float(np.sqrt(np.mean(np.square(clip[:early_end])))) + 1e-10
    body_rms = float(np.sqrt(np.mean(np.square(clip[early_end:body_end])))) if body_end > early_end else 0.0
    attack_body_ratio = early_rms / (body_rms + 1e-10)

    kick_distance = _nearest_distance(time_sec, kick_times)
    kick_aligned = kick_distance is not None and kick_distance <= 0.085
    drum_transient_ratio = 0.0
    if drums is not None and len(drums) >= end:
        drum_clip = np.asarray(drums[start:min(end, start + int(0.16 * sr))], dtype=float)
        if len(drum_clip):
            drum_transient_ratio = _clamp(
                np.sqrt(np.mean(np.square(drum_clip))) / (early_rms + 1e-8)
            )

    mix_low_consistency = None
    if mix is not None and len(mix) >= end:
        mix_clip = np.asarray(mix[start:end], dtype=float) * np.hanning(len(clip))
        mix_power = np.abs(np.fft.rfft(mix_clip)) ** 2
        mix_reference = _band_energy(mix_power, frequencies, 20.0, 1000.0) + 1e-12
        mix_low_consistency = _clamp(
            _band_energy(mix_power, frequencies, 25.0, 180.0) / mix_reference
        )

    return {
        "time": round(float(time_sec), 4),
        "fundamental_hz": round(fundamental, 3),
        "sub_ratio_25_95_hz": round(float(sub_ratio), 4),
        "pitch_stability": round(pitch_stability, 4),
        "pitch_motion_semitones": round(pitch_motion, 4),
        "harmonic_ratio_f0_to_5f0": round(harmonic_ratio, 4),
        "voiced_strength": round(voiced_strength, 4),
        "decay_sec": round(max(0.0, decay_sec), 4),
        "attack_body_ratio": round(float(attack_body_ratio), 4),
        "kick_distance_sec": None if kick_distance is None else round(kick_distance, 4),
        "kick_aligned": bool(kick_aligned),
        "drum_transient_ratio": round(drum_transient_ratio, 4),
        "mix_low_consistency": None if mix_low_consistency is None else round(mix_low_consistency, 4),
    }


def _ranges(events: list[dict[str, Any]], predicate) -> list[dict[str, float]]:
    return [
        {"start": item["time"], "end": round(item["time"] + 0.35, 4)}
        for item in events if predicate(item)
    ][:48]


def analyze_bass_features(
    bass: np.ndarray | None,
    drums: np.ndarray | None,
    sr: int,
    *,
    drum_analysis: dict | None = None,
    beat_points: list[float] | np.ndarray | None = None,
    original_audio: np.ndarray | None = None,
) -> dict[str, Any]:
    """Analyse Bass-stem events and return style-independent evidence."""
    method = "bass_stft_event_fusion_v1"
    required_sources = ["bass_stem", "drums_stem", "full_mix"]
    if bass is None or sr <= 0 or len(bass) < sr:
        return {
            "version": BASS_FEATURE_VERSION,
            "status": "unavailable",
            "features": {
                name: unavailable_feature(
                    "bass_stem_unavailable",
                    sources=required_sources if name in {"sub_808", "sliding_808"} else ["bass_stem"],
                    analysis_method=method,
                )
                for name in BASS_FEATURE_NAMES
            },
            "events": [],
            "confidence": 0.0,
            "quality_flags": ["bass_stem_unavailable"],
        }

    bass = np.asarray(bass, dtype=float)
    drums = np.asarray(drums, dtype=float) if drums is not None else None
    original_audio = np.asarray(original_audio, dtype=float) if original_audio is not None else None
    duration = len(bass) / sr
    kick_times = _event_times(drum_analysis, "kick")
    onsets = _bass_onsets(bass, sr)
    events = [
        descriptor
        for timestamp in onsets[:256]
        if (descriptor := _event_descriptor(
            bass, drums, original_audio, sr, float(timestamp), kick_times,
        )) is not None
    ]
    quality = _clamp(len(events) / max(6.0, duration / 5.0))
    flags: list[str] = []
    if not events:
        flags.append("no_bass_events_detected")
    if drums is None:
        flags.append("drums_stem_unavailable")
    if original_audio is None:
        flags.append("full_mix_unavailable")
    if not len(kick_times):
        flags.append("kick_events_unavailable")

    def average(key: str) -> float:
        values = [float(item[key]) for item in events if item.get(key) is not None]
        return float(np.mean(values)) if values else 0.0

    sub_score = _clamp(average("sub_ratio_25_95_hz") / 0.72)
    stability_score = average("pitch_stability")
    harmonic_score = _clamp(average("harmonic_ratio_f0_to_5f0") / 0.72)
    sustain_score = _clamp((average("decay_sec") - 0.16) / 0.48)
    aligned_fraction = average("kick_aligned")
    transient_score = _clamp(average("drum_transient_ratio") / 0.8)
    slide_events = [
        item for item in events
        if abs(item["pitch_motion_semitones"]) >= 2.5 and item["decay_sec"] >= 0.12
    ]
    slide_score = _clamp(len(slide_events) / max(1.0, len(events) * 0.22))

    mix_values = [item["mix_low_consistency"] for item in events if item["mix_low_consistency"] is not None]
    mix_consistency = _clamp(float(np.mean(mix_values)) / 0.68) if mix_values else 0.5
    identity_808 = _clamp(
        0.28 * sub_score
        + 0.22 * stability_score
        + 0.18 * harmonic_score
        + 0.17 * sustain_score
        + 0.10 * max(aligned_fraction, transient_score)
        + 0.05 * mix_consistency
    )
    sliding_808 = _clamp(identity_808 * (0.55 + 0.45 * slide_score)) if slide_events else 0.0

    percussive = _clamp((average("attack_body_ratio") - 0.8) / 2.2)
    short_decay = _clamp((0.48 - average("decay_sec")) / 0.38)
    beat_array = np.asarray([] if beat_points is None else beat_points, dtype=float)
    beat_alignment = 0.0
    if len(onsets) and len(beat_array):
        beat_alignment = float(np.mean([
            (_nearest_distance(float(value), beat_array) or 9.0) <= 0.075 for value in onsets
        ]))
    syncopation = 1.0 - beat_alignment if len(beat_array) else 0.5
    log_drum_score = _clamp(
        0.25 * percussive
        + 0.22 * stability_score
        + 0.20 * short_decay
        + 0.18 * syncopation
        + 0.15 * (1.0 - aligned_fraction)
    )

    common = {
        "event_count": len(events),
        "frequency_scope_hz": [25, 1000],
    }
    features = {
        "sub_bass": make_feature_evidence(
            sub_score,
            confidence=quality,
            sources=["bass_stem"],
            analysis_method=method,
            time_ranges=_ranges(events, lambda item: item["sub_ratio_25_95_hz"] >= 0.42),
            evidence={**common, "mean_sub_ratio_25_95_hz": round(average("sub_ratio_25_95_hz"), 4)},
        ),
        "bass_pitch_stability": make_feature_evidence(
            stability_score,
            confidence=quality,
            sources=["bass_stem"],
            analysis_method=method,
            evidence={**common, "mean_pitch_stability": round(stability_score, 4)},
        ),
        "bass_slide": make_feature_evidence(
            slide_score,
            confidence=quality,
            sources=["bass_stem"],
            analysis_method=method,
            time_ranges=_ranges(events, lambda item: abs(item["pitch_motion_semitones"]) >= 2.5 and item["decay_sec"] >= 0.12),
            evidence={**common, "minimum_motion_semitones": 2.5, "slide_event_count": len(slide_events)},
        ),
        "kick_bass_alignment": make_feature_evidence(
            aligned_fraction,
            confidence=quality if len(kick_times) else 0.0,
            sources=["bass_stem", "drums_stem"],
            analysis_method=method,
            evidence={**common, "kick_event_count": len(kick_times), "tolerance_sec": 0.085},
        ) if len(kick_times) else unavailable_feature(
            "kick_events_unavailable",
            sources=["bass_stem", "drums_stem"],
            analysis_method=method,
        ),
        "sub_808": make_feature_evidence(
            identity_808,
            threshold=0.62,
            confidence=quality * (0.85 if drums is None else 1.0),
            sources=required_sources,
            analysis_method=method,
            time_ranges=_ranges(events, lambda item: item["sub_ratio_25_95_hz"] >= 0.42 and item["pitch_stability"] >= 0.55),
            evidence={
                **common,
                "sub_score": round(sub_score, 4),
                "pitch_stability_score": round(stability_score, 4),
                "harmonic_score": round(harmonic_score, 4),
                "sustain_score": round(sustain_score, 4),
                "kick_or_drum_transient_score": round(max(aligned_fraction, transient_score), 4),
                "mix_consistency_score": round(mix_consistency, 4),
                "semantic_rule": "808 identity requires pitched sub body plus harmonic/sustain evidence; slide is not required",
            },
        ),
        "sliding_808": make_feature_evidence(
            sliding_808,
            threshold=0.62,
            confidence=quality,
            sources=required_sources,
            analysis_method=method,
            time_ranges=_ranges(events, lambda item: abs(item["pitch_motion_semitones"]) >= 2.5 and item["decay_sec"] >= 0.12),
            evidence={
                **common,
                "sub_808_identity_score": round(identity_808, 4),
                "bass_slide_score": round(slide_score, 4),
                "semantic_rule": "requires both 808 identity and bass pitch motion",
            },
        ),
        "log_drum": make_feature_evidence(
            log_drum_score,
            threshold=0.62,
            confidence=quality,
            sources=["bass_stem", "drums_stem", "beat_grid"],
            analysis_method=method,
            time_ranges=_ranges(events, lambda item: item["attack_body_ratio"] >= 1.4 and item["decay_sec"] <= 0.48),
            evidence={
                **common,
                "percussive_attack_score": round(percussive, 4),
                "pitched_body_score": round(stability_score, 4),
                "short_decay_score": round(short_decay, 4),
                "syncopation_score": round(syncopation, 4),
                "kick_separation_score": round(1.0 - aligned_fraction, 4),
                "semantic_rule": "pitched low percussion with attack, decay and rhythmic reply behaviour",
            },
        ),
    }
    return {
        "version": BASS_FEATURE_VERSION,
        "status": "ready" if quality >= 0.55 else "degraded",
        "features": features,
        "events": events,
        "confidence": round(quality, 4),
        "quality_flags": flags,
    }
