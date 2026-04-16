from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analyzer.storage import MetadataStorage
from audio.artifacts import export_candidate_search_report, export_playlist_artifact, export_transition_artifact
from audio.offline_renderer import OfflineDualDeckRenderer
from core.datatypes import TransitionPlan, TransitionWindowScore
from logic.brain import TransitionPlanner
from logic.playlist import PlaylistPlanner
from logic.reporting import build_candidate_search_report
from logic.strategies import STRATEGY_REGISTRY

FIXTURES = ROOT / "fixtures"
OUTPUTS = ROOT / "temp_outputs"
ARTIFACTS = ROOT / "temp_artifacts"
REPORTS = ROOT / "temp_artifacts"
SAMPLE_RATE = 44100
DEFAULT_CANDIDATE_LIMIT = 5
FIXTURE_TRACKS = [
    "track_a.groove.json",
    "track_b.groove.json",
    "track_c_low_energy.json",
    "track_d_build_up.json",
    "track_e_high_energy_drop.json",
]
DEFAULT_SWEEP = [
    ["track_a.groove.json", "track_b.groove.json"],
    ["track_b.groove.json", "track_d_build_up.json"],
    ["track_c_low_energy.json", "track_e_high_energy_drop.json"],
    ["track_a.groove.json", "track_b.groove.json", "track_d_build_up.json"],
]
DEFAULT_PARAMETER_GRID = {
    "overlap_beats": [4, 8, 16, 32],
    "handoff_profile": ["smooth_blend", "bass_swap", "reset_cut"],
    "phase_offset_beats": [0.0, 0.5, 1.0],
}
DEFAULT_PRUNING_RULES = {
    "min_score": 0.55,
    "max_render_peak_db": -0.2,
    "max_render_spectral_conflict": 0.72,
    "max_render_loudness_delta_db": 6.0,
}
NO_PRUNING_RULES = {
    "min_score": 0.0,
    "max_render_peak_db": 999.0,
    "max_render_spectral_conflict": 999.0,
    "max_render_loudness_delta_db": 999.0,
}


def la(path: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    audio, source_sr = sf.read(path, always_2d=True, dtype="float32")
    if source_sr != sr:
        audio = np.stack([librosa.resample(audio[:, channel], orig_sr=source_sr, target_sr=sr) for channel in range(audio.shape[1])], axis=1)
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    return audio.astype(np.float32, copy=False)


def _fixture_catalog() -> dict[str, object]:
    return {name: MetadataStorage.load(FIXTURES / name) for name in FIXTURE_TRACKS}


def _closest_pair_for_delta(target_delta: float, exclude: set[tuple[str, str]] | None = None) -> tuple[str, str]:
    exclude = exclude or set()
    catalog = _fixture_catalog()
    ranked: list[tuple[float, str, str]] = []
    names = list(catalog.keys())
    for index, track_a_name in enumerate(names):
        for track_b_name in names[index + 1:]:
            pair_key = tuple(sorted((track_a_name, track_b_name)))
            if pair_key in exclude:
                continue
            delta = abs(catalog[track_a_name].beatgrid.bpm - catalog[track_b_name].beatgrid.bpm)
            ranked.append((abs(delta - target_delta), track_a_name, track_b_name))
    if not ranked:
        raise ValueError("No fixture pairs available for fixed benchmark cases.")
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    return ranked[0][1], ranked[0][2]


def fixed_benchmark_cases() -> list[dict[str, object]]:
    same_bpm = _closest_pair_for_delta(0.0)
    used = {tuple(sorted(same_bpm))}
    near_bpm = _closest_pair_for_delta(2.0, exclude=used)
    used.add(tuple(sorted(near_bpm)))
    medium_bpm = _closest_pair_for_delta(10.0, exclude=used)
    return [
        {"case_name": "same_bpm", "case_family": "fixed_pair", "tracks": list(same_bpm), "params": {"overlap_beats": 8}},
        {"case_name": "near_bpm", "case_family": "fixed_pair", "tracks": list(near_bpm), "params": {"overlap_beats": 8}},
        {"case_name": "medium_bpm_delta", "case_family": "fixed_pair", "tracks": list(medium_bpm), "params": {"overlap_beats": 8}},
        {"case_name": "long_overlap_case", "case_family": "fixed_pair", "tracks": list(same_bpm), "params": {"overlap_beats": 32}},
        {"case_name": "short_transition_case", "case_family": "fixed_pair", "tracks": list(near_bpm), "params": {"overlap_beats": 4}},
        {"case_name": "fixture_playlist_smoke", "case_family": "playlist", "tracks": ["track_a.groove.json", "track_b.groove.json", "track_d_build_up.json"]},
    ]


def _normalize_sweep_cases(cases: list[list[str]] | list[dict[str, object]] | None) -> list[dict[str, object]]:
    if cases is None:
        return fixed_benchmark_cases()
    normalized: list[dict[str, object]] = []
    for index, case in enumerate(cases, start=1):
        if isinstance(case, dict):
            normalized.append(case)
            continue
        normalized.append({"case_name": f"case_{index}", "case_family": "pair" if len(case) == 2 else "playlist", "tracks": list(case)})
    return normalized


def _grid_variants(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    variants = [{}]
    for key, values in grid.items():
        next_variants: list[dict[str, Any]] = []
        for variant in variants:
            for value in values:
                next_variants.append({**variant, key: value})
        variants = next_variants
    return variants


def _parameterized_plan(plan: TransitionPlan, params: dict[str, Any]) -> TransitionPlan:
    overlap_beats = float(params.get("overlap_beats", plan.overlap_duration_beats))
    handoff_profile = str(params.get("handoff_profile", plan.handoff_profile))
    phase_offset_beats = float(params.get("phase_offset_beats", plan.phase_offset_beats))
    score = plan.score_breakdown.model_copy(update={
        "overlap_beats": int(round(overlap_beats)),
        "handoff_profile": handoff_profile,
        "phase_offset_beats": phase_offset_beats,
        "notes": plan.score_breakdown.notes + [
            f"Parameterized sweep override overlap={overlap_beats:.2f}.",
            f"Parameterized sweep override handoff={handoff_profile}.",
            f"Parameterized sweep override phase={phase_offset_beats:.2f}.",
        ],
    })
    updated = plan.model_copy(update={
        "overlap_duration_beats": overlap_beats,
        "handoff_profile": handoff_profile,
        "phase_offset_beats": phase_offset_beats,
        "score_breakdown": score,
    })
    updated.automation = STRATEGY_REGISTRY[updated.strategy].build_automation(updated)
    return updated


def _plan_from_candidate(track_a, candidate: TransitionWindowScore, planner: TransitionPlanner | None = None) -> TransitionPlan:
    plan = TransitionPlan(
        mix_start_time=(planner or TransitionPlanner())._bar_start_time(track_a, candidate.track_a_exit_bar),
        overlap_duration_beats=float(candidate.overlap_beats),
        target_bpm=candidate.target_bpm,
        phase_offset_beats=candidate.phase_offset_beats,
        alignment_confidence=candidate.alignment_confidence,
        handoff_profile=candidate.handoff_profile,
        strategy=candidate.strategy,
        track_a_exit_bar=candidate.track_a_exit_bar,
        track_b_entry_bar=candidate.track_b_entry_bar,
        automation=[],
        score_breakdown=candidate,
    )
    plan.automation = STRATEGY_REGISTRY[plan.strategy].build_automation(plan)
    return plan


def _render_pair_result(track_a_name: str, track_b_name: str, plan: TransitionPlan, params: dict[str, Any] | None = None, extra: dict[str, Any] | None = None, sync_backend: str | None = None) -> dict[str, object]:
    OUTPUTS.mkdir(exist_ok=True)
    ARTIFACTS.mkdir(exist_ok=True)
    track_a = MetadataStorage.load(FIXTURES / track_a_name)
    track_b = MetadataStorage.load(FIXTURES / track_b_name)
    renderer = OfflineDualDeckRenderer(sample_rate=SAMPLE_RATE, time_stretch_provider=sync_backend)
    active_plan = _parameterized_plan(plan, params) if params else plan
    result = renderer.render_transition(la(track_a.path), track_a, track_a.title, active_plan, la(track_b.path), track_b, track_b.title)
    suffix = "" if not params else "_" + "_".join(f"{key}-{str(value).replace('.', 'p')}" for key, value in params.items())
    if extra and extra.get("candidate_rank") is not None:
        suffix = f"_candidate-{extra['candidate_rank']}" + suffix
    if sync_backend:
        suffix += f"_sync-{sync_backend.replace(' ', '-')}"
    run_id = f"{Path(track_a_name).stem}_to_{Path(track_b_name).stem}{suffix}"
    wav_path = OUTPUTS / f"benchmark_{run_id}.wav"
    sf.write(wav_path, np.clip(result.audio, -1.0, 1.0), SAMPLE_RATE)
    artifact_path = ARTIFACTS / f"benchmark_{run_id}.json"
    export_transition_artifact(artifact_path, track_a_title=track_a.title, track_b_title=track_b.title, plan=active_plan, transition_summary=result.transition_summary, render_trace=result.render_trace)
    payload = {"mode": "pair", "pair": [track_a_name, track_b_name], "params": params or {}, "sync_backend": sync_backend or "default", "wav_path": str(wav_path), "artifact_path": str(artifact_path), "summary": result.transition_summary, **(extra or {})}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def benchmark_pair(track_a_name: str, track_b_name: str, params: dict[str, Any] | None = None, sync_backend: str | None = None) -> dict[str, object]:
    track_a = MetadataStorage.load(FIXTURES / track_a_name)
    track_b = MetadataStorage.load(FIXTURES / track_b_name)
    planner = TransitionPlanner()
    plan = planner.plan(track_a, track_b)
    return _render_pair_result(track_a_name, track_b_name, plan, params=params, sync_backend=sync_backend)


def benchmark_candidate_pair(track_a_name: str, track_b_name: str, candidate_rank: int, params: dict[str, Any] | None = None, candidate_limit: int = DEFAULT_CANDIDATE_LIMIT, sync_backend: str | None = None) -> dict[str, object]:
    track_a = MetadataStorage.load(FIXTURES / track_a_name)
    track_b = MetadataStorage.load(FIXTURES / track_b_name)
    planner = TransitionPlanner()
    candidates = planner.top_candidates(track_a, track_b, limit=max(candidate_limit, candidate_rank))
    if candidate_rank < 1 or candidate_rank > len(candidates):
        raise ValueError(f"Candidate rank {candidate_rank} out of range for {track_a_name} -> {track_b_name}.")
    candidate = candidates[candidate_rank - 1]
    plan = _plan_from_candidate(track_a, candidate, planner=planner)
    extra = {
        "candidate_rank": candidate_rank,
        "candidate_limit": max(candidate_limit, candidate_rank),
        "candidate_strategy": candidate.strategy.value,
        "candidate_exit_bar": candidate.track_a_exit_bar,
        "candidate_entry_bar": candidate.track_b_entry_bar,
        "candidate_score": candidate.total_score,
    }
    return _render_pair_result(track_a_name, track_b_name, plan, params=params, extra=extra, sync_backend=sync_backend)


def benchmark_playlist(track_names: list[str], sync_backend: str | None = None) -> dict[str, object]:
    OUTPUTS.mkdir(exist_ok=True)
    ARTIFACTS.mkdir(exist_ok=True)
    tracks = [MetadataStorage.load(FIXTURES / name) for name in track_names]
    planner = PlaylistPlanner(TransitionPlanner())
    renderer = OfflineDualDeckRenderer(sample_rate=SAMPLE_RATE, time_stretch_provider=sync_backend)
    playlist_plan = planner.plan(tracks)
    ordered = {track.track_id: track for track in tracks}
    ordered_tracks = [ordered[track_id] for track_id in playlist_plan.ordered_track_ids]
    current = la(ordered_tracks[0].path)
    transitions: list[dict[str, object]] = []
    artifacts: list[dict[str, object]] = []
    run_id = "playlist_" + "_".join(Path(name).stem for name in track_names)
    if sync_backend:
        run_id += f"_sync-{sync_backend.replace(' ', '-')}"
    for index, transition in enumerate(playlist_plan.transitions, start=1):
        incoming = ordered_tracks[index]
        outgoing = ordered_tracks[index - 1]
        result = renderer.render_transition(current, outgoing, outgoing.title, transition.plan, la(incoming.path), incoming, incoming.title)
        current = result.audio
        transitions.append(result.transition_summary)
        artifact_path = ARTIFACTS / f"{run_id}_transition_{index}.json"
        export_transition_artifact(artifact_path, track_a_title=outgoing.title, track_b_title=incoming.title, plan=transition.plan, transition_summary=result.transition_summary, render_trace=result.render_trace)
        artifacts.append({"path": str(artifact_path), "summary": result.transition_summary})
    wav_path = OUTPUTS / f"{run_id}.wav"
    sf.write(wav_path, np.clip(current, -1.0, 1.0), SAMPLE_RATE)
    mix_result = {"wav_path": str(wav_path), "ordered_track_ids": playlist_plan.ordered_track_ids, "ordered_titles": playlist_plan.ordered_titles, "average_score": playlist_plan.average_score, "playlist_notes": playlist_plan.notes, "transitions": transitions}
    artifact_path = ARTIFACTS / f"{run_id}.json"
    export_playlist_artifact(artifact_path, playlist_plan=playlist_plan, mix_result=mix_result, transition_artifacts=artifacts)
    payload = {"mode": "playlist", "track_names": track_names, "sync_backend": sync_backend or "default", "artifact_path": str(artifact_path), **mix_result}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def _sync_warning_summary(summary: dict[str, Any]) -> str:
    notes = summary.get("notes", [])
    sync_notes = [note for note in notes if isinstance(note, str) and ("overlap" in note.lower() or "drift" in note.lower() or "phase" in note.lower() or "prototype" in note.lower())]
    return " | ".join(sync_notes[:3])


def _row_from_pair(result: dict[str, object]) -> dict[str, Any]:
    summary = result["summary"]
    pair = result["pair"]
    params = result.get("params", {})
    return {
        "mode": "pair",
        "label": f"{pair[0]} -> {pair[1]}",
        "track_count": 2,
        "candidate_rank": result.get("candidate_rank", 1),
        "candidate_strategy": result.get("candidate_strategy", summary.get("strategy", "unknown")),
        "candidate_exit_bar": result.get("candidate_exit_bar", summary.get("track_a_exit_bar", 0)),
        "candidate_entry_bar": result.get("candidate_entry_bar", summary.get("track_b_entry_bar", 0)),
        "candidate_score": result.get("candidate_score", summary.get("score", 0.0)),
        "score": summary.get("score", 0.0),
        "strategy": summary.get("strategy", "unknown"),
        "handoff_profile": summary.get("handoff_profile", "unknown"),
        "target_bpm": summary.get("target_bpm", 0.0),
        "overlap_beats": params.get("overlap_beats", summary.get("overlap_beats", 0.0)),
        "phase_offset_beats": params.get("phase_offset_beats", summary.get("render_phase_offset_applied", 0.0)),
        "render_anchor_delta_beats": summary.get("render_anchor_delta_beats", 0.0),
        "render_phase_offset_applied": summary.get("render_phase_offset_applied", 0.0),
        "render_effective_phase_correction_beats": summary.get("render_effective_phase_correction_beats", summary.get("render_phase_offset_applied", 0.0)),
        "render_phase_error_estimate": summary.get("render_phase_error_estimate", 0.0),
        "render_drift_risk": summary.get("render_drift_risk", 0.0),
        "render_long_blend_safe": summary.get("render_long_blend_safe", False),
        "render_long_overlap_safe": summary.get("render_long_overlap_safe", summary.get("render_long_blend_safe", False)),
        "render_recommended_max_overlap_beats": summary.get("render_recommended_max_overlap_beats", 0),
        "sync_warning_count": summary.get("render_sync_warning_count", 0),
        "sync_warning_summary": _sync_warning_summary(summary),
        "render_peak_db": summary.get("render_peak_db", 0.0),
        "render_rms_db": summary.get("render_rms_db", 0.0),
        "render_headroom_db": summary.get("render_headroom_db", 0.0),
        "render_spectral_conflict": summary.get("render_spectral_conflict", 0.0),
        "render_loudness_delta_db": abs(float(summary.get("render_loudness_delta_db", 0.0))),
        "trace_blocks": summary.get("render_trace_blocks", 0),
        "artifact_path": result.get("artifact_path", ""),
        "wav_path": result.get("wav_path", ""),
    }


def _rows_from_playlist(result: dict[str, object]) -> list[dict[str, Any]]:
    transitions = result["transitions"]
    track_names = result["track_names"]
    rows: list[dict[str, Any]] = []
    for index, summary in enumerate(transitions, start=1):
        rows.append({
            "mode": "playlist",
            "label": f"{' | '.join(track_names)} :: transition {index}",
            "track_count": len(track_names),
            "score": summary.get("score", 0.0),
            "strategy": summary.get("strategy", "unknown"),
            "handoff_profile": summary.get("handoff_profile", "unknown"),
            "target_bpm": summary.get("target_bpm", 0.0),
            "overlap_beats": summary.get("overlap_beats", 0.0),
            "phase_offset_beats": summary.get("render_phase_offset_applied", 0.0),
            "render_anchor_delta_beats": summary.get("render_anchor_delta_beats", 0.0),
            "render_phase_offset_applied": summary.get("render_phase_offset_applied", 0.0),
            "render_effective_phase_correction_beats": summary.get("render_effective_phase_correction_beats", summary.get("render_phase_offset_applied", 0.0)),
            "render_phase_error_estimate": summary.get("render_phase_error_estimate", 0.0),
            "render_drift_risk": summary.get("render_drift_risk", 0.0),
            "render_long_blend_safe": summary.get("render_long_blend_safe", False),
            "render_long_overlap_safe": summary.get("render_long_overlap_safe", summary.get("render_long_blend_safe", False)),
            "render_recommended_max_overlap_beats": summary.get("render_recommended_max_overlap_beats", 0),
            "sync_warning_count": summary.get("render_sync_warning_count", 0),
            "sync_warning_summary": _sync_warning_summary(summary),
            "render_peak_db": summary.get("render_peak_db", 0.0),
            "render_rms_db": summary.get("render_rms_db", 0.0),
            "render_headroom_db": summary.get("render_headroom_db", 0.0),
            "render_spectral_conflict": summary.get("render_spectral_conflict", 0.0),
            "render_loudness_delta_db": abs(float(summary.get("render_loudness_delta_db", 0.0))),
            "trace_blocks": summary.get("render_trace_blocks", 0),
            "artifact_path": result.get("artifact_path", ""),
            "wav_path": result.get("wav_path", ""),
        })
    return rows


def _report_payload(
    *,
    title: str,
    report_slug: str,
    rows: list[dict[str, Any]],
    results: list[dict[str, object]],
    metadata: dict[str, Any] | None = None,
    pruning_rules: dict[str, float] | None = None,
) -> dict[str, object]:
    report = build_candidate_search_report(
        title=title,
        rows=rows,
        metadata=metadata,
        pruning_rules=pruning_rules,
    )
    json_path = REPORTS / f"{report_slug}.json"
    csv_path = REPORTS / f"{report_slug}.csv"
    export_candidate_search_report(
        json_path,
        csv_path,
        title=title,
        rows=rows,
        metadata=metadata,
        pruning_rules=pruning_rules,
    )
    payload = {
        "report": report,
        "json_report": str(json_path),
        "csv_report": str(csv_path),
        "results": results,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return payload


def run_sweep(cases: list[list[str]] | list[dict[str, object]] | None = None) -> dict[str, object]:
    normalized_cases = _normalize_sweep_cases(cases)
    rows: list[dict[str, Any]] = []
    results: list[dict[str, object]] = []
    for case in normalized_cases:
        tracks = list(case["tracks"])
        params = case.get("params")
        if len(tracks) == 2:
            result = benchmark_pair(tracks[0], tracks[1], params=params)
            result["case_name"] = case.get("case_name", "pair")
            result["case_family"] = case.get("case_family", "pair")
            results.append(result)
            row = _row_from_pair(result)
            row["case_name"] = result["case_name"]
            row["case_family"] = result["case_family"]
            rows.append(row)
        elif len(tracks) >= 3:
            result = benchmark_playlist(tracks)
            result["case_name"] = case.get("case_name", "playlist")
            result["case_family"] = case.get("case_family", "playlist")
            results.append(result)
            playlist_rows = _rows_from_playlist(result)
            for row in playlist_rows:
                row["case_name"] = result["case_name"]
                row["case_family"] = result["case_family"]
            rows.extend(playlist_rows)
        else:
            raise ValueError("Each sweep case must include at least two tracks.")
    return _report_payload(
        title="Benchmark sweep",
        report_slug="sweep_report",
        rows=rows,
        results=results,
        metadata={
            "case_count": len(normalized_cases),
            "row_count": len(rows),
            "fixed_cases": normalized_cases,
        },
        pruning_rules=NO_PRUNING_RULES,
    )


def _load_cases_from_file(path: str) -> list[list[str]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Sweep config must be a JSON list of track-name lists.")
    return [list(item) for item in payload]


def run_parameterized_sweep(cases: list[list[str]] | None = None, parameter_grid: dict[str, list[Any]] | None = None) -> dict[str, object]:
    cases = cases or [case for case in DEFAULT_SWEEP if len(case) == 2]
    parameter_grid = parameter_grid or DEFAULT_PARAMETER_GRID
    variants = _grid_variants(parameter_grid)
    rows: list[dict[str, Any]] = []
    results: list[dict[str, object]] = []
    for case in cases:
        if len(case) != 2:
            continue
        for params in variants:
            result = benchmark_pair(case[0], case[1], params=params)
            results.append(result)
            rows.append(_row_from_pair(result))
    return _report_payload(
        title="Parameterized benchmark sweep",
        report_slug="parameterized_sweep_report",
        rows=rows,
        results=results,
        metadata={
            "case_count": len(cases),
            "parameter_variant_count": len(variants),
            "row_count": len(rows),
            "parameter_grid": parameter_grid,
        },
        pruning_rules=NO_PRUNING_RULES,
    )


def run_candidate_parameter_search(cases: list[list[str]] | None = None, parameter_grid: dict[str, list[Any]] | None = None, candidate_limit: int = DEFAULT_CANDIDATE_LIMIT, pruning_rules: dict[str, float] | None = None) -> dict[str, object]:
    cases = cases or [case for case in DEFAULT_SWEEP if len(case) == 2]
    parameter_grid = parameter_grid or DEFAULT_PARAMETER_GRID
    pruning_rules = pruning_rules or DEFAULT_PRUNING_RULES
    variants = _grid_variants(parameter_grid)
    rows: list[dict[str, Any]] = []
    results: list[dict[str, object]] = []
    for case in cases:
        if len(case) != 2:
            continue
        for candidate_rank in range(1, candidate_limit + 1):
            for params in variants:
                result = benchmark_candidate_pair(case[0], case[1], candidate_rank=candidate_rank, params=params, candidate_limit=candidate_limit)
                results.append(result)
                rows.append(_row_from_pair(result))
    return _report_payload(
        title="Candidate parameter search",
        report_slug="candidate_parameter_search_report",
        rows=rows,
        results=results,
        metadata={
            "case_count": len(cases),
            "candidate_limit": candidate_limit,
            "parameter_variant_count": len(variants),
            "row_count": len(rows),
            "parameter_grid": parameter_grid,
        },
        pruning_rules=pruning_rules,
    )


def _load_parameter_grid(path: str) -> dict[str, list[Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Parameter grid config must be a JSON object.")
    return {str(key): list(value) for key, value in payload.items()}


def main() -> None:
    raw_args = sys.argv[1:]
    sync_backend: str | None = None
    args: list[str] = []
    index = 0
    while index < len(raw_args):
        if raw_args[index] == "--sync-backend":
            if index + 1 >= len(raw_args):
                raise SystemExit("--sync-backend requires a provider name")
            sync_backend = raw_args[index + 1]
            index += 2
            continue
        args.append(raw_args[index])
        index += 1
    usage = "Usage: python scripts/benchmark_runner.py track_a.groove.json track_b.groove.json [more tracks...] [--sync-backend provider] | --sweep [config.json] [--sync-backend provider] | --parameter-sweep [cases.json] [grid.json] [--sync-backend provider] | --candidate-parameter-search [cases.json] [grid.json] [candidate_limit] [--sync-backend provider]"
    if not args:
        raise SystemExit(usage)
    if args[0] == "--sweep":
        cases = _load_cases_from_file(args[1]) if len(args) > 1 else None
        run_sweep(cases)
        return
    if args[0] == "--parameter-sweep":
        cases = _load_cases_from_file(args[1]) if len(args) > 1 else None
        grid = _load_parameter_grid(args[2]) if len(args) > 2 else None
        run_parameterized_sweep(cases, grid)
        return
    if args[0] == "--candidate-parameter-search":
        cases = _load_cases_from_file(args[1]) if len(args) > 1 else None
        grid = _load_parameter_grid(args[2]) if len(args) > 2 else None
        candidate_limit = int(args[3]) if len(args) > 3 else DEFAULT_CANDIDATE_LIMIT
        run_candidate_parameter_search(cases, grid, candidate_limit)
        return
    if len(args) == 2:
        benchmark_pair(args[0], args[1], sync_backend=sync_backend)
        return
    if len(args) >= 3:
        benchmark_playlist(args, sync_backend=sync_backend)
        return
    raise SystemExit(usage)


if __name__ == "__main__":
    main()
