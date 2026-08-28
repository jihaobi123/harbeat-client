"""Event-level bass behaviour and low-frequency timbre candidate analysis.

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


BASS_FEATURE_VERSION = "bass_features_v3"
BASS_FEATURE_NAMES = (
    "sub_bass",
    "bass_pitch_stability",
    "bass_slide",
    "kick_bass_alignment",
    "sustained_harmonic_bass_candidate",
    "sliding_bass_candidate",
    "low_percussive_bass_candidate",
    "low_frequency_melody",
    "bass_reply_pattern",
    "bass_syncopation",
    "bass_staccato_ratio",
    "bass_riff_repetition",
    "bass_octave_pattern",
    "bass_kick_interlock",
    "808_timbre_candidate",
    "log_drum_candidate",
    "sub_808",
    "sliding_808",
    "log_drum",
)

BASS_F0_MIN_HZ = 30.0
BASS_F0_MAX_HZ = 300.0
PYIN_FRAME_LENGTH = 4096
PYIN_HOP_LENGTH = 256
PYIN_MIN_VOICED_PROB = 0.60


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


def _set_similarity(left: set[tuple[int, float]], right: set[tuple[int, float]]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return 2.0 * len(left & right) / (len(left) + len(right))


def _bass_groove_descriptors(
    events: list[dict[str, Any]],
    beat_points: np.ndarray,
    downbeats: np.ndarray,
    kick_times: np.ndarray,
) -> dict[str, Any]:
    """Measure note placement and recurrence without assigning a style label."""
    ordered = sorted(events, key=lambda item: float(item["time"]))
    beat_intervals = np.diff(beat_points)
    valid_intervals = beat_intervals[(beat_intervals >= 0.20) & (beat_intervals <= 1.50)]
    beat_period = float(np.median(valid_intervals)) if len(valid_intervals) else 0.0

    placement_weights: list[float] = []
    quantized_steps: list[int] = []
    timing_offsets: list[float] = []
    if beat_period > 0 and len(beat_points) >= 2:
        for item in ordered:
            value = float(item["time"])
            index = int(np.searchsorted(beat_points, value, side="right") - 1)
            if index < 0 or index >= len(beat_points) - 1:
                continue
            local_period = float(beat_points[index + 1] - beat_points[index])
            if local_period <= 0:
                continue
            phase = np.clip((value - beat_points[index]) / local_period, 0.0, 0.9999)
            exact_step = float(phase * 4.0)
            step = int(round(exact_step)) % 4
            placement_weights.append({0: 0.0, 1: 1.0, 2: 0.75, 3: 1.0}[step])
            quantized_steps.append(step)
            timing_offsets.append(abs(exact_step - round(exact_step)) * local_period / 4.0)
    placement_coverage = len(placement_weights) / max(1, len(ordered))
    raw_syncopation = float(np.mean(placement_weights)) if placement_weights else 0.0
    syncopation_score = _clamp(raw_syncopation / 0.65)

    staccato_limit = min(0.32, 0.62 * beat_period) if beat_period else 0.28
    staccato_values = [float(item.get("decay_sec", 0.0)) <= staccato_limit for item in ordered]
    staccato_fraction = float(np.mean(staccato_values)) if staccato_values else 0.0
    staccato_score = _clamp(staccato_fraction / 0.70)

    pitched = [
        item for item in ordered
        if item.get("pitch_method") == "pyin_candidate_segment"
        and float(item.get("voiced_strength", 0.0)) >= PYIN_MIN_VOICED_PROB
        and float(item.get("fundamental_hz", 0.0)) > 0
    ]
    midi = np.asarray([
        69.0 + 12.0 * np.log2(float(item["fundamental_hz"]) / 440.0)
        for item in pitched
    ])
    pitch_intervals = np.diff(midi) if len(midi) >= 2 else np.asarray([])
    octave_mask = (np.abs(pitch_intervals) >= 10.75) & (np.abs(pitch_intervals) <= 13.25)
    octave_fraction = float(np.mean(octave_mask)) if len(pitch_intervals) else 0.0
    octave_score = _clamp(octave_fraction / 0.28)

    bar_patterns: list[set[tuple[int, float]]] = []
    if len(downbeats) >= 3:
        for start, end in zip(downbeats[:-1], downbeats[1:], strict=True):
            if end <= start:
                continue
            members = [item for item in pitched if start <= float(item["time"]) < end]
            if not members:
                bar_patterns.append(set())
                continue
            root = 69.0 + 12.0 * np.log2(float(members[0]["fundamental_hz"]) / 440.0)
            pattern = set()
            for item in members:
                position = (float(item["time"]) - start) / (end - start)
                step = int(np.clip(round(position * 16.0), 0, 15))
                note = 69.0 + 12.0 * np.log2(float(item["fundamental_hz"]) / 440.0)
                pattern.add((step, round((note - root) * 2.0) / 2.0))
            bar_patterns.append(pattern)
    recurrence_by_lag: dict[str, float] = {}
    for lag in (1, 2, 4):
        similarities = [
            _set_similarity(bar_patterns[index], bar_patterns[index + lag])
            for index in range(len(bar_patterns) - lag)
            if bar_patterns[index] and bar_patterns[index + lag]
        ]
        if similarities:
            recurrence_by_lag[str(lag)] = round(float(np.mean(similarities)), 4)
    recurrence = max(recurrence_by_lag.values(), default=0.0)
    bar_coverage = _divide_count(sum(bool(value) for value in bar_patterns), len(bar_patterns))
    riff_score = _clamp(recurrence * np.sqrt(bar_coverage))

    aligned = complementary = 0
    relation_limit = min(0.28, 0.55 * beat_period) if beat_period else 0.24
    if len(kick_times):
        for item in ordered:
            distance = _nearest_distance(float(item["time"]), kick_times)
            if distance is None:
                continue
            if distance <= 0.085:
                aligned += 1
            elif distance <= relation_limit:
                complementary += 1
    relation_coverage = (aligned + complementary) / max(1, len(ordered))
    complementary_share = complementary / max(1, aligned + complementary)
    interlock_score = _clamp(relation_coverage * (0.35 + 0.65 * complementary_share))
    return {
        "beat_period_sec": round(beat_period, 4),
        "placement_coverage": round(placement_coverage, 4),
        "sixteenth_steps_within_beat": quantized_steps,
        "mean_grid_offset_sec": round(float(np.mean(timing_offsets)), 4) if timing_offsets else None,
        "raw_syncopated_event_fraction": round(raw_syncopation, 4),
        "syncopation_score": syncopation_score,
        "staccato_limit_sec": round(staccato_limit, 4),
        "staccato_fraction": round(staccato_fraction, 4),
        "staccato_score": staccato_score,
        "octave_interval_fraction": round(octave_fraction, 4),
        "octave_interval_count": int(np.sum(octave_mask)),
        "pitched_interval_count": len(pitch_intervals),
        "octave_score": octave_score,
        "bar_count": len(bar_patterns),
        "bar_coverage": round(bar_coverage, 4),
        "recurrence_by_lag_bars": recurrence_by_lag,
        "riff_score": riff_score,
        "kick_aligned_count": aligned,
        "kick_complementary_count": complementary,
        "kick_relation_coverage": round(relation_coverage, 4),
        "interlock_score": interlock_score,
    }


def _divide_count(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def _spectral_peak_pitch_track(clip: np.ndarray, sr: int) -> dict[str, Any]:
    spectrum = np.abs(librosa.stft(
        clip, n_fft=PYIN_FRAME_LENGTH, hop_length=PYIN_HOP_LENGTH,
    ))
    frequencies = librosa.fft_frequencies(sr=sr, n_fft=PYIN_FRAME_LENGTH)
    mask = (frequencies >= BASS_F0_MIN_HZ) & (frequencies <= BASS_F0_MAX_HZ)
    low = spectrum[mask]
    if not low.size:
        return {"f0_hz": np.asarray([]), "voiced_prob": np.asarray([]), "method": "unavailable"}
    strengths = np.max(low, axis=0)
    pitches = frequencies[mask][np.argmax(low, axis=0)]
    gate = max(float(np.percentile(strengths, 45)), 1e-8)
    voiced = strengths >= gate
    normalized = strengths[voiced] / (float(np.max(strengths)) + 1e-12)
    return {
        "f0_hz": pitches[voiced],
        "voiced_prob": normalized,
        "method": "spectral_peak_fallback",
    }


def _pitch_track(clip: np.ndarray, sr: int) -> dict[str, Any]:
    """Estimate an event-local F0 trajectory, retaining an explicit fallback."""
    if len(clip) < PYIN_FRAME_LENGTH or sr <= 2 * BASS_F0_MAX_HZ:
        return _spectral_peak_pitch_track(clip, sr)
    try:
        f0, voiced, probability = librosa.pyin(
            np.asarray(clip, dtype=float),
            fmin=BASS_F0_MIN_HZ,
            fmax=min(BASS_F0_MAX_HZ, sr / 2.0 - 1.0),
            sr=sr,
            frame_length=PYIN_FRAME_LENGTH,
            hop_length=PYIN_HOP_LENGTH,
            fill_na=np.nan,
        )
        probability = np.asarray(probability, dtype=float)
        valid = (
            np.asarray(voiced, dtype=bool)
            & np.isfinite(f0)
            & np.isfinite(probability)
            & (probability >= PYIN_MIN_VOICED_PROB)
        )
        if int(np.sum(valid)) >= 3:
            return {
                "f0_hz": np.asarray(f0[valid], dtype=float),
                "voiced_prob": probability[valid],
                "method": "pyin_candidate_segment",
            }
    except (ValueError, FloatingPointError):
        pass
    return _spectral_peak_pitch_track(clip, sr)


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

    pitch_track = _pitch_track(clip, sr)
    pitches = pitch_track["f0_hz"]
    voiced_prob = pitch_track["voiced_prob"]
    if len(pitches) >= 3:
        midi = 69.0 + 12.0 * np.log2(np.maximum(pitches, 1e-6) / 440.0)
        fundamental = float(np.median(pitches))
        pitch_spread = float(np.median(np.abs(midi - np.median(midi))))
        pitch_stability = _clamp(1.0 - pitch_spread / 1.6)
        edge = max(1, len(midi) // 4)
        pitch_motion = float(np.median(midi[-edge:]) - np.median(midi[:edge]))
        voiced_strength = _clamp(float(np.mean(voiced_prob)))
    else:
        fundamental = 0.0
        pitch_stability = 0.0
        pitch_motion = 0.0
        voiced_strength = 0.0

    fundamental_energy = 0.0
    upper_harmonic_energy = 0.0
    if fundamental > 0:
        for multiple in (1, 2, 3, 4, 5):
            center = fundamental * multiple
            width = max(4.0, center * 0.045)
            value = _band_energy(power, frequencies, center - width, center + width)
            if multiple == 1:
                fundamental_energy = value
            else:
                upper_harmonic_energy += value
    harmonic_energy = fundamental_energy + upper_harmonic_energy
    harmonic_ratio = _clamp(harmonic_energy / reference_energy)
    fundamental_purity = _clamp(fundamental_energy / (harmonic_energy + 1e-12))

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
        "fundamental_purity": round(fundamental_purity, 4),
        "voiced_strength": round(voiced_strength, 4),
        "pitch_method": pitch_track["method"],
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
    downbeats: list[float] | np.ndarray | None = None,
    original_audio: np.ndarray | None = None,
    source_quality: float = 0.75,
) -> dict[str, Any]:
    """Analyse Bass-stem events and return style-independent evidence."""
    method = "bass_candidate_segment_pyin_v3"
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
    pitch_methods = sorted({str(item.get("pitch_method")) for item in events})
    if "spectral_peak_fallback" in pitch_methods:
        flags.append("bass_pitch_spectral_fallback_used")

    def average(key: str) -> float:
        values = [float(item[key]) for item in events if item.get(key) is not None]
        return float(np.mean(values)) if values else 0.0

    sub_score = _clamp(average("sub_ratio_25_95_hz") / 0.72)
    stability_score = average("pitch_stability")
    harmonic_score = _clamp(average("harmonic_ratio_f0_to_5f0") / 0.72)
    sine_dominance_score = _clamp((average("fundamental_purity") - 0.58) / 0.32)
    sustain_score = _clamp((average("decay_sec") - 0.16) / 0.48)
    aligned_fraction = average("kick_aligned")
    transient_score = _clamp(average("drum_transient_ratio") / 0.8)
    pyin_events = [
        item for item in events
        if item.get("pitch_method") == "pyin_candidate_segment"
        and float(item.get("voiced_strength", 0.0)) >= PYIN_MIN_VOICED_PROB
        and float(item.get("fundamental_hz", 0.0)) > 0
    ]
    pitch_evidence_coverage = len(pyin_events) / max(1, len(events))
    pitch_track_quality = (
        float(np.mean([float(item["voiced_strength"]) for item in pyin_events]))
        if pyin_events else 0.0
    )
    slide_events = [
        item for item in pyin_events
        if 2.5 <= abs(float(item["pitch_motion_semitones"])) <= 12.0
        and float(item["decay_sec"]) >= 0.12
    ]
    # A slide must be visible inside voiced event-local F0 tracks.  Spectral
    # peak jumps and a large range across separate notes are not slide proof.
    slide_score = _clamp(
        len(slide_events) / max(2.0, len(pyin_events) * 0.28)
    ) * _clamp(pitch_evidence_coverage / 0.45)
    pitched_sequence = [
        (float(item["time"]), float(item["fundamental_hz"]))
        for item in pyin_events
    ]
    if len(pitched_sequence) >= 3:
        midi_events = 69.0 + 12.0 * np.log2(
            np.asarray([value for _, value in pitched_sequence]) / 440.0
        )
        pitch_range = float(np.percentile(midi_events, 90) - np.percentile(midi_events, 10))
        intervals = np.abs(np.diff(midi_events))
        meaningful_fraction = float(np.mean((intervals >= 0.45) & (intervals <= 7.0)))
        implausible_fraction = float(np.mean(intervals > 12.0))
        pitch_diversity = _clamp((len(np.unique(np.round(midi_events * 2.0) / 2.0)) - 1) / 8.0)
        pitch_span = _clamp((pitch_range - 1.0) / 12.0)
        sequence_quality = _clamp(1.0 - implausible_fraction / 0.25)
        melody_score = _clamp(
            0.42 * meaningful_fraction
            + 0.24 * pitch_diversity
            + 0.18 * pitch_span
            + 0.16 * sequence_quality
        ) * _clamp(pitch_evidence_coverage / 0.55)
    else:
        pitch_range = 0.0
        meaningful_fraction = 0.0
        implausible_fraction = 0.0
        pitch_diversity = 0.0
        sequence_quality = 0.0
        melody_score = 0.0

    mix_values = [item["mix_low_consistency"] for item in events if item["mix_low_consistency"] is not None]
    mix_consistency = _clamp(float(np.mean(mix_values)) / 0.68) if mix_values else 0.5
    sustained_harmonic_score = _clamp(
        0.30 * stability_score
        + 0.25 * harmonic_score
        + 0.25 * sustain_score
        + 0.20 * sub_score
    )
    identity_808 = _clamp(
        0.30 * sub_score
        + 0.25 * sine_dominance_score
        + 0.18 * sustain_score
        + 0.12 * stability_score
        + 0.10 * max(aligned_fraction, transient_score)
        + 0.05 * mix_consistency
    )
    sliding_808 = _clamp(identity_808 * (0.55 + 0.45 * slide_score)) if slide_events else 0.0

    percussive = _clamp((average("attack_body_ratio") - 0.8) / 2.2)
    short_decay = _clamp((0.48 - average("decay_sec")) / 0.38)
    beat_array = np.asarray([] if beat_points is None else beat_points, dtype=float)
    downbeat_array = np.asarray([] if downbeats is None else downbeats, dtype=float)
    groove = _bass_groove_descriptors(events, beat_array, downbeat_array, kick_times)
    beat_alignment = 0.0
    if len(onsets) and len(beat_array):
        beat_alignment = float(np.mean([
            (_nearest_distance(float(value), beat_array) or 9.0) <= 0.075 for value in onsets
        ]))
    syncopation = float(groove["syncopation_score"]) if len(beat_array) else 0.5
    reply_score = _clamp(syncopation * (1.0 - aligned_fraction) * _clamp(len(events) / 6.0))
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
        "pitch_methods": pitch_methods,
        "minimum_voiced_probability": PYIN_MIN_VOICED_PROB,
    }
    source_quality = _clamp(source_quality)
    pitch_estimator_quality = 0.82 if pitch_methods == ["pyin_candidate_segment"] else 0.55
    pitch_reliability_cap = 1.0 if pitch_methods == ["pyin_candidate_segment"] else 0.62

    def feature(
        score: float,
        *,
        threshold: float = 0.55,
        estimator_quality: float = 0.72,
        confidence: float | None = None,
        sources: list[str],
        time_ranges: list[dict[str, Any]] | None = None,
        evidence: dict[str, Any] | None = None,
        coverage: float = 1.0,
        stability: float = 1.0,
        reliability_cap: float = 1.0,
    ) -> dict[str, Any]:
        return make_feature_evidence(
            score,
            threshold=threshold,
            confidence=quality if confidence is None else confidence,
            measurement_confidence=quality if confidence is None else confidence,
            source_quality=source_quality,
            estimator_quality=estimator_quality,
            coverage=coverage,
            stability=stability,
            reliability_cap=reliability_cap,
            quality_flags=flags,
            sources=sources,
            analysis_method=method,
            time_ranges=time_ranges,
            evidence=evidence,
        )

    features = {
        "sub_bass": feature(
            sub_score,
            estimator_quality=0.78,
            sources=["bass_stem"],
            time_ranges=_ranges(events, lambda item: item["sub_ratio_25_95_hz"] >= 0.42),
            evidence={**common, "mean_sub_ratio_25_95_hz": round(average("sub_ratio_25_95_hz"), 4)},
        ),
        "bass_pitch_stability": feature(
            stability_score,
            estimator_quality=pitch_estimator_quality,
            coverage=pitch_evidence_coverage,
            stability=pitch_track_quality,
            reliability_cap=pitch_reliability_cap,
            sources=["bass_stem"],
            evidence={
                **common,
                "mean_pitch_stability": round(stability_score, 4),
                "voiced_event_coverage": round(pitch_evidence_coverage, 4),
            },
        ),
        "bass_slide": feature(
            slide_score,
            estimator_quality=pitch_estimator_quality,
            coverage=pitch_evidence_coverage,
            stability=pitch_track_quality,
            reliability_cap=pitch_reliability_cap,
            sources=["bass_stem"],
            time_ranges=_ranges(slide_events, lambda item: True),
            evidence={
                **common,
                "motion_range_semitones": [2.5, 12.0],
                "slide_event_count": len(slide_events),
                "voiced_event_count": len(pyin_events),
                "voiced_event_coverage": round(pitch_evidence_coverage, 4),
                "semantic_rule": "voiced event-local F0 motion; pitch differences between separate notes do not count as slides",
            },
        ),
        "kick_bass_alignment": feature(
            aligned_fraction,
            confidence=quality if len(kick_times) else 0.0,
            estimator_quality=0.80,
            sources=["bass_stem", "drums_stem"],
            evidence={**common, "kick_event_count": len(kick_times), "tolerance_sec": 0.085},
        ) if len(kick_times) else unavailable_feature(
            "kick_events_unavailable",
            sources=["bass_stem", "drums_stem"],
            analysis_method=method,
        ),
        "808_timbre_candidate": feature(
            identity_808,
            threshold=0.62,
            confidence=quality * (0.85 if drums is None else 1.0),
            estimator_quality=0.58,
            coverage=max(pitch_evidence_coverage, _clamp(len(events) / 6.0)),
            reliability_cap=0.68 if "spectral_peak_fallback" in pitch_methods else 1.0,
            sources=required_sources,
            time_ranges=_ranges(events, lambda item: item["sub_ratio_25_95_hz"] >= 0.42 and item["pitch_stability"] >= 0.55),
            evidence={
                **common,
                "sub_score": round(sub_score, 4),
                "pitch_stability_score": round(stability_score, 4),
                "harmonic_score": round(harmonic_score, 4),
                "sine_dominance_score": round(sine_dominance_score, 4),
                "sustain_score": round(sustain_score, 4),
                "kick_or_drum_transient_score": round(max(aligned_fraction, transient_score), 4),
                "mix_consistency_score": round(mix_consistency, 4),
                "semantic_rule": "candidate only: sub-dominant sustained body with fundamental-dominant timbre and compatible transient evidence",
            },
        ),
        "sliding_bass_candidate": feature(
            sliding_808,
            threshold=0.62,
            estimator_quality=min(0.65, pitch_estimator_quality),
            coverage=pitch_evidence_coverage,
            stability=pitch_track_quality,
            reliability_cap=pitch_reliability_cap,
            sources=required_sources,
            time_ranges=_ranges(slide_events, lambda item: True),
            evidence={
                **common,
                "sub_808_identity_score": round(identity_808, 4),
                "bass_slide_score": round(slide_score, 4),
                "voiced_event_coverage": round(pitch_evidence_coverage, 4),
                "semantic_rule": "requires sustained harmonic bass evidence and measured pitch motion",
            },
        ),
        "low_percussive_bass_candidate": feature(
            log_drum_score,
            threshold=0.62,
            estimator_quality=0.62,
            sources=["bass_stem", "drums_stem", "beat_grid"],
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
        "sustained_harmonic_bass_candidate": feature(
            sustained_harmonic_score,
            threshold=0.60,
            estimator_quality=0.68,
            sources=["bass_stem", "drums_stem"],
            time_ranges=_ranges(events, lambda item: item["pitch_stability"] >= 0.55 and item["decay_sec"] >= 0.20),
            evidence={
                **common,
                "sustain_score": round(sustain_score, 4),
                "harmonic_score": round(harmonic_score, 4),
                "semantic_rule": "pitched and sustained bass behaviour; does not imply an 808 timbre",
            },
        ),
        "low_frequency_melody": feature(
            melody_score,
            estimator_quality=pitch_estimator_quality,
            coverage=pitch_evidence_coverage,
            stability=sequence_quality,
            reliability_cap=pitch_reliability_cap,
            sources=["bass_stem"],
            evidence={
                **common,
                "event_pitch_range_semitones": round(pitch_range, 4),
                "meaningful_interval_fraction": round(meaningful_fraction, 4),
                "implausible_interval_fraction": round(implausible_fraction, 4),
                "pitch_diversity": round(pitch_diversity, 4),
                "voiced_event_coverage": round(pitch_evidence_coverage, 4),
                "semantic_rule": "repeated, plausible pitch movement across voiced bass events; range alone is insufficient",
            },
        ),
        "bass_reply_pattern": feature(
            reply_score,
            estimator_quality=0.70,
            sources=["bass_stem", "drums_stem", "beat_grid"],
            evidence={**common, "syncopation_score": round(syncopation, 4), "kick_separation_score": round(1.0 - aligned_fraction, 4)},
        ),
        "bass_syncopation": feature(
            float(groove["syncopation_score"]),
            estimator_quality=0.78,
            coverage=float(groove["placement_coverage"]),
            stability=_clamp(len(events) / 12.0),
            sources=["bass_stem", "beat_grid"],
            evidence={
                **common,
                "raw_syncopated_event_fraction": groove["raw_syncopated_event_fraction"],
                "sixteenth_steps_within_beat": groove["sixteenth_steps_within_beat"][:64],
                "mean_grid_offset_sec": groove["mean_grid_offset_sec"],
                "semantic_rule": "bass onset placement on the local sixteenth-note grid; weak sixteenths count more than eighth offbeats",
            },
        ) if len(beat_array) >= 2 else unavailable_feature(
            "beat_grid_unavailable", sources=["bass_stem", "beat_grid"], analysis_method=method,
        ),
        "bass_staccato_ratio": feature(
            float(groove["staccato_score"]),
            estimator_quality=0.70,
            coverage=_clamp(len(events) / 8.0),
            sources=["bass_stem"],
            time_ranges=_ranges(events, lambda item: item["decay_sec"] <= groove["staccato_limit_sec"]),
            evidence={
                **common,
                "staccato_fraction": groove["staccato_fraction"],
                "maximum_staccato_decay_sec": groove["staccato_limit_sec"],
                "semantic_rule": "short active bass envelopes relative to the measured beat period",
            },
        ),
        "bass_octave_pattern": feature(
            float(groove["octave_score"]),
            estimator_quality=pitch_estimator_quality,
            coverage=pitch_evidence_coverage,
            stability=_clamp(float(groove["pitched_interval_count"]) / 10.0),
            reliability_cap=pitch_reliability_cap,
            sources=["bass_stem"],
            evidence={
                **common,
                "octave_interval_fraction": groove["octave_interval_fraction"],
                "octave_interval_count": groove["octave_interval_count"],
                "pitched_interval_count": groove["pitched_interval_count"],
                "accepted_interval_semitones": [10.75, 13.25],
                "semantic_rule": "consecutive voiced bass notes separated by approximately one octave",
            },
        ),
        "bass_riff_repetition": feature(
            float(groove["riff_score"]),
            estimator_quality=pitch_estimator_quality,
            coverage=float(groove["bar_coverage"]),
            stability=_clamp(float(groove["bar_count"]) / 8.0),
            reliability_cap=pitch_reliability_cap,
            sources=["bass_stem", "downbeat_grid"],
            evidence={
                **common,
                "bar_count": groove["bar_count"],
                "bar_coverage": groove["bar_coverage"],
                "recurrence_by_lag_bars": groove["recurrence_by_lag_bars"],
                "semantic_rule": "beat-quantized relative-pitch pattern recurrence at one, two or four bars",
            },
        ) if len(downbeat_array) >= 3 else unavailable_feature(
            "downbeat_grid_unavailable", sources=["bass_stem", "downbeat_grid"], analysis_method=method,
        ),
        "bass_kick_interlock": feature(
            float(groove["interlock_score"]),
            estimator_quality=0.76,
            coverage=float(groove["kick_relation_coverage"]),
            stability=_clamp(len(events) / 12.0),
            sources=["bass_stem", "drums_stem", "beat_grid"],
            evidence={
                **common,
                "kick_event_count": len(kick_times),
                "kick_aligned_count": groove["kick_aligned_count"],
                "kick_complementary_count": groove["kick_complementary_count"],
                "kick_relation_coverage": groove["kick_relation_coverage"],
                "semantic_rule": "bass notes consistently alternate with nearby kicks; simple coincidence is retained by kick_bass_alignment",
            },
        ) if len(kick_times) and len(beat_array) >= 2 else unavailable_feature(
            "kick_or_beat_grid_unavailable", sources=["bass_stem", "drums_stem", "beat_grid"], analysis_method=method,
        ),
    }
    # Compatibility aliases remain readable for persisted v3 rules.  The v2
    # taxonomy migration consumes the canonical behaviour/candidate names.
    for legacy, canonical in {
        "sub_808": "808_timbre_candidate",
        "sliding_808": "sliding_bass_candidate",
        "log_drum": "low_percussive_bass_candidate",
        "log_drum_candidate": "low_percussive_bass_candidate",
    }.items():
        features[legacy] = {
            **features[canonical],
            "deprecated_alias_for": canonical,
        }
    return {
        "version": BASS_FEATURE_VERSION,
        "status": "ready" if quality >= 0.55 else "degraded",
        "features": features,
        "events": events,
        "confidence": round(quality, 4),
        "quality_flags": flags,
    }
