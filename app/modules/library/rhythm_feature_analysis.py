"""Bar-aligned rhythm grammar for downstream style classification."""
from __future__ import annotations

from typing import Any

import numpy as np

from app.modules.library.style_feature_evidence import make_feature_evidence, unavailable_feature


RHYTHM_FEATURE_VERSION = "rhythm_grammar_features_v1"
RHYTHM_FEATURES = (
    "four_on_floor", "backbeat_2_4", "halftime_snare_3", "jersey_club",
    "tamborzao", "dembow", "tresillo", "two_step", "drill_hat",
    "breakbeat", "swing", "afro_syncopation",
)


def _clamp(value: float) -> float:
    return float(np.clip(float(value), 0.0, 1.0))


def _points(values) -> np.ndarray:
    raw = np.asarray([] if values is None else values, dtype=float)
    return np.sort(raw[np.isfinite(raw) & (raw >= 0)])


def _event_times(analysis: dict | None, *names: str) -> np.ndarray:
    values = []
    events = ((analysis or {}).get("events") or {})
    for name in names:
        for item in events.get(name, []):
            try:
                values.append(float(item.get("time", item)))
            except (AttributeError, TypeError, ValueError):
                continue
    return _points(values)


def _bars(downbeats, beats, bpm: float | None, duration: float) -> np.ndarray:
    downbeat_points = _points(downbeats)
    if len(downbeat_points) >= 2:
        return downbeat_points
    beat_points = _points(beats)
    if len(beat_points) >= 8:
        return beat_points[::4]
    if bpm and np.isfinite(bpm) and bpm > 0:
        return np.arange(0.0, duration + 1e-6, 240.0 / bpm)
    return np.asarray([])


def _quantize(events: np.ndarray, bars: np.ndarray, bpm: float | None) -> list[set[int]]:
    if len(bars) < 2:
        return []
    expected = 240.0 / bpm if bpm and bpm > 0 else float(np.median(np.diff(bars)))
    result = []
    for start, end in zip(bars[:-1], bars[1:]):
        length = float(end - start)
        if length <= 0 or abs(length / expected - 1.0) > 0.22:
            continue
        steps = {
            int(round((value - start) / length * 16))
            for value in events
            if start - length / 32 <= value < end + length / 32
        }
        result.append({step for step in steps if 0 <= step < 16})
    return result


def _match(steps: set[int], targets: set[int]) -> float:
    if not targets:
        return 0.0
    hits = len(steps & targets)
    recall = hits / len(targets)
    precision = hits / max(len(steps), 1)
    return 0.72 * recall + 0.28 * precision


def _combined(kick: set[int], snare: set[int], kick_target: set[int], snare_target: set[int]) -> float:
    return 0.58 * _match(kick, kick_target) + 0.42 * _match(snare, snare_target)


def _ranges(indices: list[int], bars: np.ndarray) -> list[dict[str, float]]:
    return [
        {"start": round(float(bars[index]), 4), "end": round(float(bars[index + 1]), 4)}
        for index in indices[:48] if index + 1 < len(bars)
    ]


def _aggregate(scores: list[float]) -> tuple[float, list[int]]:
    if not scores:
        return 0.0, []
    return float(np.mean(scores)), [index for index, score in enumerate(scores) if score >= 0.60]


def analyze_rhythm_features(
    drum_analysis: dict | None,
    *,
    bpm: float | None,
    beat_points,
    downbeats,
    duration: float,
) -> dict[str, Any]:
    method = "bar_aligned_16_step_templates_v1"
    bars = _bars(downbeats, beat_points, bpm, duration)
    if len(bars) < 2:
        return {
            "version": RHYTHM_FEATURE_VERSION,
            "status": "unavailable",
            "features": {
                name: unavailable_feature(
                    "bar_grid_unavailable",
                    sources=["bpm", "beat_grid", "downbeat_grid", "drum_transcription"],
                    analysis_method=method,
                ) for name in RHYTHM_FEATURES
            },
            "windows": [],
            "confidence": 0.0,
            "quality_flags": ["bar_grid_unavailable"],
        }

    kick_times = _event_times(drum_analysis, "kick")
    snare_times = _event_times(drum_analysis, "snare", "clap", "rim")
    hat_times = _event_times(drum_analysis, "hihat", "cymbal")
    percussion_times = _event_times(drum_analysis, "tom", "percussion", "conga", "bongo")
    kick = _quantize(kick_times, bars, bpm)
    snare = _quantize(snare_times, bars, bpm)
    hats = _quantize(hat_times, bars, bpm)
    percussion = _quantize(percussion_times, bars, bpm)
    analyzed = min(len(kick), len(snare), len(hats))
    if analyzed == 0:
        analyzed = min(len(kick), len(snare))
    quality = _clamp(analyzed / 16.0) * _clamp(
        (len(kick_times) + len(snare_times) + len(hat_times)) / max(duration * 1.2, 12.0)
    )

    raw: dict[str, list[float]] = {name: [] for name in RHYTHM_FEATURES if name != "swing"}
    for index in range(analyzed):
        k, s = kick[index], snare[index]
        h = hats[index] if index < len(hats) else set()
        p = percussion[index] if index < len(percussion) else set()
        union = k | s | h | p
        four = _match(k, {0, 4, 8, 12})
        backbeat = _match(s, {4, 12})
        halftime = _match(s, {8})
        tresillo = max(_match(union, {0, 6, 12}), _match(union, {0, 6, 10}))
        offbeat_kicks = sum(step % 4 != 0 for step in k) / max(len(k), 1)
        offbeat_drums = sum(step % 4 != 0 for step in (k | s | p)) / max(len(k | s | p), 1)
        hat_density = _clamp(len(h) / 8.0)
        percussion_density = _clamp(len(p) / 6.0)
        jersey = _combined(k, s, {0, 4, 8, 11, 14}, {8, 11})
        tamborzao = _combined(k, s, {0, 6, 10, 12}, {4, 12})
        dembow = max(
            _combined(k, s, {0, 3, 10}, {6, 12}),
            _combined(k, s, {0, 8}, {3, 6, 11, 14}),
        )
        two_step = _clamp(0.58 * backbeat + 0.42 * offbeat_kicks - 0.38 * four)
        # Drill hats need both a subdivided/tresillo layer and local rapid hits.
        drill_hat = _clamp(0.44 * tresillo + 0.34 * hat_density + 0.22 * offbeat_drums)
        variation = _clamp((len(k | s) - len((k | s) & {0, 4, 8, 12})) / 5.0)
        breakbeat = _clamp(0.38 * backbeat + 0.34 * variation + 0.28 * offbeat_drums - 0.30 * four)
        afro = _clamp(
            0.30 * offbeat_kicks + 0.25 * percussion_density + 0.23 * hat_density
            + 0.22 * tresillo - 0.22 * four
        )
        for name, score in {
            "four_on_floor": four,
            "backbeat_2_4": backbeat,
            "halftime_snare_3": halftime,
            "jersey_club": jersey,
            "tamborzao": tamborzao,
            "dembow": dembow,
            "tresillo": tresillo,
            "two_step": two_step,
            "drill_hat": drill_hat,
            "breakbeat": breakbeat,
            "afro_syncopation": afro,
        }.items():
            raw[name].append(score)

    beats = _points(beat_points)
    offbeat_delays = []
    if len(beats) >= 2:
        for value in hat_times:
            previous = int(np.searchsorted(beats, value, side="right") - 1)
            if 0 <= previous < len(beats) - 1:
                interval = beats[previous + 1] - beats[previous]
                phase = (value - beats[previous]) / interval if interval > 0 else 0.0
                if 0.38 <= phase <= 0.78:
                    offbeat_delays.append(float(phase - 0.5))
    median_delay = float(np.median(offbeat_delays)) if offbeat_delays else 0.0
    consistency = _clamp(1.0 - float(np.std(offbeat_delays)) / 0.12) if len(offbeat_delays) >= 3 else 0.0
    swing_score = _clamp(max(0.0, median_delay - 0.025) / 0.14 * consistency)

    templates = {
        "four_on_floor": {"kick_steps": [0, 4, 8, 12], "conflicts": ["syncopated_kick"]},
        "backbeat_2_4": {"snare_steps": [4, 12]},
        "halftime_snare_3": {"snare_steps": [8]},
        "jersey_club": {"kick_steps": [0, 4, 8, 11, 14], "snare_steps": [8, 11]},
        "tamborzao": {"kick_steps": [0, 6, 10, 12], "snare_steps": [4, 12]},
        "dembow": {"kick_steps": [0, 3, 10], "snare_steps": [6, 12], "allows_phase_variant": True},
        "tresillo": {"accent_step_variants": [[0, 6, 12], [0, 6, 10]]},
        "two_step": {"snare_steps": [4, 12], "negative_evidence": "stable_four_on_floor"},
        "drill_hat": {"requires": ["subdivided_hat", "tresillo_or_offbeat_accents"]},
        "breakbeat": {"requires": ["backbeat_skeleton", "kick_snare_variation"], "negative_evidence": "stable_four_on_floor"},
        "afro_syncopation": {"requires": ["sparse_syncopated_kick", "layered_percussion", "continuous_high_layer"]},
    }
    features = {}
    matched_by_name = {}
    for name, scores in raw.items():
        score, matched = _aggregate(scores)
        matched_by_name[name] = matched
        features[name] = make_feature_evidence(
            score,
            threshold=0.58,
            confidence=quality,
            sources=["bpm", "beat_grid", "downbeat_grid", "drum_transcription"],
            analysis_method=method,
            time_ranges=_ranges(matched, bars),
            evidence={
                "bars_analyzed": analyzed,
                "grid_resolution": 16,
                "template": templates[name],
                "mean_template_score": round(score, 4),
            },
        )
    features["swing"] = make_feature_evidence(
        swing_score,
        threshold=0.55,
        confidence=_clamp(len(offbeat_delays) / 16.0),
        sources=["beat_grid", "drum_transcription"],
        analysis_method="microtiming_offbeat_delay_v1",
        evidence={
            "median_offbeat_delay_beats": round(median_delay, 4),
            "offbeat_event_count": len(offbeat_delays),
            "timing_consistency": round(consistency, 4),
        },
    )

    windows = []
    for start in range(0, analyzed, 8):
        end = min(analyzed, start + 8)
        windows.append({
            "start": round(float(bars[start]), 4),
            "end": round(float(bars[end]), 4),
            "bar_count": end - start,
            "scores": {
                name: round(float(np.mean(scores[start:end])), 4)
                for name, scores in raw.items() if scores[start:end]
            },
        })
    flags = []
    if analyzed < 8:
        flags.append("fewer_than_8_valid_bars")
    if quality < 0.55:
        flags.append("low_rhythm_evidence_quality")
    return {
        "version": RHYTHM_FEATURE_VERSION,
        "status": "ready" if quality >= 0.55 else "degraded",
        "features": features,
        "windows": windows,
        "confidence": round(quality, 4),
        "quality_flags": flags,
    }
