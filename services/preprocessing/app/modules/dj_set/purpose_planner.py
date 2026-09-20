"""Transition Purpose Planner.

Once a set is ordered (set_optimizer), each transition has a *purpose*
in the narrative — not just "blend A into B", but "this is the moment
we lift from groove into build". The purpose tag drives:

  - which transition rule to actually use (refines edge.best_rule)
  - how the UI labels the seam ("→ build_to_peak")
  - which beat reinforcement profile mixer_rules picks

Purposes:
  open_to_groove        opener → groove_holder            soft EQ swap
  groove_to_build       groove_holder → builder           4-bar EQ swap
  build_to_peak         builder → peak                    bass_drop_swap
  peak_to_reset         peak → reset                      drum_takeover
  reset_to_build        reset → builder                   eq_swap_4bar
  bridge_style_change   any → bridge / bridge → any       harmonic_blend
  vocal_handoff         vocal_moment in/out               instrumental_bridge_vocal_late
  drop_cut              high-impact, big energy_delta     micro_gap_drop
  final_peak            second-to-last → peak             bass_drop_swap or loop_roll_drop
  closer_release        any → closer                      eq_swap_4bar (long)
  hold_groove           groove_holder → groove_holder     harmonic_blend or eq_swap_4bar
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.dj_set.edge_analyzer import TransitionEdge
from app.modules.dj_set.role_classifier import RoleAssessment
from app.modules.dj_set.set_optimizer import DJSet


PURPOSES = (
    "open_to_groove",
    "groove_to_build",
    "build_to_peak",
    "peak_to_reset",
    "reset_to_build",
    "bridge_style_change",
    "vocal_handoff",
    "drop_cut",
    "final_peak",
    "closer_release",
    "hold_groove",
)


@dataclass(frozen=True)
class TransitionPurpose:
    from_track_id: str
    to_track_id: str
    purpose: str
    rule_recommendation: str          # may differ from edge.best_rule when purpose forces it
    reason: str

    def as_dict(self) -> dict:
        return {
            "from": self.from_track_id,
            "to": self.to_track_id,
            "purpose": self.purpose,
            "rule_recommendation": self.rule_recommendation,
            "reason": self.reason,
        }


def _override_rule_for_purpose(edge: TransitionEdge, purpose: str) -> tuple[str, str]:
    """Map purpose → preferred rule (must still be in edge.allowed_rules).

    All rule names use mixer_rules.py's 18-key namespace (11 ANALYZED + 7 RAW).
    """
    pref_map = {
        "open_to_groove":      ["eq_swap_4bar", "harmonic_blend", "raw_xfade_6s"],
        "groove_to_build":     ["eq_swap_4bar", "harmonic_blend", "filter_sweep_high"],
        "build_to_peak":       ["drop_swap", "back_to_back_drop", "key_lift", "loop_roll"],
        "peak_to_reset":       ["drum_only_bridge", "echo_tail", "reverb_throw"],
        "reset_to_build":      ["eq_swap_4bar", "key_lift", "harmonic_blend"],
        "bridge_style_change": ["filter_sweep_high", "harmonic_blend", "eq_swap_4bar"],
        "vocal_handoff":       ["drum_only_bridge", "filter_sweep_high", "eq_swap_4bar"],
        "drop_cut":            ["back_to_back_drop", "drop_swap", "raw_hard_cut"],
        "final_peak":          ["drop_swap", "back_to_back_drop", "loop_roll"],
        "closer_release":      ["echo_tail", "reverb_throw", "raw_fade_out_in"],
        "hold_groove":         ["harmonic_blend", "eq_swap_4bar", "raw_xfade_6s"],
    }
    prefs = pref_map.get(purpose, [])
    for r in prefs:
        if r in edge.allowed_rules:
            if r != edge.best_rule:
                return r, f"purpose='{purpose}' 推荐 {r}（覆盖 edge.best_rule）"
            return r, f"purpose='{purpose}' 与 edge.best_rule 一致"
    # Fallback: keep edge's choice
    return edge.best_rule, f"purpose='{purpose}' 推荐项不可用，回落 edge.best_rule"


def _classify_purpose(prev_role: str, next_role: str,
                      edge: TransitionEdge,
                      is_last_transition: bool,
                      is_first_transition: bool) -> str:
    """Heuristic mapping (prev_role, next_role, edge.energy_delta) → purpose."""
    # Highest priority: closer / final
    if next_role == "closer":
        return "closer_release"
    if is_last_transition and next_role == "peak":
        return "final_peak"
    if next_role == "bridge" or prev_role == "bridge":
        return "bridge_style_change"

    # Vocal handoff trumps role pairs when there's a vocal conflict
    if edge.vocal_conflict:
        return "vocal_handoff"

    # Big energy jump regardless of role
    if edge.energy_delta >= 0.20 and edge.risk_level in ("A", "B", "C"):
        if next_role == "peak":
            return "build_to_peak"
        return "drop_cut"

    # Role-pair table
    pair = (prev_role, next_role)
    if pair == ("opener", "groove_holder") or (is_first_transition and next_role == "groove_holder"):
        return "open_to_groove"
    if pair == ("groove_holder", "builder"):
        return "groove_to_build"
    if pair == ("builder", "peak"):
        return "build_to_peak"
    if pair == ("peak", "reset"):
        return "peak_to_reset"
    if pair == ("reset", "builder"):
        return "reset_to_build"
    if next_role == "vocal_moment" or prev_role == "vocal_moment":
        return "vocal_handoff"
    if pair == ("groove_holder", "groove_holder"):
        return "hold_groove"
    if next_role == "peak":
        return "build_to_peak"
    if next_role == "reset":
        return "peak_to_reset"
    return "hold_groove"


def plan_purposes(dj_set: DJSet,
                  role_map: dict[str, RoleAssessment]) -> list[TransitionPurpose]:
    """Tag every transition in `dj_set` with a purpose + refined rule."""
    out: list[TransitionPurpose] = []
    n_trans = len(dj_set.transitions)
    for i, edge in enumerate(dj_set.transitions):
        prev_id = edge.from_track_id
        next_id = edge.to_track_id
        prev_role = role_map.get(prev_id).primary_role if role_map.get(prev_id) else "groove_holder"
        next_role = role_map.get(next_id).primary_role if role_map.get(next_id) else "groove_holder"
        is_last = (i == n_trans - 1)
        is_first = (i == 0)
        purpose = _classify_purpose(prev_role, next_role, edge, is_last, is_first)
        rule, reason = _override_rule_for_purpose(edge, purpose)
        out.append(TransitionPurpose(
            from_track_id=prev_id,
            to_track_id=next_id,
            purpose=purpose,
            rule_recommendation=rule,
            reason=reason,
        ))
    return out
