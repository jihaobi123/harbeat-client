"""Style-independent audio evidence required by high-frequency style analysis.

This module deliberately does not emit genre/style labels.  It converts the
existing beat/downbeat grid and Demucs stems into measurable evidence that a
later classifier can consume: rhythm grammar, low-frequency behaviour,
percussion timbre candidates, and whole-track sonic characteristics.

The named timbres are confidence-gated acoustic candidates, not claims of
ground-truth drum transcription.  Every output retains a score, confidence,
evidence, and candidate time ranges so it can be tested independently.
"""
from __future__ import annotations

from typing import Any

import librosa
import numpy as np


STYLE_FEATURE_VERSION = "pre_style_evidence_v2"
RHYTHM_FEATURES = (
    "four_on_floor", "backbeat_2_4", "halftime_snare_3", "tresillo",
    "dembow", "two_step", "swing", "shuffle", "hihat_roll", "ghost_notes",
)
LOW_FREQUENCY_FEATURES = (
    "sub_bass", "sub_808", "kick_bass_alignment", "sliding_808", "log_drum",
)
PERCUSSION_FEATURES = (
    "clap", "rim_snap", "closed_hihat", "open_hihat", "ride_crash",
    "shaker", "tambourine", "cowbell_clave", "tom", "conga_bongo",
    "general_percussion",
)
SONIC_FEATURES = (
    "brightness", "distortion", "lofi_texture", "harmonic_complexity",
    "acousticness", "synth_brightness",
)


def _clamp(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


def _ranges(values: list[float], width: float = 0.12, limit: int = 48) -> list[dict]:
    return [
        {"start": round(max(0.0, float(value) - 0.01), 4), "end": round(float(value) + width, 4)}
        for value in values[:limit]
    ]


def _feature(
    score: float,
    *,
    threshold: float = 0.55,
    evidence: dict[str, Any] | None = None,
    time_ranges: list[dict] | None = None,
    data_quality: float = 1.0,
) -> dict[str, Any]:
    score = _clamp(float(score))
    distance = min(1.0, abs(score - threshold) / max(threshold, 1.0 - threshold, 1e-6))
    confidence = _clamp((0.48 + 0.52 * distance) * _clamp(data_quality))
    return {
        "detected": bool(score >= threshold),
        "score": round(score, 4),
        "decision_threshold": round(float(threshold), 4),
        "confidence": round(confidence, 4),
        "time_ranges": list(time_ranges or []),
        "evidence": dict(evidence or {}),
    }


def empty_style_features(reason: str = "required_audio_unavailable") -> dict[str, Any]:
    unavailable = lambda: _feature(0.0, data_quality=0.0)  # noqa: E731
    return {
        "version": STYLE_FEATURE_VERSION,
        "status": "unavailable",
        "needs_review": True,
        "reason": reason,
        "rhythm_grammar": {name: unavailable() for name in RHYTHM_FEATURES},
        "low_frequency": {name: unavailable() for name in LOW_FREQUENCY_FEATURES},
        "percussion_timbre": {name: unavailable() for name in PERCUSSION_FEATURES},
        "sonic_profile": {name: unavailable() for name in SONIC_FEATURES},
        "confidence": {"overall": 0.0, "rhythm": 0.0, "low_frequency": 0.0, "percussion": 0.0, "sonic": 0.0},
        "quality_flags": [reason],
        "selected_models": [],
        "model_evidence": {"status": "unavailable", "routes": {}},
    }


def _points(values: list[float] | np.ndarray | None) -> np.ndarray:
    raw = np.asarray([] if values is None else values, dtype=float)
    return np.sort(raw[np.isfinite(raw) & (raw >= 0)])


def _event_times(drum_analysis: dict | None, name: str) -> np.ndarray:
    events = (drum_analysis or {}).get("events", {}).get(name, [])
    values = []
    for event in events:
        try:
            values.append(float(event.get("time", 0.0)))
        except (TypeError, ValueError, AttributeError):
            continue
    return _points(values)


def _bar_grid(
    downbeats: list[float] | np.ndarray | None,
    beat_points: list[float] | np.ndarray | None,
    bpm: float | None,
    duration: float,
) -> np.ndarray:
    bars = _points(downbeats)
    if len(bars) >= 2:
        return bars
    beats = _points(beat_points)
    if len(beats) >= 8:
        return beats[::4]
    if bpm and np.isfinite(bpm) and bpm > 0:
        return np.arange(0.0, duration, 240.0 / bpm)
    return np.asarray([], dtype=float)


def _step_bars(events: np.ndarray, bars: np.ndarray, bpm: float | None) -> list[set[int]]:
    if len(bars) < 2:
        return []
    expected = 240.0 / bpm if bpm and bpm > 0 else float(np.median(np.diff(bars)))
    result: list[set[int]] = []
    for start, end in zip(bars[:-1], bars[1:]):
        length = float(end - start)
        if length <= 0 or abs(length / expected - 1.0) > 0.22:
            continue
        steps = set()
        for event in events:
            step = int(round((float(event) - start) / length * 16))
            if 0 <= step < 16 and start - length / 32 <= event < end + length / 32:
                steps.add(step)
        result.append(steps)
    return result


def _template_score(step_bars: list[set[int]], targets: set[int]) -> tuple[float, list[int]]:
    if not step_bars or not targets:
        return 0.0, []
    scores = []
    matched_bars = []
    for index, steps in enumerate(step_bars):
        hits = len(steps & targets)
        recall = hits / len(targets)
        precision = hits / max(len(steps), 1)
        score = 0.72 * recall + 0.28 * precision
        scores.append(score)
        if score >= 0.60:
            matched_bars.append(index)
    return float(np.mean(scores)), matched_bars


def _bar_ranges(indices: list[int], bars: np.ndarray, limit: int = 32) -> list[dict]:
    out = []
    for index in indices[:limit]:
        if 0 <= index < len(bars) - 1:
            out.append({"start": round(float(bars[index]), 4), "end": round(float(bars[index + 1]), 4)})
    return out


def _rhythm_features(
    drum_analysis: dict | None,
    *,
    bpm: float | None,
    beat_points: list[float] | np.ndarray | None,
    downbeats: list[float] | np.ndarray | None,
    duration: float,
) -> tuple[dict[str, dict], float]:
    beats = _points(beat_points)
    bars = _bar_grid(downbeats, beat_points, bpm, duration)
    kick_times = _event_times(drum_analysis, "kick")
    snare_times = _event_times(drum_analysis, "snare")
    hat_times = _event_times(drum_analysis, "hihat")
    kick = _step_bars(kick_times, bars, bpm)
    snare = _step_bars(snare_times, bars, bpm)
    hats = _step_bars(hat_times, bars, bpm)
    analyzed = min(len(kick), len(snare), len(hats))
    quality = _clamp(analyzed / 16.0)

    four, four_bars = _template_score(kick, {0, 4, 8, 12})
    backbeat, backbeat_bars = _template_score(snare, {4, 12})
    halftime, halftime_bars = _template_score(snare, {8})
    tresillo_a, tresillo_a_bars = _template_score(hats, {0, 3, 6, 8, 11, 14})
    tresillo_b, tresillo_b_bars = _template_score(kick, {0, 3, 6, 8, 11, 14})
    tresillo = max(tresillo_a, tresillo_b)
    tresillo_bars = tresillo_a_bars if tresillo_a >= tresillo_b else tresillo_b_bars

    dembow_scores = []
    dembow_bars = []
    for index in range(analyzed):
        dancehall_k = len(kick[index] & {0, 3, 10}) / 3.0
        dancehall_s = len(snare[index] & {6, 12}) / 2.0
        moombahton_s = len(snare[index] & {3, 6, 11, 14}) / 4.0
        score = max(0.58 * dancehall_k + 0.42 * dancehall_s, moombahton_s)
        dembow_scores.append(score)
        if score >= 0.60:
            dembow_bars.append(index)
    dembow = float(np.mean(dembow_scores)) if dembow_scores else 0.0

    syncopated_kick = float(np.mean([
        sum(step % 4 != 0 for step in steps) / max(len(steps), 1) for steps in kick
    ])) if kick else 0.0
    two_step = _clamp(backbeat * 0.58 + syncopated_kick * 0.42 - four * 0.35)

    beat_interval = 60.0 / bpm if bpm and bpm > 0 else (float(np.median(np.diff(beats))) if len(beats) >= 2 else 0.0)
    offbeat_delays = []
    if beat_interval > 0 and len(beats) >= 2:
        for event in hat_times:
            prior_index = int(np.searchsorted(beats, event, side="right") - 1)
            if 0 <= prior_index < len(beats) - 1:
                interval = float(beats[prior_index + 1] - beats[prior_index])
                if interval <= 0:
                    continue
                phase = (event - beats[prior_index]) / interval
                if 0.35 <= phase <= 0.78:
                    offbeat_delays.append(float(phase - 0.5))
    mean_delay = float(np.median(offbeat_delays)) if offbeat_delays else 0.0
    delay_consistency = _clamp(1.0 - float(np.std(offbeat_delays)) / 0.12) if len(offbeat_delays) >= 3 else 0.0
    swing = _clamp(max(0.0, mean_delay - 0.025) / 0.14 * delay_consistency)
    shuffle = _clamp(swing * (0.55 + 0.45 * tresillo))

    hat_intervals = np.diff(hat_times)
    roll_threshold = beat_interval * 0.21 if beat_interval > 0 else 0.10
    roll_times = []
    if len(hat_intervals):
        for index in range(1, len(hat_intervals)):
            if hat_intervals[index - 1] <= roll_threshold and hat_intervals[index] <= roll_threshold:
                roll_times.append(float(hat_times[index]))
    expected_roll_opportunities = max(1.0, duration / 16.0)
    roll_score = _clamp(len(roll_times) / expected_roll_opportunities)

    snare_events = (drum_analysis or {}).get("events", {}).get("snare", [])
    ghost_times = []
    for event in snare_events:
        try:
            if float(event.get("velocity", 127)) <= 72 or float(event.get("confidence", 1.0)) <= 0.58:
                ghost_times.append(float(event["time"]))
        except (TypeError, ValueError, KeyError):
            continue
    ghost_score = _clamp(len(ghost_times) / max(len(snare_events) * 0.25, 1.0))

    evidence_base = {"bars_analyzed": analyzed, "resolution": 16}
    features = {
        "four_on_floor": _feature(four, evidence={**evidence_base, "target_steps": [0, 4, 8, 12]}, time_ranges=_bar_ranges(four_bars, bars), data_quality=quality),
        "backbeat_2_4": _feature(backbeat, evidence={**evidence_base, "target_steps": [4, 12]}, time_ranges=_bar_ranges(backbeat_bars, bars), data_quality=quality),
        "halftime_snare_3": _feature(halftime, evidence={**evidence_base, "target_steps": [8]}, time_ranges=_bar_ranges(halftime_bars, bars), data_quality=quality),
        "tresillo": _feature(tresillo, evidence={**evidence_base, "target_steps": [0, 3, 6, 8, 11, 14]}, time_ranges=_bar_ranges(tresillo_bars, bars), data_quality=quality),
        "dembow": _feature(dembow, evidence={**evidence_base, "kick_template": [0, 3, 10], "snare_templates": [[6, 12], [3, 6, 11, 14]]}, time_ranges=_bar_ranges(dembow_bars, bars), data_quality=quality),
        "two_step": _feature(two_step, evidence={**evidence_base, "backbeat_score": round(backbeat, 4), "kick_syncopation": round(syncopated_kick, 4), "four_on_floor_score": round(four, 4)}, data_quality=quality),
        "swing": _feature(swing, evidence={"median_offbeat_delay_beats": round(mean_delay, 4), "offbeats_analyzed": len(offbeat_delays)}, data_quality=_clamp(len(offbeat_delays) / 12.0)),
        "shuffle": _feature(shuffle, evidence={"swing_score": round(swing, 4), "tresillo_score": round(tresillo, 4)}, data_quality=_clamp(len(offbeat_delays) / 12.0)),
        "hihat_roll": _feature(roll_score, evidence={"roll_cluster_count": len(roll_times), "maximum_interval_sec": round(roll_threshold, 4)}, time_ranges=_ranges(roll_times), data_quality=_clamp(len(hat_times) / 24.0)),
        "ghost_notes": _feature(ghost_score, evidence={"low_strength_snare_count": len(ghost_times), "snare_count": len(snare_events)}, time_ranges=_ranges(ghost_times), data_quality=_clamp(len(snare_events) / 12.0)),
    }
    return features, quality


def _band_ratio(audio: np.ndarray, sr: int, low: float, high: float) -> float:
    if audio is None or len(audio) < 32:
        return 0.0
    spectrum = np.abs(np.fft.rfft(np.asarray(audio, dtype=float))) ** 2
    frequencies = np.fft.rfftfreq(len(audio), 1.0 / sr)
    total = float(np.sum(spectrum)) + 1e-12
    return float(np.sum(spectrum[(frequencies >= low) & (frequencies < high)]) / total)


def _onset_times(audio: np.ndarray, sr: int) -> np.ndarray:
    if audio is None or len(audio) < sr // 2:
        return np.asarray([], dtype=float)
    envelope = librosa.onset.onset_strength(y=np.asarray(audio, dtype=float), sr=sr, hop_length=256)
    frames = librosa.onset.onset_detect(onset_envelope=envelope, sr=sr, hop_length=256, backtrack=False, units="frames")
    return librosa.frames_to_time(frames, sr=sr, hop_length=256)


def _nearest_fraction(values: np.ndarray, references: np.ndarray, tolerance: float) -> float:
    if not len(values) or not len(references):
        return 0.0
    return sum(float(np.min(np.abs(references - value))) <= tolerance for value in values) / len(values)


def _pitch_motion_ranges(audio: np.ndarray, sr: int) -> tuple[list[dict], dict[str, float]]:
    if audio is None or len(audio) < sr:
        return [], {"voiced_fraction": 0.0, "maximum_motion_semitones": 0.0}
    hop = 512
    n_fft = 4096
    spectrum = np.abs(librosa.stft(np.asarray(audio, dtype=float), n_fft=n_fft, hop_length=hop))
    frequencies = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    mask = (frequencies >= 30.0) & (frequencies <= 260.0)
    low = spectrum[mask]
    if not low.size:
        return [], {"voiced_fraction": 0.0, "maximum_motion_semitones": 0.0}
    indices = np.argmax(low, axis=0)
    pitch = frequencies[mask][indices]
    strength = np.max(low, axis=0)
    gate = float(np.percentile(strength, 55))
    voiced = strength >= max(gate, 1e-8)
    midi = 69.0 + 12.0 * np.log2(np.maximum(pitch, 1e-6) / 440.0)
    ranges = []
    maximum_motion = 0.0
    window = max(10, int(round(0.35 * sr / hop)))
    for start in range(0, max(0, len(midi) - window), max(2, window // 3)):
        end = start + window
        valid = voiced[start:end]
        if np.mean(valid) < 0.72:
            continue
        values = midi[start:end][valid]
        if len(values) < 6:
            continue
        motion = float(values[-1] - values[0])
        maximum_motion = max(maximum_motion, abs(motion))
        diffs = np.diff(values)
        monotonic = max(float(np.mean(diffs >= -0.20)), float(np.mean(diffs <= 0.20)))
        if abs(motion) >= 2.5 and monotonic >= 0.72:
            ranges.append({
                "start": round(start * hop / sr, 4),
                "end": round(end * hop / sr, 4),
                "motion_semitones": round(motion, 3),
            })
    merged = []
    for item in ranges:
        if merged and item["start"] <= merged[-1]["end"] + 0.08:
            merged[-1]["end"] = max(merged[-1]["end"], item["end"])
            if abs(item["motion_semitones"]) > abs(merged[-1]["motion_semitones"]):
                merged[-1]["motion_semitones"] = item["motion_semitones"]
        else:
            merged.append(dict(item))
    return merged[:48], {
        "voiced_fraction": round(float(np.mean(voiced)), 4),
        "maximum_motion_semitones": round(maximum_motion, 4),
    }


def _low_frequency_features(
    bass: np.ndarray | None,
    drums: np.ndarray | None,
    sr: int,
    drum_analysis: dict | None,
    beat_points: list[float] | np.ndarray | None,
    duration: float,
) -> tuple[dict[str, dict], float]:
    if bass is None or len(bass) < sr:
        return {name: _feature(0.0, data_quality=0.0) for name in LOW_FREQUENCY_FEATURES}, 0.0
    bass = np.asarray(bass, dtype=float)
    sub_ratio = _band_ratio(bass, sr, 20.0, 100.0)
    low_ratio = _band_ratio(bass, sr, 20.0, 180.0)
    bass_onsets = _onset_times(bass, sr)
    kick_times = _event_times(drum_analysis, "kick")
    alignment = _nearest_fraction(bass_onsets, kick_times, 0.085)
    rms = librosa.feature.rms(y=bass, frame_length=1024, hop_length=256)[0]
    active = rms > max(float(np.percentile(rms, 60)), 1e-7)
    sustain = float(np.mean(active))
    crest = float(np.max(np.abs(bass)) / (np.sqrt(np.mean(np.square(bass))) + 1e-8))
    sustain_score = _clamp((sustain - 0.12) / 0.45)
    sub_score = _clamp(sub_ratio / 0.72)
    sub_808 = _clamp(0.52 * sub_score + 0.28 * sustain_score + 0.20 * alignment)

    motion_ranges, motion_evidence = _pitch_motion_ranges(bass, sr)
    slide_score = _clamp(len(motion_ranges) / max(1.0, duration / 45.0))

    beats = _points(beat_points)
    syncopation = 0.0
    if len(beats) >= 2 and len(bass_onsets):
        interval = float(np.median(np.diff(beats)))
        aligned_beats = _nearest_fraction(bass_onsets, beats, max(0.055, interval * 0.12))
        syncopation = 1.0 - aligned_beats
    onset_density = len(bass_onsets) / max(duration, 1.0)
    percussive_density = _clamp(onset_density / 2.2)
    log_drum = _clamp(0.30 * sub_score + 0.30 * percussive_density + 0.27 * syncopation + 0.13 * (1.0 - alignment) - 0.12 * slide_score)
    quality = _clamp(duration / 30.0)
    onset_ranges = _ranges(bass_onsets.tolist(), width=0.18)
    features = {
        "sub_bass": _feature(sub_score, evidence={"energy_ratio_20_100_hz": round(sub_ratio, 4), "energy_ratio_20_180_hz": round(low_ratio, 4)}, data_quality=quality),
        "sub_808": _feature(sub_808, evidence={"sub_score": round(sub_score, 4), "sustain_score": round(sustain_score, 4), "kick_alignment": round(alignment, 4), "crest_factor": round(crest, 4)}, data_quality=quality),
        "kick_bass_alignment": _feature(alignment, evidence={"bass_onsets": len(bass_onsets), "kick_candidates": len(kick_times), "tolerance_sec": 0.085}, time_ranges=onset_ranges, data_quality=quality),
        "sliding_808": _feature(slide_score, evidence={**motion_evidence, "motion_range_count": len(motion_ranges)}, time_ranges=motion_ranges, data_quality=quality),
        "log_drum": _feature(log_drum, evidence={"sub_score": round(sub_score, 4), "onsets_per_second": round(onset_density, 4), "syncopation": round(syncopation, 4), "kick_alignment": round(alignment, 4)}, time_ranges=onset_ranges, data_quality=quality),
    }
    return features, quality


def _descriptor(audio: np.ndarray, sr: int, time_sec: float) -> dict[str, float]:
    start = max(0, int((time_sec - 0.006) * sr))
    end = min(len(audio), start + int(0.38 * sr))
    clip = np.asarray(audio[start:end], dtype=float)
    if len(clip) < 64:
        return {}
    attack_end = min(len(clip), int(0.09 * sr))
    attack = clip[:attack_end] * np.hanning(max(attack_end, 1))
    magnitude = np.abs(np.fft.rfft(attack)) + 1e-12
    frequencies = np.fft.rfftfreq(len(attack), 1.0 / sr)
    power = magnitude ** 2
    total = float(np.sum(power)) + 1e-12
    centroid = float(np.sum(frequencies * power) / total)
    dominant = float(frequencies[int(np.argmax(power))])
    flatness = float(np.exp(np.mean(np.log(magnitude))) / np.mean(magnitude))
    prominence = float(np.max(magnitude) / (np.mean(magnitude) + 1e-12))
    early = float(np.sqrt(np.mean(np.square(clip[:min(len(clip), int(0.055 * sr))])))) + 1e-9
    late_start = min(len(clip), int(0.09 * sr))
    late_end = min(len(clip), int(0.30 * sr))
    late = float(np.sqrt(np.mean(np.square(clip[late_start:late_end])))) if late_end > late_start else 0.0
    envelope = librosa.feature.rms(y=clip, frame_length=min(512, max(64, len(clip))), hop_length=128, center=False)[0]
    peak = float(np.max(envelope)) if len(envelope) else 0.0
    active_frames = np.where(envelope >= peak * 0.20)[0] if peak > 0 else np.asarray([])
    decay = float((active_frames[-1] + 1) * 128 / sr) if len(active_frames) else 0.0
    return {
        "centroid": centroid,
        "dominant_frequency": dominant,
        "flatness": flatness,
        "prominence": prominence,
        "decay_sec": decay,
        "late_early_ratio": late / early,
        "low_ratio": float(np.sum(power[(frequencies >= 35) & (frequencies < 220)]) / total),
        "mid_ratio": float(np.sum(power[(frequencies >= 220) & (frequencies < 4000)]) / total),
        "high_ratio": float(np.sum(power[frequencies >= 4000]) / total),
    }


def _candidate_score(count: int, total: int, target_fraction: float = 0.18) -> float:
    return _clamp(count / max(total * target_fraction, 1.0))


def _percussion_features(
    drums: np.ndarray | None,
    sr: int,
    drum_analysis: dict | None,
    duration: float,
) -> tuple[dict[str, dict], float]:
    if drums is None or len(drums) < sr:
        return {name: _feature(0.0, data_quality=0.0) for name in PERCUSSION_FEATURES}, 0.0
    drums = np.asarray(drums, dtype=float)
    classified = {name: [] for name in PERCUSSION_FEATURES}
    snare_times = _event_times(drum_analysis, "snare").tolist()
    hat_times = _event_times(drum_analysis, "hihat").tolist()
    kick_times = _event_times(drum_analysis, "kick").tolist()
    all_onsets = _onset_times(drums, sr).tolist()

    for value in snare_times[:600]:
        desc = _descriptor(drums, sr, value)
        if not desc:
            continue
        if desc["decay_sec"] <= 0.075 and desc["centroid"] >= 2200 and desc["prominence"] >= 8:
            classified["rim_snap"].append(value)
        elif desc["centroid"] >= 1700 and desc["flatness"] >= 0.12 and desc["high_ratio"] >= 0.12:
            classified["clap"].append(value)

    open_hat_descriptors = []
    for value in hat_times[:900]:
        desc = _descriptor(drums, sr, value)
        if not desc:
            continue
        if desc["decay_sec"] >= 0.14 or desc["late_early_ratio"] >= 0.24:
            classified["open_hihat"].append(value)
            open_hat_descriptors.append(desc)
        else:
            classified["closed_hihat"].append(value)
        if desc["decay_sec"] >= 0.30 and desc["high_ratio"] >= 0.16:
            classified["ride_crash"].append(value)

    for value in kick_times[:600]:
        desc = _descriptor(drums, sr, value)
        if desc and 95 <= desc["dominant_frequency"] <= 330 and desc["decay_sec"] >= 0.09:
            classified["tom"].append(value)

    known = np.asarray(snare_times + hat_times + kick_times, dtype=float)
    unassigned = [
        value for value in all_onsets[:1200]
        if not len(known) or float(np.min(np.abs(known - value))) > 0.045
    ]
    for value in unassigned:
        desc = _descriptor(drums, sr, value)
        if not desc:
            continue
        tonal = desc["prominence"] >= 12 and desc["flatness"] <= 0.16
        if tonal and 500 <= desc["dominant_frequency"] <= 2600 and desc["decay_sec"] <= 0.32:
            classified["cowbell_clave"].append(value)
        elif tonal and 160 <= desc["dominant_frequency"] < 800 and desc["decay_sec"] >= 0.07:
            classified["conga_bongo"].append(value)
        elif desc["high_ratio"] >= 0.30 and 0.08 <= desc["decay_sec"] <= 0.32:
            classified["tambourine"].append(value)
        else:
            classified["general_percussion"].append(value)

    hat_rate = len(hat_times) / max(duration, 1.0)
    hat_events = (drum_analysis or {}).get("events", {}).get("hihat", [])
    median_hat_velocity = float(np.median([float(event.get("velocity", 100)) for event in hat_events])) if hat_events else 127.0
    shaker_score = _clamp(0.62 * _clamp(hat_rate / 5.0) + 0.38 * _clamp((105.0 - median_hat_velocity) / 50.0))
    if shaker_score >= 0.55:
        classified["shaker"] = hat_times

    total = max(len(all_onsets), 1)
    quality = _clamp(total / max(duration * 1.2, 24.0))
    thresholds = {
        "clap": 0.45, "rim_snap": 0.45, "closed_hihat": 0.40,
        "open_hihat": 0.45, "ride_crash": 0.45, "shaker": 0.55,
        "tambourine": 0.45, "cowbell_clave": 0.45, "tom": 0.45,
        "conga_bongo": 0.45, "general_percussion": 0.40,
    }
    features = {}
    for name in PERCUSSION_FEATURES:
        values = classified[name]
        if name == "shaker":
            score = shaker_score
        elif name in {"closed_hihat", "open_hihat", "ride_crash"}:
            score = _candidate_score(len(values), max(len(hat_times), 1), 0.20)
        elif name in {"clap", "rim_snap"}:
            score = _candidate_score(len(values), max(len(snare_times), 1), 0.18)
        elif name == "tom":
            score = _candidate_score(len(values), max(len(kick_times), 1), 0.15)
        else:
            score = _candidate_score(len(values), max(len(unassigned), 1), 0.16)
        features[name] = _feature(
            score,
            threshold=thresholds[name],
            evidence={"candidate_count": len(values), "comparison_count": total, "detector": "spectral_decay_proxy_v1"},
            time_ranges=_ranges(values),
            data_quality=quality,
        )
    return features, quality


def _sonic_features(audio: np.ndarray | None, other: np.ndarray | None, sr: int) -> tuple[dict[str, dict], float]:
    source = audio if audio is not None and len(audio) >= sr else other
    if source is None or len(source) < sr:
        return {name: _feature(0.0, data_quality=0.0) for name in SONIC_FEATURES}, 0.0
    source = np.asarray(source, dtype=float)
    max_samples = sr * 60
    if len(source) > max_samples:
        start = (len(source) - max_samples) // 2
        source = source[start:start + max_samples]
    spectrum = np.abs(librosa.stft(source, n_fft=2048, hop_length=512)) + 1e-10
    centroid = float(np.mean(librosa.feature.spectral_centroid(S=spectrum, sr=sr)))
    rolloff = float(np.mean(librosa.feature.spectral_rolloff(S=spectrum, sr=sr, roll_percent=0.85)))
    flatness = float(np.mean(librosa.feature.spectral_flatness(S=spectrum)))
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(source)))
    crest = float(np.max(np.abs(source)) / (np.sqrt(np.mean(np.square(source))) + 1e-8))
    brightness = _clamp((centroid - 900.0) / 3300.0)
    distortion = _clamp(0.45 * _clamp(flatness / 0.18) + 0.35 * _clamp((4.5 - crest) / 3.2) + 0.20 * _clamp(zcr / 0.18))
    lofi = _clamp(0.48 * (1.0 - _clamp(rolloff / 8500.0)) + 0.27 * _clamp(flatness / 0.16) + 0.25 * _clamp(zcr / 0.16))

    harmonic, percussive = librosa.effects.hpss(source)
    harmonic_ratio = float(np.sqrt(np.mean(np.square(harmonic))) / (np.sqrt(np.mean(np.square(source))) + 1e-8))
    chroma = librosa.feature.chroma_stft(y=harmonic, sr=sr, n_fft=4096, hop_length=1024)
    chroma_norm = chroma / (np.sum(chroma, axis=0, keepdims=True) + 1e-10)
    entropy = -np.sum(chroma_norm * np.log2(chroma_norm + 1e-10), axis=0) / np.log2(12.0)
    harmonic_complexity = _clamp(float(np.mean(entropy)))
    acousticness = _clamp(0.56 * harmonic_ratio + 0.24 * (1.0 - _clamp(flatness / 0.20)) + 0.20 * (1.0 - distortion))

    synth_source = np.asarray(other, dtype=float) if other is not None and len(other) >= sr else source
    synth_centroid = float(np.mean(librosa.feature.spectral_centroid(y=synth_source, sr=sr)))
    synth_flatness = float(np.mean(librosa.feature.spectral_flatness(y=synth_source)))
    synth_brightness = _clamp(0.72 * _clamp((synth_centroid - 1300.0) / 3500.0) + 0.28 * _clamp(synth_flatness / 0.20))
    quality = _clamp(len(source) / (sr * 20.0))
    evidence = {"spectral_centroid_hz": round(centroid, 3), "rolloff_hz": round(rolloff, 3), "spectral_flatness": round(flatness, 5), "zero_crossing_rate": round(zcr, 5), "crest_factor": round(crest, 4)}
    return {
        "brightness": _feature(brightness, evidence=evidence, data_quality=quality),
        "distortion": _feature(distortion, evidence=evidence, data_quality=quality),
        "lofi_texture": _feature(lofi, evidence=evidence, data_quality=quality),
        "harmonic_complexity": _feature(harmonic_complexity, evidence={"chroma_entropy": round(harmonic_complexity, 4), "harmonic_ratio": round(harmonic_ratio, 4)}, data_quality=quality),
        "acousticness": _feature(acousticness, evidence={"harmonic_ratio": round(harmonic_ratio, 4), "spectral_flatness": round(flatness, 5), "distortion_score": round(distortion, 4)}, data_quality=quality),
        "synth_brightness": _feature(synth_brightness, evidence={"other_centroid_hz": round(synth_centroid, 3), "other_flatness": round(synth_flatness, 5)}, data_quality=quality),
    }, quality


def _route_result(model_evidence: dict | None, name: str) -> tuple[dict, dict]:
    route = ((model_evidence or {}).get("routes") or {}).get(name) or {}
    result = route.get("result") if route.get("status") == "ready" else {}
    return route, result if isinstance(result, dict) else {}


def _tag_scores(payload: dict) -> tuple[dict[str, float], dict[str, list[dict]]]:
    """Accept common YAMNet/PANNs worker output forms."""
    raw = payload.get("tags", payload.get("predictions", {}))
    scores: dict[str, float] = {}
    ranges: dict[str, list[dict]] = {}
    if isinstance(raw, dict):
        iterable = [{"label": label, "score": score} for label, score in raw.items()]
    elif isinstance(raw, list):
        iterable = raw
    else:
        iterable = []
    for item in iterable:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", item.get("name", ""))).strip().lower().replace("_", " ")
        try:
            score = float(item.get("score", item.get("confidence", 0.0)))
        except (TypeError, ValueError):
            continue
        if not label:
            continue
        scores[label] = max(scores.get(label, 0.0), _clamp(score))
        if "start" in item and "end" in item:
            try:
                ranges.setdefault(label, []).append({
                    "start": round(float(item["start"]), 4),
                    "end": round(float(item["end"]), 4),
                })
            except (TypeError, ValueError):
                pass
    return scores, ranges


def _best_tag(scores: dict[str, float], labels: tuple[str, ...]) -> tuple[float, str | None]:
    candidates = [(scores.get(label, 0.0), label) for label in labels]
    score, label = max(candidates, default=(0.0, None))
    return float(score), label if score > 0 else None


def _mature_event_feature(
    events: list,
    *,
    engine: str,
    threshold: float = 0.45,
) -> dict:
    normalized = []
    confidences = []
    for value in events:
        event = value if isinstance(value, dict) else {"time": value}
        try:
            timestamp = float(event["time"])
            confidence = _clamp(float(event.get("confidence", event.get("probability", 0.75))))
        except (KeyError, TypeError, ValueError):
            continue
        normalized.append(timestamp)
        confidences.append(confidence)
    score = float(np.mean(confidences)) if confidences else 0.0
    return _feature(
        score,
        threshold=threshold,
        evidence={"source_type": "mature_model", "engine": engine, "event_count": len(normalized)},
        time_ranges=_ranges(normalized),
        data_quality=1.0,
    )


def _apply_mature_model_evidence(
    rhythm: dict[str, dict],
    low: dict[str, dict],
    percussion: dict[str, dict],
    sonic: dict[str, dict],
    *,
    model_evidence: dict | None,
    duration: float,
) -> list[str]:
    """Prefer dedicated model evidence while retaining explicit fallbacks."""
    selected: list[str] = []
    pitch_route, pitch = _route_result(model_evidence, "bass_pitch")
    notes_route, notes = _route_result(model_evidence, "bass_notes")
    pitch_slides = pitch.get("slide_ranges") if isinstance(pitch.get("slide_ranges"), list) else []
    bend_count = int(notes.get("pitch_bend_note_count", 0) or 0)
    note_count = int(notes.get("note_count", 0) or 0)
    if pitch_route.get("status") == "ready" or notes_route.get("status") == "ready":
        pitch_score = _clamp(len(pitch_slides) / max(duration / 45.0, 1.0))
        bend_score = _clamp(bend_count / max(note_count * 0.12, 1.0))
        available_scores = []
        if pitch_route.get("status") == "ready":
            available_scores.append(pitch_score)
        if notes_route.get("status") == "ready":
            available_scores.append(bend_score)
        consensus = float(np.mean(available_scores)) if available_scores else 0.0
        ranges = list(pitch_slides)
        low["sliding_808"] = _feature(
            consensus,
            evidence={
                "source_type": "mature_model_consensus",
                "engines": [
                    route.get("engine") for route in (pitch_route, notes_route)
                    if route.get("status") == "ready"
                ],
                "crepe_slide_count": len(pitch_slides),
                "basic_pitch_bend_notes": bend_count,
                "basic_pitch_note_count": note_count,
                "semantic_note": "detects bass slides; 808 identity requires timbre evidence",
            },
            time_ranges=ranges,
            data_quality=1.0,
        )
        selected.extend([
            route.get("engine") for route in (pitch_route, notes_route)
            if route.get("status") == "ready" and route.get("engine")
        ])

    drum_route, drum = _route_result(model_evidence, "drum_transcription")
    drum_events = drum.get("events") if isinstance(drum.get("events"), dict) else {}
    drum_engine = str(drum.get("engine") or drum_route.get("engine") or "dedicated_drum_model")
    if drum_events:
        direct_event_mapping = {
            "clap": ("clap", "hand_clap"),
            "rim_snap": ("rim", "rimshot", "snap", "finger_snap"),
            "closed_hihat": ("closed_hihat", "closed_hi_hat"),
            "open_hihat": ("open_hihat", "open_hi_hat"),
            "ride_crash": ("cymbal", "cymbals", "ride", "crash", "ride_cymbal", "crash_cymbal"),
            "shaker": ("shaker", "maraca"),
            "tambourine": ("tambourine",),
            "cowbell_clave": ("cowbell", "clave", "wood_block"),
            "tom": ("tom", "toms"),
            "conga_bongo": ("conga", "bongo", "conga_bongo"),
            "general_percussion": ("percussion",),
        }
        for feature_name, event_names in direct_event_mapping.items():
            values = []
            for event_name in event_names:
                raw_values = drum_events.get(event_name, [])
                if isinstance(raw_values, list):
                    values.extend(raw_values)
            if values:
                percussion[feature_name] = _mature_event_feature(values, engine=drum_engine)
        selected.append(drum_engine)

    tag_route, tag_payload = _route_result(model_evidence, "audio_tags")
    scores, tag_ranges = _tag_scores(tag_payload)
    if scores:
        mapping = {
            "clap": ("clapping", "clap", "hand clap"),
            "rim_snap": ("rimshot", "finger snapping", "snap"),
            "closed_hihat": ("hi-hat", "closed hi-hat"),
            "open_hihat": ("open hi-hat",),
            "ride_crash": ("cymbal", "ride cymbal", "crash cymbal"),
            "shaker": ("rattle", "rattle (instrument)", "maraca", "shaker"),
            "tambourine": ("tambourine",),
            "cowbell_clave": ("cowbell", "clave", "wood block"),
            "conga_bongo": ("bongo", "conga"),
            "general_percussion": ("percussion",),
        }
        for feature_name, labels in mapping.items():
            score, label = _best_tag(scores, labels)
            if label is None:
                continue
            percussion[feature_name] = _feature(
                score,
                threshold=0.30,
                evidence={
                    "source_type": "mature_audio_tagger",
                    "engine": tag_route.get("engine"),
                    "matched_label": label,
                },
                time_ranges=tag_ranges.get(label, []),
                data_quality=1.0,
            )
        roll_score, roll_label = _best_tag(scores, ("drum roll",))
        if roll_label is not None:
            rhythm["hihat_roll"] = _feature(
                roll_score,
                threshold=0.30,
                evidence={
                    "source_type": "mature_audio_tagger",
                    "engine": tag_route.get("engine"),
                    "matched_label": roll_label,
                    "semantic_note": "general drum roll; hi-hat identity requires drum-stem evidence",
                },
                time_ranges=tag_ranges.get(roll_label, []),
                data_quality=1.0,
            )
        acoustic_score, acoustic_label = _best_tag(scores, ("acoustic music", "acoustic guitar", "piano"))
        electronic_score, electronic_label = _best_tag(scores, ("electronic music", "synthesizer", "drum machine"))
        if acoustic_label or electronic_label:
            probability = _clamp(acoustic_score / max(acoustic_score + electronic_score, 1e-8))
            sonic["acousticness"] = _feature(
                probability,
                evidence={
                    "source_type": "mature_audio_tagger",
                    "engine": tag_route.get("engine"),
                    "acoustic_label": acoustic_label,
                    "electronic_label": electronic_label,
                },
                data_quality=1.0,
            )
        if tag_route.get("engine"):
            selected.append(str(tag_route["engine"]))
    semantic_features = tag_payload.get("features") if isinstance(tag_payload.get("features"), dict) else {}
    sonic_aliases = {
        "brightness": ("brightness", "bright"),
        "distortion": ("distortion", "distorted"),
        "lofi_texture": ("lofi_texture", "lofi", "lo_fi"),
        "harmonic_complexity": ("harmonic_complexity",),
        "acousticness": ("acousticness", "acoustic"),
        "synth_brightness": ("synth_brightness",),
    }
    semantic_model_used = False
    for feature_name, aliases in sonic_aliases.items():
        raw_score = next((semantic_features[name] for name in aliases if name in semantic_features), None)
        if raw_score is None:
            continue
        try:
            score = _clamp(float(raw_score))
        except (TypeError, ValueError):
            continue
        sonic[feature_name] = _feature(
            score,
            evidence={
                "source_type": "mature_audio_model",
                "engine": tag_route.get("engine"),
                "feature_name": next(name for name in aliases if name in semantic_features),
            },
            data_quality=1.0,
        )
        semantic_model_used = True
    if semantic_model_used and tag_route.get("engine"):
        selected.append(str(tag_route["engine"]))
    return list(dict.fromkeys(selected))


def analyze_style_features(
    stems: dict[str, np.ndarray] | None,
    sr: int,
    *,
    bpm: float | None = None,
    beat_points: list[float] | np.ndarray | None = None,
    downbeats: list[float] | np.ndarray | None = None,
    drum_analysis: dict | None = None,
    original_audio: np.ndarray | None = None,
    model_evidence: dict | None = None,
) -> dict[str, Any]:
    """Extract style-independent evidence from existing pre-processing outputs."""
    stems = stems or {}
    arrays = {
        name: np.asarray(value, dtype=np.float32) if value is not None else None
        for name, value in stems.items()
    }
    candidates = [value for value in arrays.values() if value is not None and len(value)]
    if sr <= 0 or not candidates:
        return empty_style_features()
    duration = max(len(value) for value in candidates) / sr
    target_sr = 22050
    if sr != target_sr:
        for name, value in list(arrays.items()):
            if value is not None and len(value):
                arrays[name] = librosa.resample(value, orig_sr=sr, target_sr=target_sr)
        if original_audio is not None and len(original_audio):
            original_audio = librosa.resample(np.asarray(original_audio, dtype=float), orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    if original_audio is None and candidates:
        lengths = [len(value) for value in arrays.values() if value is not None and len(value)]
        if lengths:
            length = min(lengths)
            original_audio = sum(value[:length] for value in arrays.values() if value is not None and len(value))

    rhythm, rhythm_quality = _rhythm_features(
        drum_analysis,
        bpm=bpm,
        beat_points=beat_points,
        downbeats=downbeats,
        duration=duration,
    )
    low, low_quality = _low_frequency_features(
        arrays.get("bass"), arrays.get("drums"), sr, drum_analysis, beat_points, duration,
    )
    percussion, percussion_quality = _percussion_features(arrays.get("drums"), sr, drum_analysis, duration)
    sonic, sonic_quality = _sonic_features(original_audio, arrays.get("other"), sr)
    selected_models = _apply_mature_model_evidence(
        rhythm,
        low,
        percussion,
        sonic,
        model_evidence=model_evidence,
        duration=duration,
    )
    qualities = [rhythm_quality, low_quality, percussion_quality, sonic_quality]
    overall = float(np.mean(qualities))
    flags = []
    if rhythm_quality < 0.55:
        flags.append("insufficient_bar_aligned_drum_events")
    if low_quality == 0:
        flags.append("bass_stem_unavailable")
    if percussion_quality == 0:
        flags.append("drums_stem_unavailable")
    if sonic_quality == 0:
        flags.append("sonic_audio_unavailable")
    if overall < 0.55:
        flags.append("low_overall_confidence")
    if not selected_models:
        flags.append("mature_models_unavailable_using_dsp_fallbacks")
    return {
        "version": STYLE_FEATURE_VERSION,
        "status": "ready" if overall >= 0.55 else "degraded",
        "needs_review": bool(flags),
        "reason": None,
        "rhythm_grammar": rhythm,
        "low_frequency": low,
        "percussion_timbre": percussion,
        "sonic_profile": sonic,
        "confidence": {
            "overall": round(overall, 4),
            "rhythm": round(rhythm_quality, 4),
            "low_frequency": round(low_quality, 4),
            "percussion": round(percussion_quality, 4),
            "sonic": round(sonic_quality, 4),
        },
        "quality_flags": flags,
        "selected_models": selected_models,
        "model_evidence": model_evidence or {
            "status": "unavailable",
            "routes": {},
        },
    }
