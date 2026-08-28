"""Bar-aligned rhythm grammar for downstream style classification."""
from __future__ import annotations

from typing import Any

import numpy as np

from app.modules.library.style_feature_evidence import make_feature_evidence, unavailable_feature


RHYTHM_FEATURE_VERSION = "rhythm_grammar_features_v3"
RHYTHM_FEATURES = (
    "four_on_floor", "backbeat_2_4", "halftime_snare_3", "jersey_club",
    "tamborzao", "dembow", "tresillo", "two_step", "drill_hat",
    "breakbeat", "swing", "afro_syncopation",
    "offbeat_open_hat", "four_floor_stability", "timing_quantization",
    "drum_loop_repetition", "drum_machine_consistency",
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


def _event_records(analysis: dict | None, *names: str) -> list[dict[str, Any]]:
    result = []
    events = ((analysis or {}).get("events") or {})
    for name in names:
        for value in events.get(name, []):
            if isinstance(value, dict):
                result.append(value)
            else:
                try:
                    result.append({"time": float(value)})
                except (TypeError, ValueError):
                    continue
    return result


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
    return 0.60 * recall + 0.40 * precision


def _combined(kick: set[int], snare: set[int], kick_target: set[int], snare_target: set[int]) -> float:
    return 0.58 * _match(kick, kick_target) + 0.42 * _match(snare, snare_target)


def _signature_similarity(left: set[tuple[str, int]], right: set[tuple[str, int]]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return 2.0 * len(left & right) / (len(left) + len(right))


def _rhythm_boundary_descriptors(
    *,
    kick: list[set[int]],
    snare: list[set[int]],
    hats: list[set[int]],
    bars: np.ndarray,
    event_records: list[dict[str, Any]],
) -> dict[str, Any]:
    analyzed = min(len(kick), len(snare), len(hats))
    four_scores = [_match(value, {0, 4, 8, 12}) for value in kick[:analyzed]]
    four_matches = [value >= 0.72 for value in four_scores]
    four_coverage = float(np.mean(four_matches)) if four_matches else 0.0
    four_continuity = _longest_run(four_matches) / max(1, len(four_matches))
    four_stability = _clamp(1.0 - float(np.std(four_scores)) / 0.30) if four_scores else 0.0
    four_floor_stability = _clamp(
        (float(np.mean(four_scores)) if four_scores else 0.0)
        * np.sqrt(four_coverage)
        * (0.55 + 0.45 * four_continuity)
        * four_stability
    )

    hat_scores = [_match(value, {2, 6, 10, 14}) for value in hats[:analyzed]]
    offbeat_hat_coverage = float(np.mean([value >= 0.70 for value in hat_scores])) if hat_scores else 0.0
    offbeat_hat_score = _clamp(
        (float(np.mean(hat_scores)) if hat_scores else 0.0) * np.sqrt(offbeat_hat_coverage)
    )

    signatures = [
        ({("kick", step) for step in kick[index]}
         | {("snare", step) for step in snare[index]}
         | {("hat", step) for step in hats[index]})
        for index in range(analyzed)
    ]
    recurrence_by_lag: dict[str, float] = {}
    for lag in (1, 2, 4):
        values = [
            _signature_similarity(signatures[index], signatures[index + lag])
            for index in range(len(signatures) - lag)
            if signatures[index] and signatures[index + lag]
        ]
        if values:
            recurrence_by_lag[str(lag)] = round(float(np.mean(values)), 4)
    loop_repetition = max(recurrence_by_lag.values(), default=0.0)
    loop_coverage = sum(bool(value) for value in signatures) / max(1, len(signatures))
    loop_score = _clamp(loop_repetition * np.sqrt(loop_coverage))

    timing_errors = []
    for record in event_records:
        try:
            timestamp = float(record.get("time"))
        except (AttributeError, TypeError, ValueError):
            continue
        index = int(np.searchsorted(bars, timestamp, side="right") - 1)
        if index < 0 or index >= len(bars) - 1 or bars[index + 1] <= bars[index]:
            continue
        bar_length = float(bars[index + 1] - bars[index])
        exact_step = (timestamp - bars[index]) / bar_length * 16.0
        timing_errors.append(abs(exact_step - round(exact_step)) * bar_length / 16.0)
    median_error_ms = float(np.median(timing_errors) * 1000.0) if timing_errors else None
    p90_error_ms = float(np.percentile(timing_errors, 90) * 1000.0) if timing_errors else None
    quantization_score = _clamp(
        1.0 - (0.40 * median_error_ms + 0.60 * p90_error_ms) / 55.0
    ) if median_error_ms is not None and p90_error_ms is not None else 0.0

    intensities = []
    for record in event_records:
        try:
            value = float(record.get("relative_intensity"))
        except (AttributeError, TypeError, ValueError):
            continue
        if np.isfinite(value):
            intensities.append(value)
    intensity_consistency = _clamp(1.0 - float(np.std(intensities)) / 0.35) if len(intensities) >= 4 else 0.5
    drum_machine_score = _clamp(
        0.45 * quantization_score + 0.40 * loop_score + 0.15 * intensity_consistency
    )
    return {
        "four_floor_stability_score": four_floor_stability,
        "four_floor_bar_coverage": round(four_coverage, 4),
        "four_floor_continuity": round(four_continuity, 4),
        "four_floor_cross_bar_stability": round(four_stability, 4),
        "offbeat_hat_score": offbeat_hat_score,
        "offbeat_hat_bar_coverage": round(offbeat_hat_coverage, 4),
        "loop_score": loop_score,
        "loop_bar_coverage": round(loop_coverage, 4),
        "recurrence_by_lag_bars": recurrence_by_lag,
        "timing_event_count": len(timing_errors),
        "median_grid_error_ms": None if median_error_ms is None else round(median_error_ms, 4),
        "p90_grid_error_ms": None if p90_error_ms is None else round(p90_error_ms, 4),
        "quantization_score": quantization_score,
        "intensity_consistency": round(intensity_consistency, 4),
        "drum_machine_score": drum_machine_score,
    }


def _ranges(indices: list[int], bars: np.ndarray) -> list[dict[str, float]]:
    return [
        {"start": round(float(bars[index]), 4), "end": round(float(bars[index + 1]), 4)}
        for index in indices[:48] if index + 1 < len(bars)
    ]


def _aggregate(scores: list[float]) -> tuple[float, list[int]]:
    if not scores:
        return 0.0, []
    return float(np.mean(scores)), [index for index, score in enumerate(scores) if score >= 0.60]


def _longest_run(values: list[bool]) -> int:
    best = current = 0
    for value in values:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def _adaptive_windows(
    raw: dict[str, list[float]], bars: np.ndarray, analyzed: int,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    windows: list[dict[str, Any]] = []
    best_by_feature: dict[str, dict[str, Any]] = {}
    for bar_count in (4, 8, 16):
        if analyzed < bar_count:
            continue
        stride = max(1, bar_count // 4)
        starts = list(range(0, analyzed - bar_count + 1, stride))
        final_start = analyzed - bar_count
        if final_start not in starts:
            starts.append(final_start)
        for start in starts:
            end = start + bar_count
            feature_metrics = {}
            for name, scores in raw.items():
                values = np.asarray(scores[start:end], dtype=float)
                if not len(values):
                    continue
                matched = (values >= 0.58).tolist()
                template_match = float(np.mean(values))
                coverage = float(np.mean(matched))
                continuity = _longest_run(matched) / len(values)
                variance = float(np.var(values))
                stability = _clamp(1.0 - float(np.std(values)) / 0.35)
                stable_score = _clamp(
                    template_match * continuity * np.sqrt(max(coverage, 0.0)) * stability
                )
                metrics = {
                    "template_match": round(template_match, 4),
                    "continuity": round(continuity, 4),
                    "coverage": round(coverage, 4),
                    "cross_bar_variance": round(variance, 4),
                    "stability": round(stability, 4),
                    "stable_score": round(stable_score, 4),
                }
                feature_metrics[name] = metrics
                candidate = {
                    "start_bar": start,
                    "end_bar": end,
                    "window_bars": bar_count,
                    "start": round(float(bars[start]), 4),
                    "end": round(float(bars[end]), 4),
                    **metrics,
                }
                previous = best_by_feature.get(name)
                if previous is None or candidate["stable_score"] > previous["stable_score"]:
                    best_by_feature[name] = candidate
            windows.append({
                "start": round(float(bars[start]), 4),
                "end": round(float(bars[end]), 4),
                "start_bar": start,
                "end_bar": end,
                "bar_count": bar_count,
                "features": feature_metrics,
                # Compatibility summary used by existing diagnostics.
                "scores": {
                    name: metrics["template_match"] for name, metrics in feature_metrics.items()
                },
            })
    return windows, best_by_feature


def analyze_rhythm_features(
    drum_analysis: dict | None,
    *,
    bpm: float | None,
    beat_points,
    downbeats,
    duration: float,
) -> dict[str, Any]:
    method = "adaptive_bar_aligned_16_step_templates_v2"
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

    template_names = (
        "four_on_floor", "backbeat_2_4", "halftime_snare_3", "jersey_club",
        "tamborzao", "dembow", "tresillo", "two_step", "drill_hat",
        "breakbeat", "afro_syncopation",
    )
    raw: dict[str, list[float]] = {name: [] for name in template_names}
    for index in range(analyzed):
        k, s = kick[index], snare[index]
        h = hats[index] if index < len(hats) else set()
        p = percussion[index] if index < len(percussion) else set()
        union = k | s | h | p
        four = _match(k, {0, 4, 8, 12})
        raw_backbeat = _match(s, {4, 12})
        raw_halftime = _match(s, {8})
        # A dense or duplicated snare stream used to satisfy both grammars.
        # Treat the competing skeleton as counter-evidence while still
        # allowing a small ghost-note contribution.
        backbeat = _clamp(raw_backbeat - 0.35 * raw_halftime)
        halftime = _clamp(raw_halftime - 0.45 * raw_backbeat)
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

    all_drum_records = _event_records(
        drum_analysis, "kick", "snare", "clap", "rim", "hihat", "cymbal", "tom", "percussion",
    )
    boundary = _rhythm_boundary_descriptors(
        kick=kick, snare=snare, hats=hats, bars=bars, event_records=all_drum_records,
    )
    explicit_open_hat_count = sum(
        str(item.get("subtype") or "").lower() in {"open_hihat", "open_hi_hat"}
        for item in _event_records(drum_analysis, "hihat")
    )

    windows, best_by_name = _adaptive_windows(raw, bars, analyzed)
    flags = []
    if analyzed < 8:
        flags.append("fewer_than_8_valid_bars")
    if quality < 0.55:
        flags.append("low_rhythm_evidence_quality")
    drum_source_quality = _clamp(
        float(((drum_analysis or {}).get("confidence") or {}).get("overall", 0.75) or 0.0)
    )
    fallback_source = (drum_analysis or {}).get("detector_mode") == "fallback"
    if fallback_source:
        flags.append("rhythm_uses_spectral_drum_proxy")

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
        global_score, matched = _aggregate(scores)
        song_coverage = len(matched) / max(analyzed, 1)
        best_window = best_by_name.get(name)
        stable_score = float((best_window or {}).get("stable_score", global_score))
        score = _clamp(0.55 * global_score + 0.30 * stable_score + 0.15 * song_coverage)
        matched_by_name[name] = matched
        features[name] = make_feature_evidence(
            score,
            threshold=0.58,
            confidence=quality,
            measurement_confidence=quality,
            source_quality=drum_source_quality,
            estimator_quality=0.84,
            reliability_cap=0.55 if fallback_source else 1.0,
            coverage=max(song_coverage, 1.0 / max(analyzed, 1)),
            stability=float((best_window or {}).get("stability", 0.5)),
            calibration_status="proxy_limited" if fallback_source else "provisional",
            quality_flags=flags,
            sources=["bpm", "beat_grid", "downbeat_grid", "drum_transcription"],
            analysis_method=method,
            time_ranges=_ranges(matched, bars),
            evidence={
                "bars_analyzed": analyzed,
                "grid_resolution": 16,
                "template": templates[name],
                "mean_template_score": round(global_score, 4),
                "global_score": round(global_score, 4),
                "stable_window_score": round(stable_score, 4),
                "stable_song_coverage": round(song_coverage, 4),
                "best_stable_window": best_window,
                "window_sizes_bars": [4, 8, 16],
                "source_detector_mode": (drum_analysis or {}).get("detector_mode", "unknown"),
            },
            raw_measurements={
                "mean_template_score": round(global_score, 4),
                "matched_bar_count": len(matched),
                "bars_analyzed": analyzed,
            },
        )
    features["swing"] = make_feature_evidence(
        swing_score,
        threshold=0.55,
        confidence=_clamp(len(offbeat_delays) / 16.0),
        measurement_confidence=_clamp(len(offbeat_delays) / 16.0),
        source_quality=drum_source_quality,
        estimator_quality=0.75,
        quality_flags=flags,
        sources=["beat_grid", "drum_transcription"],
        analysis_method="microtiming_offbeat_delay_v1",
        evidence={
            "median_offbeat_delay_beats": round(median_delay, 4),
            "offbeat_event_count": len(offbeat_delays),
            "timing_consistency": round(consistency, 4),
        },
    )
    boundary_common = {
        "bars_analyzed": analyzed,
        "grid_resolution": 16,
        "source_detector_mode": (drum_analysis or {}).get("detector_mode", "unknown"),
    }
    features["four_floor_stability"] = make_feature_evidence(
        boundary["four_floor_stability_score"],
        threshold=0.60,
        confidence=quality,
        source_quality=drum_source_quality,
        estimator_quality=0.86,
        coverage=boundary["four_floor_bar_coverage"],
        stability=boundary["four_floor_cross_bar_stability"],
        reliability_cap=0.55 if fallback_source else 1.0,
        calibration_status="proxy_limited" if fallback_source else "provisional",
        quality_flags=flags,
        sources=["beat_grid", "downbeat_grid", "drum_transcription"],
        analysis_method="four_floor_cross_bar_stability_v1",
        evidence={
            **boundary_common,
            "bar_coverage": boundary["four_floor_bar_coverage"],
            "continuity": boundary["four_floor_continuity"],
            "cross_bar_stability": boundary["four_floor_cross_bar_stability"],
            "semantic_rule": "four kick positions must persist across bars; a short favourable window is insufficient",
        },
    )
    open_hat_cap = 1.0 if explicit_open_hat_count else (0.55 if fallback_source else 0.68)
    features["offbeat_open_hat"] = make_feature_evidence(
        boundary["offbeat_hat_score"],
        threshold=0.58,
        confidence=quality,
        source_quality=drum_source_quality,
        estimator_quality=0.82 if explicit_open_hat_count else 0.58,
        coverage=boundary["offbeat_hat_bar_coverage"],
        stability=_clamp(analyzed / 8.0),
        reliability_cap=open_hat_cap,
        calibration_status="provisional" if explicit_open_hat_count else "hat_family_proxy_only",
        quality_flags=flags + ([] if explicit_open_hat_count else ["open_hat_subtype_unavailable"]),
        sources=["beat_grid", "downbeat_grid", "drum_transcription"],
        analysis_method="offbeat_open_hat_grid_v1",
        evidence={
            **boundary_common,
            "target_steps": [2, 6, 10, 14],
            "bar_coverage": boundary["offbeat_hat_bar_coverage"],
            "explicit_open_hat_event_count": explicit_open_hat_count,
            "semantic_rule": "offbeat hat-family events; open-hat identity is confirmed only when a dedicated transcriber preserves the subtype",
        },
    )
    features["timing_quantization"] = make_feature_evidence(
        boundary["quantization_score"],
        threshold=0.62,
        confidence=_clamp(boundary["timing_event_count"] / 32.0),
        source_quality=drum_source_quality,
        estimator_quality=0.82,
        coverage=_clamp(boundary["timing_event_count"] / max(32.0, analyzed * 4.0)),
        stability=_clamp(analyzed / 8.0),
        reliability_cap=0.55 if fallback_source else 1.0,
        calibration_status="proxy_limited" if fallback_source else "provisional",
        quality_flags=flags,
        sources=["downbeat_grid", "drum_transcription"],
        analysis_method="sixteenth_grid_timing_deviation_v1",
        evidence={
            **boundary_common,
            "event_count": boundary["timing_event_count"],
            "median_grid_error_ms": boundary["median_grid_error_ms"],
            "p90_grid_error_ms": boundary["p90_grid_error_ms"],
            "semantic_rule": "absolute event deviation from the nearest local sixteenth-note position",
        },
    )
    features["drum_loop_repetition"] = make_feature_evidence(
        boundary["loop_score"],
        threshold=0.60,
        confidence=quality,
        source_quality=drum_source_quality,
        estimator_quality=0.84,
        coverage=boundary["loop_bar_coverage"],
        stability=_clamp(analyzed / 8.0),
        reliability_cap=0.55 if fallback_source else 1.0,
        calibration_status="proxy_limited" if fallback_source else "provisional",
        quality_flags=flags,
        sources=["downbeat_grid", "drum_transcription"],
        analysis_method="drum_pattern_recurrence_v1",
        evidence={
            **boundary_common,
            "bar_coverage": boundary["loop_bar_coverage"],
            "recurrence_by_lag_bars": boundary["recurrence_by_lag_bars"],
            "semantic_rule": "kick, snare and hat pattern recurrence at one, two or four bars",
        },
    )
    features["drum_machine_consistency"] = make_feature_evidence(
        boundary["drum_machine_score"],
        threshold=0.65,
        confidence=quality,
        source_quality=drum_source_quality,
        estimator_quality=0.62,
        coverage=min(boundary["loop_bar_coverage"], _clamp(boundary["timing_event_count"] / 32.0)),
        stability=_clamp(analyzed / 8.0),
        reliability_cap=0.68,
        calibration_status="semantic_candidate",
        quality_flags=flags + ["drum_machine_identity_not_directly_observed"],
        sources=["downbeat_grid", "drum_transcription"],
        analysis_method="drum_machine_consistency_candidate_v1",
        evidence={
            **boundary_common,
            "timing_quantization_score": round(boundary["quantization_score"], 4),
            "loop_repetition_score": round(boundary["loop_score"], 4),
            "intensity_consistency": boundary["intensity_consistency"],
            "semantic_rule": "candidate only: highly quantized, repeating and dynamically consistent drums; does not identify a specific machine",
        },
    )

    return {
        "version": RHYTHM_FEATURE_VERSION,
        "status": "ready" if quality >= 0.55 else "degraded",
        "features": features,
        "windows": windows,
        "confidence": round(quality, 4),
        "quality_flags": flags,
    }
