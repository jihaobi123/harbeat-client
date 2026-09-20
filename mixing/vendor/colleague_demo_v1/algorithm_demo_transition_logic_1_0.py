#!/usr/bin/env python3
"""Render Future Bass 6 with DEMO transition logic 1.0."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from itertools import permutations
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harbeat import (  # noqa: E402
    TrackPreprocessBundle,
    read_library_index,
    read_track_preprocess_from_manifest_key,
    resolve_storage_key,
)
from harbeat.cue_points import bar_duration_seconds  # noqa: E402
from harbeat.drums import drum_overlap_score  # noqa: E402
from harbeat.key_compatibility import harmonic_compatibility_score  # noqa: E402
from harbeat.phrase_mix import snap_to_bar  # noqa: E402


DEFAULT_ROOT = Path("/Users/pineapple/Desktop/future_bass_6_bundle_20260916_v1")
DEFAULT_INDEX = "published/indexes/future_bass_demo_6_v1.json"
DEFAULT_VOCAL_INDEX = "published/indexes/future_bass_demo_6_vocal_activity_v1.json"
DEFAULT_OUTPUT_ROOT = Path("/Users/pineapple/Documents/harbeat/outputs")
SAMPLE_RATE = 44_100
RENDER_GAIN = 0.76
FINAL_FADE_SECONDS = 7.0
VOCAL_PAD_MS = 300
VOCAL_PRESENT_MIN_MS = 500
VOCAL_PRESENT_MIN_RATIO = 0.05
CASE_3_A_CHORUS_BARS = 4

CHORUS_LABELS = {"chorus", "hook", "refrain", "drop", "副歌"}
INTRO_LABELS = {"intro", "前奏"}


@dataclass(frozen=True)
class SegmentWindow:
    start_ms: int
    end_ms: int
    bars: int
    reason: str


@dataclass(frozen=True)
class DemoTransition:
    position: int
    from_track_id: str
    to_track_id: str
    case: str
    entry_rate: float
    a_chorus_start_ms: int
    a_exit_ms: int
    a_chorus_bars: int
    a_transition_start_ms: int
    b_intro_start_ms: int
    b_intro_end_ms: int
    b_intro_bars: int
    b_entry_ms: int
    incoming_source_overlap_ms: int
    overlap_seconds: float
    restore_half_bar_seconds: float
    a_vocal_ratio: float
    b_vocal_ratio: float
    both_vocal: bool
    score: float
    reason: str


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def _ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise RuntimeError("ffmpeg is not installed or not on PATH")
    return path


def _ffprobe() -> str:
    path = shutil.which("ffprobe")
    if not path:
        raise RuntimeError("ffprobe is not installed or not on PATH")
    return path


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_audio(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            _ffprobe(),
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=sample_rate,channels",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def audio_duration_seconds(path: Path) -> float:
    return float(probe_audio(path)["format"]["duration"])


def _label(value: str | None) -> str:
    return (value or "").strip().lower()


def _sections(bundle: TrackPreprocessBundle):
    return tuple(sorted(bundle.track.sections, key=lambda section: section.start_time_seconds))


def _bar_count(bundle: TrackPreprocessBundle, start_ms: int, end_ms: int) -> int:
    if end_ms <= start_ms:
        return 0
    bars = round(((end_ms - start_ms) / 1000.0) / bar_duration_seconds(bundle.track.bpm))
    return max(1, int(bars))


def _snap_ms(bundle: TrackPreprocessBundle, time_ms: int, mode: str = "nearest") -> int:
    return int(round(snap_to_bar(bundle.track, time_ms / 1000.0, mode=mode) * 1000))


def first_intro_window(bundle: TrackPreprocessBundle) -> SegmentWindow:
    sections = _sections(bundle)
    if not sections or _label(sections[0].name) not in INTRO_LABELS:
        first_nonzero_bar = _snap_ms(bundle, 0, mode="ceil")
        return SegmentWindow(
            0,
            max(0, first_nonzero_bar),
            0,
            "fallback: no labelled intro before the first non-intro section",
        )

    start_ms = int(round(max(0.0, sections[0].start_time_seconds) * 1000))
    end_seconds = sections[0].end_time_seconds
    for section in sections[1:]:
        if _label(section.name) not in INTRO_LABELS:
            break
        if section.start_time_seconds <= end_seconds + 0.100:
            end_seconds = max(end_seconds, section.end_time_seconds)
        else:
            break
    end_ms = _snap_ms(bundle, int(round(end_seconds * 1000)), mode="nearest")
    return SegmentWindow(
        start_ms,
        max(start_ms, end_ms),
        _bar_count(bundle, start_ms, max(start_ms, end_ms)),
        "contiguous labelled intro snapped to beat grid",
    )


def first_chorus_block(bundle: TrackPreprocessBundle) -> SegmentWindow:
    sections = _sections(bundle)
    for index, section in enumerate(sections):
        if _label(section.name) not in CHORUS_LABELS:
            continue
        start_seconds = section.start_time_seconds
        end_seconds = section.end_time_seconds
        for next_section in sections[index + 1 :]:
            if _label(next_section.name) not in CHORUS_LABELS:
                break
            if next_section.start_time_seconds <= end_seconds + 0.100:
                end_seconds = max(end_seconds, next_section.end_time_seconds)
            else:
                break
        start_ms = _snap_ms(bundle, int(round(start_seconds * 1000)), mode="nearest")
        end_ms = _snap_ms(bundle, int(round(end_seconds * 1000)), mode="nearest")
        return SegmentWindow(
            start_ms,
            max(start_ms + 1, end_ms),
            _bar_count(bundle, start_ms, max(start_ms + 1, end_ms)),
            "first contiguous chorus block snapped to beat grid",
        )

    duration_ms = int((bundle.track.duration_seconds or 0.0) * 1000)
    fallback_end = _snap_ms(bundle, min(duration_ms, 70_000), mode="nearest")
    return SegmentWindow(
        0,
        max(1, fallback_end),
        _bar_count(bundle, 0, max(1, fallback_end)),
        "fallback: no chorus label found, using early bar-snapped window",
    )


def _merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        else:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
    return merged


def vocal_overlap_ms(
    intervals: list[tuple[int, int]] | None,
    start_ms: int,
    end_ms: int,
    *,
    pad_ms: int = VOCAL_PAD_MS,
) -> int:
    if not intervals or end_ms <= start_ms:
        return 0
    total = 0
    for start, end in _merge_intervals([(max(0, s - pad_ms), e + pad_ms) for s, e in intervals]):
        left = max(start_ms, start)
        right = min(end_ms, end)
        if right > left:
            total += right - left
    return min(total, end_ms - start_ms)


def vocal_ratio(intervals: list[tuple[int, int]] | None, start_ms: int, end_ms: int) -> float:
    if end_ms <= start_ms:
        return 0.0
    return vocal_overlap_ms(intervals, start_ms, end_ms) / (end_ms - start_ms)


def vocal_present(intervals: list[tuple[int, int]] | None, start_ms: int, end_ms: int) -> bool:
    overlap = vocal_overlap_ms(intervals, start_ms, end_ms)
    return overlap >= VOCAL_PRESENT_MIN_MS and vocal_ratio(intervals, start_ms, end_ms) >= VOCAL_PRESENT_MIN_RATIO


def load_bundles(root: Path, index_storage_key: str, verify_assets: bool) -> tuple[list[TrackPreprocessBundle], list[str]]:
    index = read_library_index(root=root, index_storage_key=index_storage_key)
    bundles: list[TrackPreprocessBundle] = []
    warnings: list[str] = []
    for item in index.items:
        style = item.style_labels[0] if item.style_labels else item.source_collection or "future_bass"
        bundle = read_track_preprocess_from_manifest_key(
            item.manifest_storage_key,
            root=root,
            expected_track_id=item.track_id,
            expected_analysis_run_id=item.analysis_run_id,
            style=style,
            title=item.title,
            artist=item.artist,
            allow_degraded=True,
            verify_assets=verify_assets,
        )
        bundles.append(bundle)
        if bundle.manifest.get("status") == "degraded":
            warnings.append(
                f"{bundle.track.title}: degraded; flags={', '.join(bundle.quality_flags) or 'none'}"
            )
    return bundles, warnings


def load_vocal_activity(
    *,
    root: Path,
    vocal_index_storage_key: str,
    expected_runs: set[tuple[str, str]],
) -> tuple[dict[str, list[tuple[int, int]]], dict[str, Mapping[str, Any]], list[str]]:
    index_path = root / vocal_index_storage_key
    if not index_path.exists():
        return {}, {}, [f"vocal activity index not found: {index_path}"]

    index = json.loads(index_path.read_text(encoding="utf-8"))
    reports: dict[str, list[tuple[int, int]]] = {}
    metadata: dict[str, Mapping[str, Any]] = {}
    warnings: list[str] = []
    for item in index.get("items", []):
        if not isinstance(item, Mapping):
            continue
        track_id = str(item.get("track_id") or "")
        analysis_run_id = str(item.get("analysis_run_id") or "")
        if (track_id, analysis_run_id) not in expected_runs:
            warnings.append(
                f"{track_id}: vocal activity skipped because track_id + analysis_run_id "
                "does not match the loaded manifest set"
            )
            continue
        if item.get("status") != "ready":
            warnings.append(f"{track_id}: vocal activity status={item.get('status')}")
            continue

        report_path = resolve_storage_key(root, str(item.get("vocal_activity_storage_key") or ""))
        if not report_path.exists():
            warnings.append(f"{track_id}: vocal activity report missing at {report_path}")
            continue
        expected_hash = str(item.get("vocal_activity_sha256") or "")
        if expected_hash and _sha256_file(report_path) != expected_hash:
            warnings.append(f"{track_id}: vocal activity report sha256 mismatch")
            continue

        manifest_path = resolve_storage_key(root, str(item.get("manifest_storage_key") or ""))
        expected_manifest_hash = str(item.get("manifest_sha256") or "")
        if manifest_path.exists() and expected_manifest_hash and _sha256_file(manifest_path) != expected_manifest_hash:
            warnings.append(f"{track_id}: manifest sha256 mismatch for vocal activity binding")
            continue

        report = json.loads(report_path.read_text(encoding="utf-8"))
        intervals = [
            (int(interval.get("start_ms") or 0), int(interval.get("end_ms") or 0))
            for interval in report.get("intervals") or []
            if isinstance(interval, Mapping)
        ]
        reports[track_id] = _merge_intervals(intervals)
        metadata[track_id] = {
            "coverage_ratio": report.get("coverage_ratio"),
            "active_duration_ms": report.get("active_duration_ms"),
            "needs_review": report.get("needs_review"),
            "quality_flags": report.get("quality_flags") or [],
        }
    return reports, metadata, warnings


def transition_for_pair(
    position: int,
    left: TrackPreprocessBundle,
    right: TrackPreprocessBundle,
    vocal_reports: dict[str, list[tuple[int, int]]],
) -> DemoTransition:
    a_chorus = first_chorus_block(left)
    b_intro = first_intro_window(right)
    a_bar_seconds = bar_duration_seconds(left.track.bpm)
    b_bar_seconds = bar_duration_seconds(right.track.bpm)
    rate = left.track.bpm / right.track.bpm

    if a_chorus.bars < b_intro.bars:
        case = "case_3_a_chorus_shorter_than_b_intro"
        transition_bars = min(CASE_3_A_CHORUS_BARS, max(1, a_chorus.bars))
        a_transition_start_ms = _snap_ms(
            left,
            int(round(a_chorus.end_ms - transition_bars * a_bar_seconds * 1000)),
            mode="nearest",
        )
        b_entry_raw = b_intro.end_ms - int(round(transition_bars * b_bar_seconds * 1000))
        b_entry_ms = _snap_ms(right, max(b_intro.start_ms, b_entry_raw), mode="nearest")
        reason = (
            "A first chorus is shorter than B intro; use the last 4 bars of A chorus "
            "and the matching last bars of B intro"
        )
    else:
        if a_chorus.bars == b_intro.bars:
            case = "case_1_equal_chorus_and_intro_bars"
            reason = "A first chorus and B intro have equal bar counts; use normal aligned crossfade"
        else:
            case = "case_2_a_chorus_longer_than_b_intro"
            reason = "A first chorus is longer than B intro; B intro first beat is the entry point"
        b_entry_ms = b_intro.start_ms
        incoming_source_overlap_ms = max(1, b_intro.end_ms - b_entry_ms)
        overlap_seconds = (incoming_source_overlap_ms / 1000.0) / rate
        a_transition_start_ms = _snap_ms(
            left,
            int(round(a_chorus.end_ms - overlap_seconds * 1000)),
            mode="nearest",
        )

    incoming_source_overlap_ms = max(1, b_intro.end_ms - b_entry_ms)
    overlap_seconds = (incoming_source_overlap_ms / 1000.0) / rate
    a_transition_start_ms = max(a_chorus.start_ms, min(a_transition_start_ms, a_chorus.end_ms - 1))
    a_vocal = vocal_ratio(vocal_reports.get(left.track.id), a_transition_start_ms, a_chorus.end_ms)
    b_vocal = vocal_ratio(vocal_reports.get(right.track.id), b_entry_ms, b_intro.end_ms)
    both_vocal = vocal_present(
        vocal_reports.get(left.track.id), a_transition_start_ms, a_chorus.end_ms
    ) and vocal_present(vocal_reports.get(right.track.id), b_entry_ms, b_intro.end_ms)

    tempo_shift = abs(rate - 1.0)
    key_score = harmonic_compatibility_score(left.track.key, right.track.key)
    drum_score = drum_overlap_score(left.track.drum_profile, right.track.drum_profile)
    case_cost = 0.0 if case.startswith("case_1") else 0.08 if case.startswith("case_2") else 0.18
    vocal_cost = (a_vocal * b_vocal * 2.0) + (0.18 if both_vocal else 0.0)
    score = (
        1.0
        - tempo_shift * 2.6
        - case_cost
        - vocal_cost
        + key_score * 0.13
        + drum_score * 0.17
    )

    return DemoTransition(
        position=position,
        from_track_id=left.track.id,
        to_track_id=right.track.id,
        case=case,
        entry_rate=rate,
        a_chorus_start_ms=a_chorus.start_ms,
        a_exit_ms=a_chorus.end_ms,
        a_chorus_bars=a_chorus.bars,
        a_transition_start_ms=a_transition_start_ms,
        b_intro_start_ms=b_intro.start_ms,
        b_intro_end_ms=b_intro.end_ms,
        b_intro_bars=b_intro.bars,
        b_entry_ms=b_entry_ms,
        incoming_source_overlap_ms=incoming_source_overlap_ms,
        overlap_seconds=overlap_seconds,
        restore_half_bar_seconds=a_bar_seconds / 2.0,
        a_vocal_ratio=a_vocal,
        b_vocal_ratio=b_vocal,
        both_vocal=both_vocal,
        score=score,
        reason=reason,
    )


def order_tracks(
    bundles: list[TrackPreprocessBundle],
    vocal_reports: dict[str, list[tuple[int, int]]],
) -> tuple[list[TrackPreprocessBundle], list[DemoTransition], float]:
    scored_orders: list[tuple[float, tuple[int, ...], list[DemoTransition]]] = []
    for order in permutations(range(len(bundles))):
        transitions = [
            transition_for_pair(
                index + 1,
                bundles[order[index]],
                bundles[order[index + 1]],
                vocal_reports,
            )
            for index in range(len(order) - 1)
        ]
        start_bpm = bundles[order[0]].track.bpm
        start_score = max(0.0, 104.0 - start_bpm) / 120.0
        trend_score = sum(
            0.025
            if bundles[order[index + 1]].track.bpm >= bundles[order[index]].track.bpm
            else -0.045
            for index in range(len(order) - 1)
        )
        total = start_score + trend_score + sum(item.score for item in transitions)
        scored_orders.append((total, order, transitions))

    scored_orders.sort(
        key=lambda item: (
            -item[0],
            [bundles[index].track.title.lower() for index in item[1]],
        )
    )
    total, order, transitions = scored_orders[0]
    ordered = [bundles[index] for index in order]
    renumbered = [
        DemoTransition(
            position=index + 1,
            from_track_id=transition.from_track_id,
            to_track_id=transition.to_track_id,
            case=transition.case,
            entry_rate=transition.entry_rate,
            a_chorus_start_ms=transition.a_chorus_start_ms,
            a_exit_ms=transition.a_exit_ms,
            a_chorus_bars=transition.a_chorus_bars,
            a_transition_start_ms=transition.a_transition_start_ms,
            b_intro_start_ms=transition.b_intro_start_ms,
            b_intro_end_ms=transition.b_intro_end_ms,
            b_intro_bars=transition.b_intro_bars,
            b_entry_ms=transition.b_entry_ms,
            incoming_source_overlap_ms=transition.incoming_source_overlap_ms,
            overlap_seconds=transition.overlap_seconds,
            restore_half_bar_seconds=transition.restore_half_bar_seconds,
            a_vocal_ratio=transition.a_vocal_ratio,
            b_vocal_ratio=transition.b_vocal_ratio,
            both_vocal=transition.both_vocal,
            score=transition.score,
            reason=transition.reason,
        )
        for index, transition in enumerate(transitions)
    ]
    return ordered, renumbered, total


def _atempo_chain(rate: float) -> str:
    values: list[float] = []
    remaining = rate
    while remaining > 2.0:
        values.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        values.append(0.5)
        remaining /= 0.5
    values.append(remaining)
    return ",".join(f"atempo={value:.6f}" for value in values)


def _part_chain(
    *,
    source_label: str,
    start_s: float,
    end_s: float,
    output_label: str,
    rate: float = 1.0,
    eq: str = "",
) -> str | None:
    if end_s <= start_s + 0.001:
        return None
    chain = f"{source_label}atrim=start={start_s:.3f}:end={end_s:.3f},asetpts=PTS-STARTPTS"
    if abs(rate - 1.0) > 0.002:
        chain += f",{_atempo_chain(rate)}"
    if eq:
        chain += f",{eq}"
    chain += f"[{output_label}]"
    return chain


def render_segment(
    *,
    ffmpeg: str,
    source_path: Path,
    output_path: Path,
    entry_ms: int,
    exit_ms: int,
    incoming_source_overlap_ms: int,
    incoming_rate: float,
    outgoing_overlap_seconds: float,
    mid_duck: bool,
    restore_half_bar_seconds: float,
    final_track: bool,
) -> None:
    start_s = entry_ms / 1000.0
    end_s = max(start_s + 1.0, exit_ms / 1000.0)
    head_end_s = min(end_s, start_s + incoming_source_overlap_ms / 1000.0)
    restore_source_s = min(
        max(0.0, head_end_s - start_s),
        max(0.0, restore_half_bar_seconds * max(incoming_rate, 0.001)),
    )
    restore_start_s = head_end_s - restore_source_s
    tail_start_s = max(head_end_s, end_s - max(0.0, outgoing_overlap_seconds))

    incoming_eq = "bass=g=-7:f=140,treble=g=1.2:f=3600"
    ducked_eq = incoming_eq
    if mid_duck:
        ducked_eq += ",equalizer=f=1200:t=q:w=1.05:g=-5.0"
    tail_eq = "bass=g=-9:f=140,treble=g=-1.4:f=3600"

    filter_lines: list[str] = []
    part_labels: list[str] = []
    rendered_duration = 0.0

    def add_simple(
        start: float,
        end: float,
        *,
        label: str,
        rate: float = 1.0,
        eq: str = "",
    ) -> None:
        nonlocal rendered_duration
        chain = _part_chain(
            source_label="[0:a]",
            start_s=start,
            end_s=end,
            output_label=label,
            rate=rate,
            eq=eq,
        )
        if chain is None:
            return
        filter_lines.append(chain)
        part_labels.append(f"[{label}]")
        rendered_duration += (end - start) / rate if abs(rate - 1.0) > 0.002 else end - start

    add_simple(start_s, restore_start_s, label="head", rate=incoming_rate, eq=ducked_eq)

    if restore_start_s < head_end_s - 0.001:
        restore_output_s = (head_end_s - restore_start_s) / max(incoming_rate, 0.001)
        duck_chain = _part_chain(
            source_label="[0:a]",
            start_s=restore_start_s,
            end_s=head_end_s,
            output_label="restore_duck",
            rate=incoming_rate,
            eq=ducked_eq,
        )
        normal_chain = _part_chain(
            source_label="[0:a]",
            start_s=restore_start_s,
            end_s=head_end_s,
            output_label="restore_full",
            rate=incoming_rate,
            eq="",
        )
        if duck_chain and normal_chain:
            filter_lines.extend([duck_chain, normal_chain])
            filter_lines.append(
                f"[restore_duck][restore_full]acrossfade=d={restore_output_s:.3f}:c1=tri:c2=tri[restore]"
            )
            part_labels.append("[restore]")
            rendered_duration += restore_output_s

    add_simple(head_end_s, tail_start_s, label="body")
    add_simple(tail_start_s, end_s, label="tail", eq=tail_eq)

    if not part_labels:
        add_simple(start_s, end_s, label="body")

    if len(part_labels) == 1:
        output_chain = (
            f"{part_labels[0]}volume={RENDER_GAIN:.4f},"
            "aresample=44100,aformat=channel_layouts=stereo"
        )
    else:
        output_chain = (
            f"{''.join(part_labels)}concat=n={len(part_labels)}:v=0:a=1,"
            f"volume={RENDER_GAIN:.4f},aresample=44100,aformat=channel_layouts=stereo"
        )
    if final_track:
        fade_start = max(0.0, rendered_duration - FINAL_FADE_SECONDS)
        output_chain += f",afade=t=out:st={fade_start:.3f}:d={FINAL_FADE_SECONDS:.3f}"
    output_chain += "[a]"
    filter_lines.append(output_chain)

    _run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source_path),
            "-filter_complex",
            ";".join(filter_lines),
            "-map",
            "[a]",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )


def render_crossfaded_mix(
    ffmpeg: str,
    segment_paths: list[Path],
    overlaps: list[float],
    output_path: Path,
) -> tuple[list[float], float]:
    inputs: list[str] = []
    for path in segment_paths:
        inputs.extend(["-i", str(path)])

    filters: list[str] = []
    previous = "[0:a]"
    for index, overlap in enumerate(overlaps, 1):
        label = f"[xf{index}]"
        filters.append(f"{previous}[{index}:a]acrossfade=d={overlap:.3f}:c1=tri:c2=tri{label}")
        previous = label
    filters.append(f"{previous}alimiter=limit=0.96:level=false[out]")

    _run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            *inputs,
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[out]",
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
    )

    transition_times: list[float] = []
    elapsed = 0.0
    for index, path in enumerate(segment_paths[:-1]):
        elapsed += audio_duration_seconds(path)
        transition_times.append(elapsed - overlaps[index])
        elapsed -= overlaps[index]
    return transition_times, audio_duration_seconds(output_path)


def render_snippets(ffmpeg: str, mixtape_path: Path, transition_times: list[float], snippets_dir: Path) -> list[Path]:
    snippets_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index, transition_time in enumerate(transition_times, 1):
        start = max(0.0, transition_time - 20.0)
        output = snippets_dir / f"transition_{index:02d}.wav"
        _run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{start:.3f}",
                "-i",
                str(mixtape_path),
                "-t",
                "52.000",
                "-ar",
                str(SAMPLE_RATE),
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(output),
            ]
        )
        paths.append(output)
    return paths


def _algorithm_markdown() -> str:
    return "\n".join(
        [
            "# Future Bass DEMO Transition Logic 1.0",
            "",
            "- Six same-style `future_bass` tracks are ordered by a small exhaustive route search.",
            "- Each song segment starts at its selected source entry and ends at the first contiguous chorus block end.",
            "- For each A -> B transition, B's labelled intro end is aligned to A's first chorus end.",
            "- B intro audio is tempo-matched to A for the incoming overlap with `atempo = A_bpm / B_bpm`.",
            "- Case 1: if A first chorus bars equal B intro bars, use the full B intro as the transition.",
            "- Case 2: if A first chorus bars exceed B intro bars, use the full B intro; its first beat is B's entry.",
            "- Case 3: if A first chorus bars are fewer than B intro bars, use the final 4 bars of A's chorus and the matching final B intro bars.",
            "- A fades out and B fades in with a linear master EQ crossfade; A tail has reduced low/high EQ.",
            "- If both A's transition chorus window and B's intro window contain vocal activity, B's mid band is attenuated, then restored over the final half bar before the out point.",
            "- Source paths are resolved from manifest `storage_key` values under `HARBEAT_PREPROCESS_ROOT`; `source_storage_key` is not used for audio.",
            "- Degraded and `needs_review` flags are preserved in `mix_plan.json`; this renderer does not claim human-verified analysis accuracy.",
        ]
    ) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--index", default=DEFAULT_INDEX)
    parser.add_argument("--vocal-index", default=DEFAULT_VOCAL_INDEX)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--verify-assets", action="store_true")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    ffmpeg = _ffmpeg()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = (args.output_root / f"future_bass_6_demo_logic_1_0_{stamp}").resolve()
    segments_dir = output_dir / "segments"
    snippets_dir = output_dir / "transition_snippets"
    segments_dir.mkdir(parents=True, exist_ok=True)

    bundles, warnings = load_bundles(root, args.index, args.verify_assets)
    expected_runs = {
        (str(bundle.pointer.get("track_id") or ""), str(bundle.pointer.get("analysis_run_id") or ""))
        for bundle in bundles
    }
    vocal_reports, vocal_metadata, vocal_warnings = load_vocal_activity(
        root=root,
        vocal_index_storage_key=args.vocal_index,
        expected_runs=expected_runs,
    )
    warnings.extend(vocal_warnings)

    ordered, transitions, route_score = order_tracks(bundles, vocal_reports)
    overlaps = [transition.overlap_seconds for transition in transitions]
    transition_by_from = {transition.from_track_id: transition for transition in transitions}
    transition_by_to = {transition.to_track_id: transition for transition in transitions}

    segment_paths: list[Path] = []
    track_rows: list[dict[str, Any]] = []
    for index, bundle in enumerate(ordered):
        incoming = transition_by_to.get(bundle.track.id)
        outgoing = transition_by_from.get(bundle.track.id)
        chorus = first_chorus_block(bundle)
        intro = first_intro_window(bundle)
        entry_ms = incoming.b_entry_ms if incoming else 0
        exit_ms = outgoing.a_exit_ms if outgoing else chorus.end_ms
        incoming_source_overlap_ms = incoming.incoming_source_overlap_ms if incoming else 0
        incoming_rate = incoming.entry_rate if incoming else 1.0
        outgoing_overlap_seconds = outgoing.overlap_seconds if outgoing else 0.0
        source_path = resolve_storage_key(root, bundle.assets["master"].storage_key)
        segment_path = segments_dir / f"{index + 1:02d}_{bundle.track.id}.wav"

        render_segment(
            ffmpeg=ffmpeg,
            source_path=source_path,
            output_path=segment_path,
            entry_ms=entry_ms,
            exit_ms=exit_ms,
            incoming_source_overlap_ms=incoming_source_overlap_ms,
            incoming_rate=incoming_rate,
            outgoing_overlap_seconds=outgoing_overlap_seconds,
            mid_duck=bool(incoming and incoming.both_vocal),
            restore_half_bar_seconds=incoming.restore_half_bar_seconds if incoming else 0.0,
            final_track=index == len(ordered) - 1,
        )
        segment_paths.append(segment_path)

        track_rows.append(
            {
                "position": index + 1,
                "track_id": bundle.track.id,
                "title": bundle.track.title,
                "artist": bundle.track.artist,
                "status": bundle.manifest.get("status"),
                "quality_modules": bundle.manifest.get("quality", {}).get("modules", {}),
                "quality_flags": list(bundle.quality_flags),
                "bpm": bundle.track.bpm,
                "key": bundle.track.key,
                "intro_start_ms": intro.start_ms,
                "intro_end_ms": intro.end_ms,
                "intro_bars": intro.bars,
                "first_chorus_start_ms": chorus.start_ms,
                "first_chorus_end_ms": chorus.end_ms,
                "first_chorus_bars": chorus.bars,
                "render_entry_ms": entry_ms,
                "render_exit_ms": exit_ms,
                "incoming_rate": incoming_rate,
                "incoming_mid_duck": bool(incoming and incoming.both_vocal),
                "rendered_segment": str(segment_path),
                "master_storage_key": bundle.assets["master"].storage_key,
                "vocal_activity": vocal_metadata.get(bundle.track.id, {}),
            }
        )

    mixtape_path = output_dir / "mixtape_demo_logic_1_0.wav"
    transition_times, duration = render_crossfaded_mix(ffmpeg, segment_paths, overlaps, mixtape_path)
    snippet_paths = render_snippets(ffmpeg, mixtape_path, transition_times, snippets_dir)
    probe = probe_audio(mixtape_path)

    transition_rows: list[dict[str, Any]] = []
    for index, transition in enumerate(transitions):
        left = ordered[index]
        right = ordered[index + 1]
        transition_rows.append(
            {
                "position": index + 1,
                "from": f"{left.track.artist} - {left.track.title}",
                "to": f"{right.track.artist} - {right.track.title}",
                "case": transition.case,
                "entry_rate": round(transition.entry_rate, 6),
                "overlap_seconds": round(transition.overlap_seconds, 4),
                "transition_time_seconds": transition_times[index],
                "snippet_wav": str(snippet_paths[index]),
                "a_first_chorus_start_ms": transition.a_chorus_start_ms,
                "a_out_point_first_chorus_end_ms": transition.a_exit_ms,
                "a_chorus_bars": transition.a_chorus_bars,
                "a_transition_start_ms": transition.a_transition_start_ms,
                "b_intro_start_ms": transition.b_intro_start_ms,
                "b_intro_end_ms": transition.b_intro_end_ms,
                "b_intro_bars": transition.b_intro_bars,
                "b_entry_ms": transition.b_entry_ms,
                "incoming_source_overlap_ms": transition.incoming_source_overlap_ms,
                "both_vocal_detected": transition.both_vocal,
                "a_transition_vocal_ratio": round(transition.a_vocal_ratio, 4),
                "b_intro_vocal_ratio": round(transition.b_vocal_ratio, 4),
                "mid_duck_policy": (
                    "B mid band -5dB, restored over the final half bar"
                    if transition.both_vocal
                    else "no vocal-conflict mid duck"
                ),
                "score": round(transition.score, 4),
                "reason": transition.reason,
            }
        )

    plan = {
        "schema_name": "harbeat_offline_mixtape_plan",
        "schema_version": "0.5.0",
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "input": {
            "root": str(root),
            "index_storage_key": args.index,
            "vocal_activity_index": args.vocal_index,
            "total_tracks": len(ordered),
        },
        "policy": {
            "version": "future_bass_demo_transition_logic_1_0",
            "allow_degraded": True,
            "route_strategy": "exhaustive 6-track search using demo transition costs, vocal conflict cost, BPM adjustment cost, harmonic compatibility, and drum overlap",
            "segment_strategy": "each track renders from selected intro entry to first contiguous chorus block end",
            "out_point_strategy": "B intro end / B verse first beat is aligned to A first chorus end",
            "tempo_strategy": "incoming B intro is rendered at A_bpm / B_bpm; body returns to original tempo after the intro boundary",
            "mix_strategy": "linear master EQ crossfade with B mid duck when both sides contain vocal activity",
            "render_gain": RENDER_GAIN,
            "vocal_detection_note": "Silero VAD on separated vocals is used as needs_review guidance, not human-verified lyric timing",
        },
        "route_score": route_score,
        "warnings": warnings,
        "tracks": track_rows,
        "transitions": transition_rows,
        "outputs": {
            "output_dir": str(output_dir),
            "mixtape_wav": str(mixtape_path),
            "segments_dir": str(segments_dir),
            "transition_snippets_dir": str(snippets_dir),
            "duration_seconds": duration,
            "ffprobe": probe,
        },
    }
    (output_dir / "mix_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Future Bass 6 DEMO Logic 1.0 Mixtape Plan",
        "",
        f"- Mixtape: `{mixtape_path}`",
        f"- Duration: {duration:.1f}s",
        f"- Transition snippets: `{snippets_dir}`",
        "",
        "## Track Order",
    ]
    for row in track_rows:
        lines.append(
            f"{row['position']}. {row['artist']} - {row['title']} "
            f"({row['bpm']} BPM, key {row['key']}) "
            f"entry {row['render_entry_ms'] / 1000:.1f}s, "
            f"first chorus end {row['render_exit_ms'] / 1000:.1f}s, "
            f"intro bars {row['intro_bars']}, chorus bars {row['first_chorus_bars']}"
        )
    lines.extend(["", "## Transitions"])
    for row in transition_rows:
        lines.append(
            f"{row['position']}. {row['from']} -> {row['to']}: "
            f"{row['case']}, overlap {row['overlap_seconds']:.1f}s, "
            f"B rate {row['entry_rate']}, both vocal={row['both_vocal_detected']}, "
            f"A vocal {row['a_transition_vocal_ratio']:.2f}, "
            f"B vocal {row['b_intro_vocal_ratio']:.2f}, "
            f"snippet `{row['snippet_wav']}`"
        )
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {warning}" for warning in warnings)
    (output_dir / "mix_plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    shutil.copyfile(Path(__file__).resolve(), output_dir / "algorithm_demo_transition_logic_1_0.py")
    (output_dir / "ALGORITHM_demo_transition_logic_1_0.md").write_text(
        _algorithm_markdown(), encoding="utf-8"
    )

    print(json.dumps(plan["outputs"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
