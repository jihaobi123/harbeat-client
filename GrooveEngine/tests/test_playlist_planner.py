"""Smoke checks for transition and playlist planning."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analyzer.storage import MetadataStorage
from core.datatypes import PlaylistPlan, TransitionPlan
from logic.brain import TransitionPlanner
from logic.playlist import PlaylistPlanner


FIXTURES_DIR = ROOT / "fixtures"


def _load(name: str):
    return MetadataStorage.load(FIXTURES_DIR / name)


def test_transition_planner_returns_valid_plan() -> None:
    planner = TransitionPlanner()
    track_a = _load("track_a.groove.json")
    track_b = _load("track_b.groove.json")
    plan: TransitionPlan = planner.plan(track_a, track_b)
    report = planner.candidate_report(track_a, track_b, limit=3)

    assert plan.overlap_duration_beats in {1, 3, 4, 8, 16, 32}
    assert plan.track_a_exit_bar >= 1
    assert plan.track_b_entry_bar >= 1
    assert plan.target_bpm > 0
    assert 0.0 <= plan.score_breakdown.total_score <= 1.0
    assert len(plan.automation) > 0
    assert report["overview_section"]["candidate_count"] == 3
    assert len(report["rows"]) == 3


def test_playlist_planner_orders_all_tracks() -> None:
    planner = PlaylistPlanner(TransitionPlanner())
    tracks = [
        _load("track_a.groove.json"),
        _load("track_b.groove.json"),
        _load("track_c_low_energy.json"),
        _load("track_d_build_up.json"),
        _load("track_e_high_energy_drop.json"),
    ]

    plan: PlaylistPlan = planner.plan(tracks)

    assert len(plan.ordered_track_ids) == len(tracks)
    assert len(set(plan.ordered_track_ids)) == len(tracks)
    assert len(plan.transitions) == len(tracks) - 1
    assert 0.0 <= plan.average_score <= 1.2
    assert len(plan.notes) >= 2
    assert plan.ordered_track_ids[0] == "fixture-track-c"


if __name__ == "__main__":
    test_transition_planner_returns_valid_plan()
    test_playlist_planner_orders_all_tracks()
    print("playlist planner smoke checks passed")


def test_transition_candidate_report_uses_two_stage_scores() -> None:
    planner = TransitionPlanner()
    track_a = _load("track_a.groove.json")
    track_b = _load("track_b.groove.json")
    report = planner.candidate_report(track_a, track_b, limit=4, render_shortlist_limit=2)

    assert report["overview_section"]["two_stage_selection"] is True
    assert report["overview_section"]["render_validation_shortlist_count"] == 2
    assert report["report_version"] == "6.0"
    rows = report["rows"]
    assert len(rows) == 4
    assert any(row["render_validation_status"] == "validated" for row in rows)
    assert any(row["render_validation_status"] == "not_shortlisted" for row in rows)
    validated = next(row for row in rows if row["render_validation_status"] == "validated")
    assert isinstance(validated["analysis_score"], float)
    assert isinstance(validated["final_score"], float)
    assert "render_validation_score" in validated
    assert "score_delta_after_render" in validated
    assert validated["score"] == validated["final_score"]
    assert "best_by_analysis_score" in report["winner_section"]
    assert report["winner_section"]["recommended"]["score"] == report["winner_section"]["recommended"]["final_score"]
