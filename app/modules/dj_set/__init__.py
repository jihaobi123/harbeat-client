"""DJ Set generation module.

Pipeline (track_ids → 5 DJ sets):
    Track Profiler           — single-track features
    Section Energy           — per-section energy windows
    Role Classifier          — opener / builder / peak / ...
    Edge Analyzer            — pairwise A→B transition score
    Set Templates            — 5 narrative templates
    Set Optimizer            — graph search per template
    Purpose Planner          — tag each transition
    Transition Plan Generator — concrete DJ actions
    Quality Gate             — set-level checks

The pipeline is invoked by router.set_generate_endpoint().
"""

from app.modules.dj_set.track_profiler import TrackProfile, build_track_profile
from app.modules.dj_set.track_analysis_adapter import build_track_analysis_v2
from app.modules.dj_set.section_energy import SectionEnergy, compute_section_energy_map
from app.modules.dj_set.role_classifier import RoleAssessment, classify_track, ALL_ROLES
from app.modules.dj_set.edge_analyzer import (
    TransitionEdge,
    analyze_edge,
    analyze_all_edges,
    ALL_RULES,
)
from app.modules.dj_set.set_optimizer import (
    DJSet,
    optimize_set,
    optimize_all_templates,
)
from app.modules.dj_set.set_templates import (
    SetTemplate,
    ALL_TEMPLATES,
    get_template,
    SMOOTH,
    BUILD,
    CYPHER_WAVE,
    BATTLE_PEAK,
    CLEAN_VOCAL,
)
from app.modules.dj_set.purpose_planner import (
    TransitionPurpose,
    plan_purposes,
    PURPOSES,
)
from app.modules.dj_set.transition_plan import (
    TransitionPlan,
    build_transition_plan,
    build_all_plans,
)
from app.modules.dj_set.quality_gate import QualityReport, evaluate_quality
from app.modules.dj_set.service import generate_dj_sets, preview_transition

__all__ = [
    "TrackProfile",
    "build_track_profile",
    "build_track_analysis_v2",
    "SectionEnergy",
    "compute_section_energy_map",
    "RoleAssessment",
    "classify_track",
    "ALL_ROLES",
    "TransitionEdge",
    "analyze_edge",
    "analyze_all_edges",
    "ALL_RULES",
    "SetTemplate",
    "ALL_TEMPLATES",
    "get_template",
    "SMOOTH",
    "BUILD",
    "CYPHER_WAVE",
    "BATTLE_PEAK",
    "CLEAN_VOCAL",
    "DJSet",
    "optimize_set",
    "optimize_all_templates",
    "TransitionPurpose",
    "plan_purposes",
    "PURPOSES",
    "TransitionPlan",
    "build_transition_plan",
    "build_all_plans",
    "QualityReport",
    "evaluate_quality",
    "generate_dj_sets",
    "preview_transition",
]
