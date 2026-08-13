"""Standalone transition planning for the deployed HarBeat DJ paths.

This package only turns two analyzed song objects into a serializable plan.
It does not render audio, download assets, schedule RK, select target songs,
or depend on the application package.
"""

from .transition_planner import (
    PLANNER_VERSION,
    FAST_CUT_PLANNER_VERSION,
    plan_default_transition,
    plan_fast_cut_transition,
    plan_target_energy_transition,
    plan_target_style_transition,
)

__all__ = [
    "PLANNER_VERSION",
    "FAST_CUT_PLANNER_VERSION",
    "plan_default_transition",
    "plan_fast_cut_transition",
    "plan_target_energy_transition",
    "plan_target_style_transition",
]
