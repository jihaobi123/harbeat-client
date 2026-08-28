"""Mature-model-first drum transcription for DJ-oriented metadata.

The analyzer expects an isolated Demucs ``drums`` stem.  A normalized result
from ADTOF, Omnizart, or another dedicated transcriber is preferred.  The
existing spectral detector remains an explicit fallback so deployments keep
working while model workers are offline.
"""
from __future__ import annotations

from typing import Any

import librosa
import numpy as np


DRUM_ANALYSIS_VERSION = "drum_transcription_consensus_v3"
DRUM_CLASSES = ("kick", "snare", "hihat", "tom", "cymbal")
CORE_DRUM_CLASSES = ("kick", "snare", "hihat")


def empty_drum_analysis(reason: str = "drums_stem_unavailable") -> dict[str, Any]:
    return {
        "version": DRUM_ANALYSIS_VERSION,
        "source": "demucs_drums_stem",
        "status": "unavailable",
        "needs_review": True,
        "reason": reason,
        "events": {name: [] for name in DRUM_CLASSES},
        "counts": {name: 0 for name in DRUM_CLASSES},
        "density_curve": [],
        "pattern": {
            "resolution": 16,
            "bars_analyzed": 0,
            "dominant": None,
            "stability": 0.0,
            "syncopation": 0.0,
        },
        "fills": [],
        "metrical_alignment": {
            "grid_type": None,
            "subdivision_alignment": 0.0,
            "phase_consistency": 0.0,
            "timing_deviation_ms": None,
            "metrical_level_reliability": 0.0,
            "candidates": {},
        },
        "confidence": {"overall": 0.0, **{name: 0.0 for name in DRUM_CLASSES}},
        "quality_flags": [reason],
        "engine_routes": {},
    }


def _normalized_model_events(model_route: dict[str, Any] | None) -> tuple[dict[str, list[dict]], str] | None:
    """Validate the shared JSON worker contract without trusting its payload."""
    if not model_route or model_route.get("status") != "ready":
        return None
    payload = model_route.get("result") or {}
    raw_events = payload.get("events")
    if not isinstance(raw_events, dict):
        return None
    aliases = {
        "bd": "kick", "bass_drum": "kick", "kick_drum": "kick",
        "sd": "snare", "snare_drum": "snare",
        "hh": "hihat", "hi_hat": "hihat", "closed_hihat": "hihat", "open_hihat": "hihat",
        "toms": "tom", "ride": "cymbal", "crash": "cymbal", "cymbals": "cymbal",
    }
    normalized = {name: [] for name in DRUM_CLASSES}
    for raw_name, values in raw_events.items():
        raw_family = str(raw_name).strip().lower()
        name = aliases.get(raw_family, raw_family)
        if name not in normalized or not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, (int, float)):
                event = {"time": value}
            elif isinstance(value, dict):
                event = value
            else:
                continue
            try:
                timestamp = float(event["time"])
                confidence = float(event.get("confidence", event.get("probability", 0.75)))
            except (KeyError, TypeError, ValueError):
                continue
            if timestamp < 0 or not np.isfinite(timestamp):
                continue
            raw_velocity = event.get("velocity")
            try:
                velocity = int(np.clip(round(float(raw_velocity)), 1, 127)) if raw_velocity is not None else None
            except (TypeError, ValueError):
                velocity = None
            normalized[name].append({
                "time": round(timestamp, 4),
                "confidence": round(float(np.clip(confidence, 0.0, 1.0)), 4),
                "detector_confidence": round(float(np.clip(confidence, 0.0, 1.0)), 4),
                "relative_intensity": None,
                "intensity_source": "pending_waveform_measurement",
                "velocity": velocity,
                "velocity_source": "model" if velocity is not None else "unavailable",
                "subtype": raw_family,
            })
    for name in DRUM_CLASSES:
        normalized[name].sort(key=lambda item: item["time"])
    if not any(normalized.values()):
        return None
    return normalized, str(payload.get("engine") or model_route.get("engine") or "dedicated_drum_model")


def _float_points(values: list[float] | np.ndarray | None) -> np.ndarray:
    points = np.asarray([] if values is None else values, dtype=float)
    return np.sort(points[np.isfinite(points) & (points >= 0)])


def _robust_unit(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    if not len(values):
        return values
    low = float(np.percentile(values, 20))
    high = float(np.percentile(values, 98))
    if high - low <= 1e-10:
        return np.zeros_like(values)
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def _band_flux(power: np.ndarray, frequencies: np.ndarray, low: float, high: float) -> np.ndarray:
    mask = (frequencies >= low) & (frequencies < high)
    if not np.any(mask):
        return np.zeros(power.shape[1], dtype=float)
    energy = np.log1p(np.sum(power[mask], axis=0))
    flux = np.maximum(np.diff(energy, prepend=energy[0]), 0.0)
    if len(flux) >= 3:
        flux = np.convolve(flux, np.array([0.2, 0.6, 0.2]), mode="same")
    return _robust_unit(flux)


def _pick_events(
    score: np.ndarray,
    *,
    sr: int,
    hop_length: int,
    minimum_gap_seconds: float,
    threshold: float,
) -> list[dict[str, float | int]]:
    if len(score) < 3:
        return []
    adaptive = max(threshold, float(np.median(score) + 1.5 * np.median(np.abs(score - np.median(score)))))
    candidates = np.where(
        (score[1:-1] >= score[:-2])
        & (score[1:-1] > score[2:])
        & (score[1:-1] >= adaptive)
    )[0] + 1
    minimum_frames = max(1, int(round(minimum_gap_seconds * sr / hop_length)))
    accepted: list[int] = []
    for index in sorted(candidates.tolist(), key=lambda item: float(score[item]), reverse=True):
        if all(abs(index - previous) >= minimum_frames for previous in accepted):
            accepted.append(index)
    events = []
    for index in sorted(accepted):
        strength = float(np.clip(score[index], 0.0, 1.0))
        events.append({
            "time": round(float(index * hop_length / sr), 4),
            "confidence": round(float(0.35 + 0.65 * strength), 4),
            "detector_confidence": round(float(0.35 + 0.65 * strength), 4),
            "relative_intensity": None,
            "intensity_source": "pending_waveform_measurement",
            "velocity": None,
            "velocity_source": "unavailable",
        })
    return events


def _attach_relative_intensity(
    events: dict[str, list[dict]], audio: np.ndarray, sr: int,
) -> None:
    """Measure hit strength from audio, independently of detector certainty."""
    for name, values in events.items():
        raw: list[float] = []
        for event in values:
            center = int(round(float(event["time"]) * sr))
            start = max(0, center - int(0.010 * sr))
            end = min(len(audio), center + int(0.090 * sr))
            clip = np.asarray(audio[start:end], dtype=float)
            raw.append(float(np.sqrt(np.mean(np.square(clip)))) if len(clip) else 0.0)
        reference = float(np.percentile(raw, 90)) if raw else 0.0
        for event, event_rms in zip(values, raw):
            relative = float(np.clip(event_rms / (reference + 1e-10), 0.0, 1.0)) if reference > 0 else 0.0
            event["relative_intensity"] = round(relative, 4)
            event["intensity_source"] = "local_waveform_rms_same_family_p90"
            event["event_rms"] = round(event_rms, 6)


def _remove_spectral_leakage(
    events: dict[str, list[dict]],
    *,
    low: np.ndarray,
    mid: np.ndarray,
    high: np.ndarray,
    sr: int,
    hop_length: int,
) -> dict[str, list[dict]]:
    """Suppress obvious cross-band duplicates while retaining real overlaps.

    A broadband snare is allowed to coexist with a hi-hat.  We only discard a
    snare candidate when it coincides with a hi-hat and the high-band onset is
    clearly stronger than the mid band.  This removes the common failure mode
    where every isolated hi-hat is counted as a snare.
    """
    def frame_at(event: dict) -> int:
        return int(np.clip(round(float(event["time"]) * sr / hop_length), 0, len(mid) - 1))

    kick = [
        event for event in events["kick"]
        if low[frame_at(event)] > 0.8 * mid[frame_at(event)]
    ]
    snare = []
    for event in events["snare"]:
        frame = frame_at(event)
        overlaps_hihat = any(
            abs(float(event["time"]) - float(hihat["time"])) <= 0.035
            for hihat in events["hihat"]
        )
        if overlaps_hihat and high[frame] > 1.15 * mid[frame]:
            continue
        snare.append(event)
    return {"kick": kick, "snare": snare, "hihat": events["hihat"]}


def _resolve_spectral_competition(
    events: dict[str, list[dict]],
    *,
    low: np.ndarray,
    mid: np.ndarray,
    high: np.ndarray,
    sr: int,
    hop_length: int,
) -> dict[str, list[dict]]:
    """Resolve cross-band duplicates produced by the fallback detector.

    The proxy has no learned instrument identity.  Nearby candidates therefore
    compete on band evidence.  A kick+hat or snare+hat pair may survive when
    both bands are independently strong, but one broadband transient may not
    become all three drum classes.
    """
    candidates = sorted(
        (float(event["time"]), name, event)
        for name in CORE_DRUM_CLASSES for event in events[name]
    )
    clusters: list[list[tuple[float, str, dict]]] = []
    for candidate in candidates:
        if not clusters or candidate[0] - clusters[-1][-1][0] > 0.035:
            clusters.append([candidate])
        else:
            clusters[-1].append(candidate)

    resolved = {name: [] for name in CORE_DRUM_CLASSES}
    for cluster in clusters:
        center = float(np.mean([item[0] for item in cluster]))
        candidate_frames = {
            int(np.clip(round(item[0] * sr / hop_length), 0, len(mid) - 1))
            for item in cluster
        }
        frame = max(
            candidate_frames,
            key=lambda value: float(low[value] + mid[value] + high[value]),
        )
        band = {"kick": float(low[frame]), "snare": float(mid[frame]), "hihat": float(high[frame])}
        discriminant = {
            "kick": band["kick"] - 0.28 * band["snare"] - 0.08 * band["hihat"],
            "snare": band["snare"] + 0.18 * band["hihat"] - 0.38 * band["kick"],
            "hihat": band["hihat"] - 0.30 * band["kick"] - 0.12 * band["snare"],
        }
        eligible = [
            name for name, floor in {"kick": 0.45, "snare": 0.50, "hihat": 0.50}.items()
            if band[name] >= floor
        ]
        if not eligible:
            continue
        eligible.sort(key=lambda name: discriminant[name], reverse=True)
        selected = [eligible[0]]
        if len(eligible) >= 2:
            pair = {eligible[0], eligible[1]}
            independent_pair = (
                pair == {"kick", "hihat"}
                and band["kick"] >= 0.50 and band["hihat"] >= 0.50
                and band["snare"] <= max(band["kick"], band["hihat"])
            ) or (
                pair == {"snare", "hihat"}
                and band["snare"] >= 0.72 and band["hihat"] >= 0.72
                and band["kick"] <= 0.55
            )
            if independent_pair:
                selected.append(eligible[1])
        for name in selected:
            matching = [item[2] for item in cluster if item[1] == name]
            source = min(matching, key=lambda item: abs(float(item["time"]) - center)) if matching else cluster[0][2]
            confidence = min(0.62, 0.30 + 0.32 * max(0.0, band[name]))
            resolved[name].append({
                **source,
                "time": round(center, 4),
                "confidence": round(confidence, 4),
                "detector_confidence": round(confidence, 4),
                "classification_margin": round(
                    discriminant[name] - max(
                        (value for other, value in discriminant.items() if other != name),
                        default=0.0,
                    ),
                    4,
                ),
            })
    # Preserve clear single-band events that lost a close competition only
    # because another detector peak was a few frames later.
    dominance = {
        "kick": lambda frame: low[frame] >= 0.80 * mid[frame],
        "snare": lambda frame: mid[frame] >= 0.75 * low[frame] and mid[frame] >= 0.65 * high[frame],
        "hihat": lambda frame: high[frame] >= 0.85 * mid[frame],
    }
    for name in CORE_DRUM_CLASSES:
        for source in events[name]:
            timestamp = float(source["time"])
            if any(abs(timestamp - float(item["time"])) <= 0.05 for item in resolved[name]):
                continue
            frame = int(np.clip(round(timestamp * sr / hop_length), 0, len(mid) - 1))
            if not dominance[name](frame):
                continue
            confidence = min(0.62, float(source.get("detector_confidence", 0.5)))
            resolved[name].append({
                **source,
                "confidence": round(confidence, 4),
                "detector_confidence": round(confidence, 4),
                "classification_margin": 0.0,
            })
        resolved[name].sort(key=lambda item: float(item["time"]))
    return resolved


def _density_curve(events: dict[str, list[dict]], duration: float, window_sec: float) -> list[dict]:
    count = max(1, int(np.ceil(duration / window_sec)))
    raw: list[dict] = []
    totals = []
    for index in range(count):
        start = index * window_sec
        end = min(duration, start + window_sec)
        counts = {
            name: sum(start <= float(event["time"]) < end for event in events[name])
            for name in DRUM_CLASSES
        }
        total = sum(counts.values())
        totals.append(total / max(end - start, 1e-6))
        raw.append({"start": round(start, 3), "end": round(end, 3), **counts, "total": total})
    reference = float(np.percentile(totals, 95)) if totals else 0.0
    for item, hits_per_second in zip(raw, totals):
        item["hits_per_second"] = round(hits_per_second, 4)
        item["normalized"] = round(float(np.clip(hits_per_second / reference, 0.0, 1.0)), 4) if reference else 0.0
    return raw


def _bar_grid(
    *,
    bpm: float | None,
    beat_points: list[float] | np.ndarray | None,
    downbeats: list[float] | np.ndarray | None,
    duration: float,
) -> np.ndarray:
    bars = _float_points(downbeats)
    if len(bars) >= 2:
        return bars
    beats = _float_points(beat_points)
    if len(beats) >= 8:
        return beats[::4]
    if bpm is not None and np.isfinite(bpm) and bpm > 0:
        return np.arange(0.0, duration, 4.0 * 60.0 / bpm)
    return np.asarray([], dtype=float)


def _pattern_and_fills(
    events: dict[str, list[dict]],
    *,
    bars: np.ndarray,
    bpm: float | None,
) -> tuple[dict, list[dict]]:
    patterns: list[dict] = []
    weighted_counts: list[float] = []
    tail_weights: list[float] = []
    if len(bars) < 2:
        return {
            "resolution": 16,
            "bars_analyzed": 0,
            "dominant": None,
            "stability": 0.0,
            "syncopation": 0.0,
        }, []

    expected = 4.0 * 60.0 / bpm if bpm and bpm > 0 else float(np.median(np.diff(bars)))
    for start, end in zip(bars[:-1], bars[1:]):
        duration = float(end - start)
        if duration <= 0 or abs(duration / expected - 1.0) > 0.2:
            continue
        class_steps: dict[str, set[int]] = {}
        for name in DRUM_CLASSES:
            steps = set()
            for event in events[name]:
                event_time = float(event["time"])
                raw_step = int(round((event_time - start) / duration * 16))
                # Allow half a 16th-note of detector jitter around the bar
                # boundary.  A hit quantized to step 16 belongs to the next
                # bar instead of being clipped onto step 15.
                if 0 <= raw_step < 16 and start - duration / 32 <= event_time < end + duration / 32:
                    steps.add(raw_step)
            class_steps[name] = steps
        encoded = {
            name: "".join(symbol if step in class_steps[name] else "." for step in range(16))
            for name, symbol in (("kick", "K"), ("snare", "S"), ("hihat", "H"), ("tom", "T"), ("cymbal", "C"))
        }
        offbeat = sum(step % 4 not in (0,) for steps in class_steps.values() for step in steps)
        total = sum(len(steps) for steps in class_steps.values())
        patterns.append({
            "start": round(float(start), 3),
            "end": round(float(end), 3),
            **encoded,
            "syncopation": offbeat / total if total else 0.0,
            "counts": {name: len(class_steps[name]) for name in DRUM_CLASSES},
            "tail_counts": {
                name: sum(step >= 12 for step in class_steps[name])
                for name in DRUM_CLASSES
            },
        })
        weighted_counts.append(
            len(class_steps["kick"]) + len(class_steps["snare"]) + 0.35 * len(class_steps["hihat"])
        )
        tail_weights.append(
            0.5 * sum(step >= 12 for step in class_steps["kick"])
            + sum(step >= 12 for step in class_steps["snare"])
            + 0.35 * sum(step >= 12 for step in class_steps["hihat"])
        )

    if not patterns:
        return {
            "resolution": 16,
            "bars_analyzed": 0,
            "dominant": None,
            "stability": 0.0,
            "syncopation": 0.0,
        }, []

    signatures = [(item["kick"], item["snare"], item["hihat"]) for item in patterns]

    # Exact signature counting made stability collapse when one otherwise
    # identical bar contained a single ghost note or missed hi-hat.  Select a
    # medoid pattern and report cell-level agreement across the 3 x 16 grid.
    def signature_similarity(left: tuple[str, str, str], right: tuple[str, str, str]) -> float:
        comparisons = [a == b for left_row, right_row in zip(left, right) for a, b in zip(left_row, right_row)]
        return float(np.mean(comparisons)) if comparisons else 0.0

    dominant_signature = max(
        signatures,
        key=lambda candidate: float(np.mean([
            signature_similarity(candidate, other) for other in signatures
        ])),
    )
    stability = float(np.mean([
        signature_similarity(dominant_signature, other) for other in signatures
    ]))
    dominant = dict(zip(DRUM_CLASSES, dominant_signature))
    syncopation = float(np.mean([item["syncopation"] for item in patterns]))
    median_weight = float(np.median(weighted_counts))
    mad = float(np.median(np.abs(np.asarray(weighted_counts) - median_weight)))
    bar_threshold = median_weight + max(0.5, 0.75 * mad)
    median_tail = float(np.median(tail_weights))
    tail_mad = float(np.median(np.abs(np.asarray(tail_weights) - median_tail)))
    tail_threshold = median_tail + max(0.9, 1.8 * tail_mad)
    fills = []
    for item, weight, tail_weight in zip(patterns, weighted_counts, tail_weights):
        tail_counts = item["tail_counts"]
        tail_hits = sum(tail_counts.values())
        total_hits = int(sum(item["counts"].values()))
        head_hits = total_hits - tail_hits
        tail_is_locally_dense = tail_hits >= max(3, int(np.ceil(0.5 * head_hits)))
        if weight >= bar_threshold and tail_weight >= tail_threshold and tail_is_locally_dense:
            excess = (tail_weight - tail_threshold) / max(tail_threshold, 1.0)
            confidence = float(np.clip(0.55 + 0.35 * excess, 0.55, 0.98))
            fills.append({
                "start": item["start"],
                "end": item["end"],
                "confidence": round(confidence, 4),
                "hit_count": total_hits,
                "tail_hit_count": int(tail_hits),
            })

    return {
        "resolution": 16,
        "bars_analyzed": len(patterns),
        "dominant": dominant,
        "stability": round(stability, 4),
        "syncopation": round(syncopation, 4),
    }, fills


def _metrical_alignment(
    events: dict[str, list[dict]], beat_points: np.ndarray,
) -> dict[str, Any]:
    """Compare drum events with straight and triplet metrical hypotheses."""
    all_times = np.asarray(
        [float(event["time"]) for name in DRUM_CLASSES for event in events[name]],
        dtype=float,
    )
    intervals = np.diff(beat_points)
    valid_intervals = intervals[np.isfinite(intervals) & (intervals > 1e-4)]
    if not len(all_times) or len(beat_points) < 2 or not len(valid_intervals):
        return {
            "grid_type": None,
            "subdivision_alignment": 0.5,
            "phase_consistency": 0.5,
            "systematic_offset_ms": None,
            "timing_deviation_ms": None,
            "metrical_level_reliability": 0.0,
            "candidates": {},
        }

    hypotheses = {"straight_16th": 4, "triplet_12th": 3}
    candidates: dict[str, dict[str, float]] = {}
    for name, subdivisions in hypotheses.items():
        signed_errors: list[float] = []
        absolute_ms: list[float] = []
        scores: list[float] = []
        for value in all_times:
            index = int(np.searchsorted(beat_points, value, side="right") - 1)
            if index < 0 or index >= len(beat_points) - 1:
                continue
            beat_duration = float(beat_points[index + 1] - beat_points[index])
            if beat_duration <= 1e-4:
                continue
            phase = (value - beat_points[index]) / beat_duration
            nearest = round(phase * subdivisions) / subdivisions
            error = float(phase - nearest)
            half_cell = 0.5 / subdivisions
            signed_errors.append(error)
            absolute_ms.append(abs(error) * beat_duration * 1000.0)
            scores.append(1.0 - min(1.0, abs(error) / half_cell))
        if not scores:
            continue
        median_error = float(np.median(signed_errors))
        mad = float(np.median(np.abs(np.asarray(signed_errors) - median_error)))
        phase_consistency = float(np.clip(1.0 - mad / (0.5 / subdivisions), 0.0, 1.0))
        alignment = float(np.mean(scores))
        candidates[name] = {
            "subdivision_alignment": round(alignment, 4),
            "phase_consistency": round(phase_consistency, 4),
            "systematic_offset_ms": round(
                median_error * float(np.median(valid_intervals)) * 1000.0, 3
            ),
            "timing_deviation_ms": round(float(np.median(absolute_ms)), 3),
            "score": round(0.72 * alignment + 0.28 * phase_consistency, 4),
        }
    if not candidates:
        return _metrical_alignment(events, np.asarray([]))
    grid_type, best = max(candidates.items(), key=lambda item: item[1]["score"])
    interval_cv = float(np.std(valid_intervals) / (np.mean(valid_intervals) + 1e-8))
    level_reliability = float(np.clip(1.0 - 2.5 * interval_cv, 0.0, 1.0))
    return {
        "grid_type": grid_type,
        "subdivision_alignment": best["subdivision_alignment"],
        "phase_consistency": best["phase_consistency"],
        "systematic_offset_ms": best["systematic_offset_ms"],
        "timing_deviation_ms": best["timing_deviation_ms"],
        "metrical_level_reliability": round(level_reliability, 4),
        "candidates": candidates,
    }


def analyze_drum_stem(
    audio: np.ndarray | None,
    sr: int,
    *,
    bpm: float | None = None,
    beat_points: list[float] | np.ndarray | None = None,
    downbeats: list[float] | np.ndarray | None = None,
    separation_quality: float = 0.75,
    density_window_sec: float = 2.0,
    model_route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Transcribe drum events and derive grid-aligned rhythm metadata."""
    if audio is None or sr <= 0 or len(audio) < sr:
        return empty_drum_analysis()
    mono = np.asarray(audio, dtype=np.float32)
    if mono.ndim > 1:
        mono = np.mean(mono, axis=1)
    if float(np.sqrt(np.mean(np.square(mono)))) <= 1e-6:
        return empty_drum_analysis("silent_drums_stem")
    target_sr = 22050
    if sr != target_sr:
        mono = librosa.resample(mono, orig_sr=sr, target_sr=target_sr)
        sr = target_sr

    model_events = _normalized_model_events(model_route)
    if model_events is not None:
        events, selected_engine = model_events
        detector_mode = "dedicated_model"
    else:
        hop_length = 256
        n_fft = 1024
        spectrum = np.abs(librosa.stft(mono, n_fft=n_fft, hop_length=hop_length)) ** 2
        frequencies = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
        low = _band_flux(spectrum, frequencies, 30.0, 180.0)
        mid = _band_flux(spectrum, frequencies, 180.0, 4000.0)
        high = _band_flux(spectrum, frequencies, 4000.0, min(11000.0, sr / 2.0))

        kick_score = _robust_unit(low * (0.75 + 0.25 * (1.0 - high)))
        snare_score = _robust_unit(np.clip(0.72 * mid + 0.38 * high - 0.20 * low, 0.0, None))
        hihat_score = _robust_unit(np.clip(0.90 * high + 0.10 * mid - 0.28 * low, 0.0, None))
        core_events = {
            "kick": _pick_events(kick_score, sr=sr, hop_length=hop_length, minimum_gap_seconds=0.09, threshold=0.48),
            "snare": _pick_events(snare_score, sr=sr, hop_length=hop_length, minimum_gap_seconds=0.10, threshold=0.55),
            "hihat": _pick_events(hihat_score, sr=sr, hop_length=hop_length, minimum_gap_seconds=0.05, threshold=0.58),
        }
        core_events = _remove_spectral_leakage(
            core_events,
            low=low,
            mid=mid,
            high=high,
            sr=sr,
            hop_length=hop_length,
        )
        core_events = _resolve_spectral_competition(
            core_events, low=low, mid=mid, high=high, sr=sr, hop_length=hop_length,
        )
        events = {**core_events, "tom": [], "cymbal": []}
        selected_engine = "spectral_flux_fallback"
        detector_mode = "fallback"
    _attach_relative_intensity(events, mono, sr)
    duration = len(mono) / sr
    beat_grid = _float_points(beat_points)
    bars = _bar_grid(bpm=bpm, beat_points=beat_points, downbeats=downbeats, duration=duration)
    pattern, fills = _pattern_and_fills(events, bars=bars, bpm=bpm)
    density = _density_curve(events, duration, density_window_sec)
    metrical = _metrical_alignment(events, beat_grid)
    alignment = float(metrical["subdivision_alignment"])
    event_strength = float(np.mean([
        float(event["confidence"])
        for name in DRUM_CLASSES for event in events[name]
    ])) if any(events.values()) else 0.0
    overall = float(np.clip(
        0.45 * float(np.clip(separation_quality, 0.0, 1.0))
        + 0.30 * event_strength
        + 0.15 * alignment
        + 0.10 * float(metrical["phase_consistency"]),
        0.0,
        1.0,
    ))
    if detector_mode == "fallback":
        overall = min(overall, 0.58)
    class_confidence = {
        name: round(float(np.mean([event["confidence"] for event in values])), 4) if values else 0.0
        for name, values in events.items()
    }
    flags = []
    if not len(beat_grid):
        flags.append("beat_grid_unavailable")
    elif alignment < 0.45:
        flags.append("low_metrical_alignment")
    if len(_float_points(downbeats)) < 2:
        flags.append("downbeat_grid_unavailable")
    if pattern["bars_analyzed"] == 0:
        flags.append("bar_pattern_unavailable")
    if separation_quality < 0.6:
        flags.append("low_stem_quality")
    if detector_mode == "fallback":
        flags.append("dedicated_drum_model_unavailable")
        flags.append("spectral_proxy_fallback")
    if overall < 0.58:
        flags.append("low_confidence")
    return {
        "version": DRUM_ANALYSIS_VERSION,
        "source": "demucs_drums_stem",
        "selected_engine": selected_engine,
        "detector_mode": detector_mode,
        "status": "ready" if detector_mode == "dedicated_model" and overall >= 0.58 else "degraded",
        "needs_review": bool(flags),
        "reason": None,
        "events": events,
        "counts": {name: len(values) for name, values in events.items()},
        "density_curve": density,
        "pattern": pattern,
        "fills": fills,
        "metrical_alignment": metrical,
        "confidence": {
            "overall": round(overall, 4),
            **class_confidence,
            "beat_alignment": round(float(alignment), 4),
            "subdivision_alignment": round(float(alignment), 4),
            "phase_consistency": metrical["phase_consistency"],
            "stem_quality": round(float(np.clip(separation_quality, 0.0, 1.0)), 4),
        },
        "quality_flags": flags,
        "engine_routes": {
            "dedicated_model": model_route or {
                "status": "unavailable",
                "engine": "external_drum_transcriber",
                "error": "model_route_not_supplied",
            },
            "spectral_fallback": {"status": "selected" if detector_mode == "fallback" else "not_selected"},
        },
    }
