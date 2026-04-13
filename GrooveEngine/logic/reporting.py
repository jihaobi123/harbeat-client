from __future__ import annotations

from typing import Any

from core.datatypes import TransitionWindowScore

DEFAULT_REPORT_PRUNING_RULES = {
    "min_score": 0.55,
    "max_render_peak_db": -0.2,
    "max_render_spectral_conflict": 0.72,
    "max_render_loudness_delta_db": 6.0,
    "max_sync_drift_risk": 0.68,
    "max_phase_error_beats": 1.25,
}


def candidate_row(
    *,
    label: str,
    candidate: TransitionWindowScore,
    artifact_path: str = "",
    wav_path: str = "",
) -> dict[str, Any]:
    analysis_score = float(candidate.total_score)
    estimated_conflict = float(1.0 - candidate.spectral_conflict_score)
    return {
        "label": label,
        "candidate_rank": candidate.search_rank or 1,
        "final_rank": candidate.search_rank or 1,
        "candidate_strategy": candidate.strategy.value,
        "candidate_exit_bar": candidate.track_a_exit_bar,
        "candidate_entry_bar": candidate.track_b_entry_bar,
        "candidate_score": analysis_score,
        "analysis_score": analysis_score,
        "render_validation_score": None,
        "final_score": analysis_score,
        "score_delta_after_render": 0.0,
        "score": analysis_score,
        "strategy": candidate.strategy.value,
        "handoff_profile": candidate.handoff_profile,
        "target_bpm": float(candidate.target_bpm),
        "overlap_beats": int(candidate.overlap_beats),
        "phase_offset_beats": float(candidate.phase_offset_beats),
        "alignment_confidence": float(candidate.alignment_confidence),
        "phase_error_beats": float(candidate.phase_error_beats),
        "sync_drift_risk": float(candidate.sync_drift_risk),
        "recommended_max_overlap_beats": int(candidate.recommended_max_overlap_beats or candidate.overlap_beats),
        "long_blend_safe": bool(candidate.overlap_beats <= int(candidate.recommended_max_overlap_beats or candidate.overlap_beats) and candidate.sync_drift_risk <= 0.60),
        "render_validation_available": False,
        "render_validation_status": "not_shortlisted",
        "render_validation_error": "",
        "render_peak_db": 0.0,
        "render_rms_db": 0.0,
        "render_headroom_db": 0.0,
        "render_spectral_conflict": estimated_conflict,
        "render_loudness_delta_db": float((1.0 - candidate.loudness_continuity_score) * 12.0),
        "render_low_band_conflict": estimated_conflict,
        "render_bass_overlap_indicator": estimated_conflict,
        "render_transient_loss_indicator": 0.0,
        "render_groove_softening_indicator": 0.0,
        "render_vocal_overlap_risk": 0.0,
        "artifact_path": artifact_path,
        "wav_path": wav_path,
        "notes": list(candidate.notes),
    }


def passes_pruning(row: dict[str, Any], rules: dict[str, float]) -> bool:
    passes_core = (
        float(row.get("score", row.get("final_score", 0.0))) >= float(rules.get("min_score", 0.0))
        and float(row.get("sync_drift_risk", 0.0)) <= float(rules.get("max_sync_drift_risk", 1.0))
        and float(row.get("phase_error_beats", 0.0)) <= float(rules.get("max_phase_error_beats", 999.0))
    )
    if not passes_core:
        return False
    if str(row.get("render_validation_status", "")) != "validated":
        return True
    return (
        float(row.get("render_peak_db", 0.0)) <= float(rules.get("max_render_peak_db", 0.0))
        and float(row.get("render_spectral_conflict", 0.0)) <= float(rules.get("max_render_spectral_conflict", 1.0))
        and float(row.get("render_loudness_delta_db", 0.0)) <= float(rules.get("max_render_loudness_delta_db", 999.0))
    )


def prune_rows(rows: list[dict[str, Any]], rules: dict[str, float]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    kept = [row for row in rows if passes_pruning(row, rules)]
    rejected = len(rows) - len(kept)
    return kept, {
        "input_count": len(rows),
        "kept_count": len(kept),
        "rejected_count": rejected,
        "retention_ratio": (len(kept) / len(rows)) if rows else 0.0,
        "rules": rules,
    }


def shortlist(rows: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: (
            float(row.get("final_score", row.get("score", 0.0))),
            -float(row.get("render_peak_db", 0.0)),
            -float(row.get("render_spectral_conflict", 0.0)),
            -float(row.get("render_loudness_delta_db", 0.0)),
            -float(row.get("sync_drift_risk", 0.0)),
            -float(row.get("phase_error_beats", 0.0)),
        ),
        reverse=True,
    )
    return [_pack_row(row) for row in ranked[:limit]]


def winner_recommendation(rows: list[dict[str, Any]], pareto_items: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"recommended": None, "best_by_score": None, "best_by_analysis_score": None, "safest": None, "smoothest": None, "notes": ["No rows available after pruning."]}
    best_by_final = max(rows, key=lambda row: float(row.get("final_score", row.get("score", 0.0))))
    best_by_analysis = max(rows, key=lambda row: float(row.get("analysis_score", 0.0)))
    safest = min(rows, key=lambda row: float(row.get("render_peak_db", 0.0)))
    smoothest = min(rows, key=lambda row: float(row.get("render_loudness_delta_db", 0.0)))
    recommended = max(
        rows,
        key=lambda row: (
            float(row.get("final_score", row.get("score", 0.0)))
            - float(row.get("render_spectral_conflict", 0.0)) * 0.10
            - float(row.get("render_loudness_delta_db", 0.0)) * 0.02
            - max(float(row.get("render_peak_db", 0.0)) + 0.2, 0.0) * 0.50
            - float(row.get("sync_drift_risk", 0.0)) * 0.12
            - float(row.get("phase_error_beats", 0.0)) * 0.08
        ),
    )
    pareto_labels = {item["label"] for item in pareto_items}
    notes = [
        f"Recommended winner uses final score {float(recommended.get('final_score', recommended.get('score', 0.0))):.3f} from analysis {float(recommended.get('analysis_score', 0.0)):.3f} and render validation {float(recommended.get('render_validation_score') or recommended.get('analysis_score', 0.0)):.3f}.",
        f"Render metrics: spectral conflict {float(recommended.get('render_spectral_conflict', 0.0)):.3f}, loudness delta {float(recommended.get('render_loudness_delta_db', 0.0)):.2f} dB, peak {float(recommended.get('render_peak_db', 0.0)):.2f} dBFS.",
        "Recommended winner is on Pareto front." if recommended["label"] in pareto_labels else "Recommended winner is outside Pareto front but wins weighted trade-off.",
    ]
    return {
        "recommended": _pack_row(recommended),
        "best_by_score": _pack_row(best_by_final),
        "best_by_analysis_score": _pack_row(best_by_analysis),
        "safest": _pack_row(safest),
        "smoothest": _pack_row(smoothest),
        "notes": notes,
    }


def metric_rankings(rows: list[dict[str, Any]], field: str, higher_is_better: bool) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda row: float(row.get(field, 0.0) or 0.0), reverse=higher_is_better)
    return [
        {
            "label": row["label"],
            "value": float(row.get(field, 0.0) or 0.0),
            "strategy": row.get("strategy", "unknown"),
            "handoff_profile": row.get("handoff_profile", "unknown"),
            "artifact_path": row.get("artifact_path", ""),
            "wav_path": row.get("wav_path", ""),
        }
        for row in ranked[:5]
    ]


def multi_metric_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "analysis_score_top": metric_rankings(rows, "analysis_score", True),
        "final_score_top": metric_rankings(rows, "final_score", True),
        "render_validation_top": metric_rankings(rows, "render_validation_score", True),
        "headroom_top": metric_rankings(rows, "render_headroom_db", True),
        "peak_safest": metric_rankings(rows, "render_peak_db", False),
        "rms_strongest": metric_rankings(rows, "render_rms_db", True),
        "spectral_cleanest": metric_rankings(rows, "render_spectral_conflict", False),
        "loudness_smoothest": metric_rankings(rows, "render_loudness_delta_db", False),
        "sync_safest": metric_rankings(rows, "sync_drift_risk", False),
        "phase_tightest": metric_rankings(rows, "phase_error_beats", False),
    }


def dominates(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_score = float(left.get("final_score", left.get("score", 0.0)))
    right_score = float(right.get("final_score", right.get("score", 0.0)))
    left_peak = float(left.get("render_peak_db", 0.0))
    right_peak = float(right.get("render_peak_db", 0.0))
    left_spectral = float(left.get("render_spectral_conflict", 0.0))
    right_spectral = float(right.get("render_spectral_conflict", 0.0))
    left_loudness = float(left.get("render_loudness_delta_db", 0.0))
    right_loudness = float(right.get("render_loudness_delta_db", 0.0))
    left_drift = float(left.get("sync_drift_risk", 0.0))
    right_drift = float(right.get("sync_drift_risk", 0.0))
    left_phase = float(left.get("phase_error_beats", 0.0))
    right_phase = float(right.get("phase_error_beats", 0.0))
    not_worse = left_score >= right_score and left_peak <= right_peak and left_spectral <= right_spectral and left_loudness <= right_loudness and left_drift <= right_drift and left_phase <= right_phase
    strictly_better = left_score > right_score or left_peak < right_peak or left_spectral < right_spectral or left_loudness < right_loudness or left_drift < right_drift or left_phase < right_phase
    return not_worse and strictly_better


def pareto_front(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    front: list[dict[str, Any]] = []
    for candidate in rows:
        if any(dominates(other, candidate) for other in rows if other is not candidate):
            continue
        front.append(_pack_row(candidate))
    return sorted(front, key=lambda item: item["final_score"], reverse=True)


def group_rankings(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = {}
    for row in rows:
        key = str(row.get(field, "unknown"))
        grouped.setdefault(key, []).append(float(row.get("final_score", row.get("score", 0.0))))
    ranked = []
    for key, values in grouped.items():
        ranked.append({"name": key, "count": len(values), "average_score": sum(values) / len(values), "best_score": max(values), "worst_score": min(values)})
    return sorted(ranked, key=lambda item: item["average_score"], reverse=True)


def ranking_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "strategy_ranking": group_rankings(rows, "strategy"),
        "handoff_ranking": group_rankings(rows, "handoff_profile"),
        "overlap_ranking": group_rankings(rows, "overlap_beats"),
        "phase_offset_ranking": group_rankings(rows, "phase_offset_beats"),
        "recommended_overlap_ranking": group_rankings(rows, "recommended_max_overlap_beats"),
    }


def cross_candidate_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    candidate_rows = [row for row in rows if row.get("candidate_rank") is not None]
    if not candidate_rows:
        return {"candidate_rank_ranking": [], "candidate_strategy_ranking": [], "candidate_window_ranking": []}
    window_rows = [{**row, "candidate_window": f"{row.get('candidate_exit_bar', 0)}->{row.get('candidate_entry_bar', 0)}"} for row in candidate_rows]
    return {
        "candidate_rank_ranking": group_rankings(candidate_rows, "candidate_rank"),
        "candidate_strategy_ranking": group_rankings(candidate_rows, "candidate_strategy"),
        "candidate_window_ranking": group_rankings(window_rows, "candidate_window"),
    }


def build_candidate_search_report(
    *,
    title: str,
    rows: list[dict[str, Any]],
    pruning_rules: dict[str, float] | None = None,
    metadata: dict[str, Any] | None = None,
    shortlist_limit: int = 5,
) -> dict[str, Any]:
    rules = pruning_rules or DEFAULT_REPORT_PRUNING_RULES
    pruned_rows, pruning_section = prune_rows(rows, rules)
    active_rows = pruned_rows or rows
    pareto_items = pareto_front(active_rows)
    shortlist_items = shortlist(active_rows, limit=shortlist_limit)
    winner_section = winner_recommendation(active_rows, pareto_items)
    diagnostics_section = {
        "row_count": len(active_rows),
        "ranking": ranking_summary(active_rows),
        "cross_candidate_ranking": cross_candidate_summary(active_rows),
        "multi_metric": multi_metric_summary(active_rows),
        "pareto_count": len(pareto_items),
        "validated_row_count": sum(1 for row in active_rows if row.get("render_validation_status") == "validated"),
    }
    overview = {
        "title": title,
        "best_label": max(active_rows, key=lambda row: float(row.get("final_score", row.get("score", 0.0))))["label"] if active_rows else "",
        "best_score": max((float(row.get("final_score", row.get("score", 0.0))) for row in active_rows), default=0.0),
        "active_row_count": len(active_rows),
        "pruning_fallback_used": not bool(pruned_rows) and bool(rows),
    }
    return {
        "report_version": "6.0",
        "overview_section": {**overview, **(metadata or {})},
        "winner_section": winner_section,
        "pruning_section": pruning_section,
        "diagnostics_section": diagnostics_section,
        "shortlist_section": {"items": shortlist_items},
        "pareto_section": {"items": pareto_items},
        "rows": active_rows,
    }


def _pack_row(row: dict[str, Any]) -> dict[str, Any]:
    render_validation_score = row.get("render_validation_score")
    return {
        "label": row["label"],
        "score": float(row.get("final_score", row.get("score", 0.0))),
        "analysis_score": float(row.get("analysis_score", 0.0)),
        "final_score": float(row.get("final_score", row.get("score", 0.0))),
        "render_validation_score": float(render_validation_score) if render_validation_score is not None else None,
        "score_delta_after_render": float(row.get("score_delta_after_render", 0.0)),
        "render_validation_status": row.get("render_validation_status", "not_shortlisted"),
        "strategy": row.get("strategy", "unknown"),
        "handoff_profile": row.get("handoff_profile", "unknown"),
        "candidate_rank": row.get("candidate_rank", 1),
        "final_rank": row.get("final_rank", row.get("candidate_rank", 1)),
        "candidate_window": f"{row.get('candidate_exit_bar', 0)}->{row.get('candidate_entry_bar', 0)}",
        "overlap_beats": row.get("overlap_beats", 0.0),
        "phase_offset_beats": row.get("phase_offset_beats", 0.0),
        "render_peak_db": float(row.get("render_peak_db", 0.0)),
        "render_headroom_db": float(row.get("render_headroom_db", 0.0)),
        "render_spectral_conflict": float(row.get("render_spectral_conflict", 0.0)),
        "render_loudness_delta_db": float(row.get("render_loudness_delta_db", 0.0)),
        "render_low_band_conflict": float(row.get("render_low_band_conflict", 0.0)),
        "render_bass_overlap_indicator": float(row.get("render_bass_overlap_indicator", 0.0)),
        "render_transient_loss_indicator": float(row.get("render_transient_loss_indicator", 0.0)),
        "render_groove_softening_indicator": float(row.get("render_groove_softening_indicator", 0.0)),
        "artifact_path": row.get("artifact_path", ""),
        "wav_path": row.get("wav_path", ""),
    }
