"""Demo transition comparison report for GrooveEngine fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from analyzer.storage import MetadataStorage
from core.datatypes import TransitionPlan
from core.enums import TransitionType
from logic.brain import TransitionPlanner


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@dataclass(slots=True)
class ScenarioResult:
    """Container for a named transition-planning scenario."""

    name: str
    plan: TransitionPlan
    expected_strategy: TransitionType | None = None


def _load(name: str):
    return MetadataStorage.load(FIXTURES_DIR / name)


def _run_scenario(name: str, track_a_name: str, track_b_name: str, expected: TransitionType | None = None) -> ScenarioResult:
    planner = TransitionPlanner()
    track_a = _load(track_a_name)
    track_b = _load(track_b_name)
    plan = planner.plan(track_a, track_b)
    report = planner.candidate_report(track_a, track_b, limit=3)

    assert plan.overlap_duration_beats in {1, 3, 4, 8, 16, 32}
    assert plan.track_a_exit_bar >= 1
    assert plan.track_b_entry_bar >= 1
    assert plan.target_bpm > 0
    assert 0.0 <= plan.score_breakdown.total_score <= 1.0
    assert len(plan.automation) > 0
    assert report["candidate_count"] == 3
    assert report["best_strategy"] == plan.strategy.value
    if expected is not None:
        assert plan.strategy == expected, f"Expected {expected.value}, got {plan.strategy.value} in {name}"

    return ScenarioResult(name=name, plan=plan, expected_strategy=expected)


def _print_result(result: ScenarioResult) -> None:
    plan = result.plan
    expectation = result.expected_strategy.value if result.expected_strategy else "any"
    print(f"Scenario: {result.name}")
    print(f"  Expected Strategy : {expectation}")
    print(f"  Selected Strategy : {plan.strategy.value}")
    print(f"  Mix Start         : {plan.mix_start_time:.2f}s")
    print(f"  Overlap Beats     : {plan.overlap_duration_beats}")
    print(f"  Target BPM        : {plan.target_bpm:.2f}")
    print(f"  Exit/Entry Bars   : A:{plan.track_a_exit_bar} -> B:{plan.track_b_entry_bar}")
    print(f"  Score             : {plan.score_breakdown.total_score:.3f}")
    print(f"  Phrase Score      : {plan.score_breakdown.phrase_score:.3f}")
    print(f"  Energy Score      : {plan.score_breakdown.energy_score:.3f}")
    print(f"  Harmonic Score    : {plan.score_breakdown.harmonic_score:.3f}")
    for note in plan.score_breakdown.notes:
        print(f"    - {note}")
    print()


def run_demo_transition_test() -> None:
    """Run the normal, echo-out, and riser strategy scenarios."""

    scenarios = [
        _run_scenario(
            name="Normal Blend",
            track_a_name="track_a.groove.json",
            track_b_name="track_b.groove.json",
            expected=None,
        ),
        _run_scenario(
            name="Echo Out Mismatch",
            track_a_name="track_a.groove.json",
            track_b_name="track_c_low_energy.json",
            expected=TransitionType.ECHO_OUT,
        ),
        _run_scenario(
            name="Riser Impact Transition",
            track_a_name="track_d_build_up.json",
            track_b_name="track_e_high_energy_drop.json",
            expected=TransitionType.RISER,
        ),
    ]

    print("=" * 72)
    print("GROOVEENGINE TRANSITION COMPARISON REPORT")
    print("=" * 72)
    for scenario in scenarios:
        _print_result(scenario)
    print("All demo scenarios passed.")


if __name__ == "__main__":
    run_demo_transition_test()


def test_demo_scenarios_support_overlap_variants() -> None:
    planner = TransitionPlanner()
    track_a = _load("track_a.groove.json")
    track_b = _load("track_b.groove.json")
    report = planner.candidate_report(track_a, track_b, limit=5)

    assert report["candidate_count"] >= 1
    top = planner.top_candidates(track_a, track_b, limit=5)
    overlaps = {int(candidate.overlap_beats) for candidate in top}
    assert any(overlap in {4, 8, 16, 32} for overlap in overlaps)
