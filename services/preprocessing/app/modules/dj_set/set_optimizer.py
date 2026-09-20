"""Stateful Set Optimizer — graph search per template.

Input:
    profiles      : list[TrackProfile]   — songs the user picked
    role_map      : dict[track_id, RoleAssessment]
    edges         : dict[(a,b), TransitionEdge]
    template      : SetTemplate
    target_length : int (default = len(profiles); ≤ len(profiles))

Output:
    DJSet object with:
      ordered_tracks : list[track_id]
      transitions    : list[TransitionEdge]   (between consecutive tracks)
      score          : float
      score_breakdown: dict
      template_name  : str
      narrative_arc  : list[str]              (role per slot)
      energy_curve   : list[float]            (per slot)
      warnings       : list[str]

Strategy: **beam search**, not exhaustive — N=8 songs has 40320 orders,
N=12 has ~4.8e8. Beam keeps the top K partial paths; each step expands
all unused tracks, scores them under the current state, prunes to K.

State carried per partial path:
    used_tracks                 : set[str]
    recent_avg_energy           : rolling window
    current_bpm_lane            : float
    peak_count                  : int
    reset_count                 : int
    consecutive_high_energy     : int
    consecutive_high_vocal      : int
    last_transition_rule        : str
    role_history                : list[str]
    cumulative_score            : float

Score per step = w_edge*edge.transition_score + w_role*role_fit
                 + w_energy*energy_arch_fit + w_state*state_penalty
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable

from app.modules.dj_set.edge_analyzer import TransitionEdge
from app.modules.dj_set.role_classifier import RoleAssessment
from app.modules.dj_set.set_templates import SetTemplate
from app.modules.dj_set.track_profiler import TrackProfile


# Default scoring weights — overridable per template.
DEFAULT_WEIGHTS = {
    "average_edge_score":  0.30,
    "narrative_fit":       0.20,
    "energy_arch_fit":     0.15,
    "peak_reset_balance":  0.10,
    "groove_continuity":   0.10,
    "vocal_flow":          0.05,
    "diversity":           0.05,
    "track_role_fit":      0.05,
}

# Risk-level → numeric for thresholding
_RISK_NUM = {"A": 4, "B": 3, "C": 2, "D": 1}


@dataclass(frozen=True)
class DJSet:
    template_name: str
    ordered_tracks: list[str]
    transitions: list[TransitionEdge]
    score: float
    score_breakdown: dict[str, float]
    narrative_arc: list[str]
    energy_curve: list[float]
    warnings: list[str]

    def as_dict(self) -> dict:
        return {
            "template": self.template_name,
            "score": round(self.score, 3),
            "breakdown": {k: round(v, 3) for k, v in self.score_breakdown.items()},
            "tracks": list(self.ordered_tracks),
            "narrative_arc": list(self.narrative_arc),
            "energy_curve": [round(e, 3) for e in self.energy_curve],
            "transitions": [t.as_dict() for t in self.transitions],
            "warnings": list(self.warnings),
        }


# ---- internal beam state -------------------------------------------------

@dataclass
class _Path:
    order: list[str]
    transitions: list[TransitionEdge]
    used: set[str]
    recent_energy_window: list[float]
    current_bpm: float
    peak_count: int
    reset_count: int
    consec_high_energy: int
    consec_high_vocal: int
    last_rule: str
    role_history: list[str]
    energy_curve: list[float]
    cum_score: float
    notes: list[str] = field(default_factory=list)


def _energy_arch_fit(template: SetTemplate, energy_curve: list[float],
                     length: int) -> float:
    if not energy_curve or length <= 1:
        return 0.5
    diffs = []
    for i, e in enumerate(energy_curve):
        target = template.target_energy(i / max(1, length - 1))
        diffs.append(abs(e - target))
    avg_diff = sum(diffs) / len(diffs)
    return float(max(0.0, 1.0 - avg_diff * 2.0))


def _role_fit(role: str, slot_role: str | None,
              candidates: Iterable[str]) -> float:
    if slot_role is None:
        return 0.6
    if role == slot_role:
        return 1.0
    if slot_role in candidates:
        return 0.8
    # Soft compatibility table: groove_holder can stand in for opener/closer
    soft = {
        "opener": {"groove_holder", "vocal_moment"},
        "closer": {"reset", "groove_holder"},
        "peak": {"weapon"},
        "weapon": {"peak"},
        "builder": {"groove_holder"},
        "reset": {"closer", "groove_holder"},
        "vocal_moment": {"groove_holder"},
        "bridge": {"groove_holder"},
        "groove_holder": {"builder"},
    }
    if role in soft.get(slot_role, set()):
        return 0.6
    return 0.3


def _slot_role_for(template: SetTemplate, slot_idx: int, total_slots: int) -> str | None:
    """Map slot index to template role_skeleton entry. Stretches/compresses skeleton."""
    sk = template.role_skeleton
    if not sk:
        return None
    if total_slots <= 1:
        return sk[0]
    # Linear stretch — slot 0 -> sk[0], slot last -> sk[-1]
    pos = slot_idx / (total_slots - 1)
    idx = min(len(sk) - 1, int(round(pos * (len(sk) - 1))))
    return sk[idx]


def _stem_diversity(transitions: list[TransitionEdge]) -> float:
    if not transitions:
        return 0.5
    rules = [t.best_rule for t in transitions]
    unique = len(set(rules))
    return float(min(1.0, unique / max(2, len(rules) * 0.6)))


def _vocal_flow(profiles_by_id: dict[str, TrackProfile],
                order: list[str], target_balance: float) -> float:
    if len(order) < 2:
        return 0.6
    vds = [profiles_by_id[t].vocal_density for t in order if t in profiles_by_id]
    if not vds:
        return 0.5
    avg = sum(vds) / len(vds)
    # Penalize 3+ vocal-heavy in a row
    streak = 0
    max_streak = 0
    for vd in vds:
        if vd >= 0.65:
            streak += 1
            max_streak = max(max_streak, streak)
        else:
            streak = 0
    streak_penalty = max(0.0, (max_streak - 2) * 0.20)
    balance_penalty = abs(avg - target_balance)
    return float(max(0.0, 1.0 - streak_penalty - balance_penalty))


def _peak_reset_balance(template: SetTemplate,
                        peak_count: int, reset_count: int) -> float:
    pf = 1.0 - min(1.0, abs(peak_count - template.peak_count) / max(1, template.peak_count + 1))
    rf = 1.0 - min(1.0, abs(reset_count - template.reset_count) / max(1, template.reset_count + 1))
    return float(0.5 * pf + 0.5 * rf)


def _groove_continuity(transitions: list[TransitionEdge]) -> float:
    if not transitions:
        return 0.6
    return float(sum(t.performance_score for t in transitions) / len(transitions))


def _final_set_score(template: SetTemplate,
                     profiles_by_id: dict[str, TrackProfile],
                     role_map: dict[str, RoleAssessment],
                     order: list[str],
                     transitions: list[TransitionEdge],
                     energy_curve: list[float],
                     peak_count: int,
                     reset_count: int) -> tuple[float, dict[str, float]]:
    weights = dict(DEFAULT_WEIGHTS)
    for k, v in (template.weight_overrides or {}).items():
        if k in weights:
            weights[k] = v
    # re-normalize
    s = sum(weights.values())
    if s > 0:
        weights = {k: v / s for k, v in weights.items()}

    avg_edge = (
        sum(t.transition_score for t in transitions) / len(transitions)
        if transitions else 0.5
    )
    role_fit_sum = 0.0
    for i, tid in enumerate(order):
        slot = _slot_role_for(template, i, len(order))
        ra = role_map.get(tid)
        role = ra.primary_role if ra else "groove_holder"
        cands = ra.role_candidates if ra else []
        role_fit_sum += _role_fit(role, slot, cands)
    narrative_fit = role_fit_sum / max(1, len(order))
    track_role_fit = narrative_fit  # same signal, different weight bucket
    arch_fit = _energy_arch_fit(template, energy_curve, len(order))
    pr_balance = _peak_reset_balance(template, peak_count, reset_count)
    groove_cont = _groove_continuity(transitions)
    vocal = _vocal_flow(profiles_by_id, order, template.vocal_balance)
    div = _stem_diversity(transitions)

    breakdown = {
        "average_edge_score": avg_edge,
        "narrative_fit": narrative_fit,
        "energy_arch_fit": arch_fit,
        "peak_reset_balance": pr_balance,
        "groove_continuity": groove_cont,
        "vocal_flow": vocal,
        "diversity": div,
        "track_role_fit": track_role_fit,
    }
    score = sum(weights[k] * breakdown[k] for k in weights)
    return float(score), breakdown


def _step_score(template: SetTemplate,
                profile: TrackProfile,
                role: RoleAssessment | None,
                edge: TransitionEdge | None,
                slot_idx: int,
                total_slots: int,
                state: _Path) -> tuple[float, list[str]]:
    """Greedy per-step score used during beam expansion.

    Heavy weight on edge.transition_score so we never pick a 'great role
    fit' that would require a D-grade transition.
    """
    notes: list[str] = []
    slot_role = _slot_role_for(template, slot_idx, total_slots)
    role_fit = _role_fit(role.primary_role if role else "groove_holder",
                         slot_role,
                         role.role_candidates if role else [])

    # Edge score (only set after the first slot)
    if edge is not None:
        edge_score = edge.transition_score
        # Hard floor by template.allowed_risk
        allowed_num = _RISK_NUM.get(template.allowed_risk, 3)
        edge_num = _RISK_NUM.get(edge.risk_level, 1)
        if edge_num < allowed_num:
            notes.append(f"edge {edge.risk_level} below {template.allowed_risk}")
            edge_score *= 0.40  # heavy penalty but not zero — let optimizer try
    else:
        edge_score = 0.65  # neutral for first slot

    # Energy arch fit at this slot
    target = template.target_energy(slot_idx / max(1, total_slots - 1))
    e_diff = abs(profile.dance_energy - target)
    arch_step = max(0.0, 1.0 - e_diff * 2.0)

    # State penalties
    state_penalty = 0.0
    if state.consec_high_energy >= 2 and profile.dance_energy >= 0.75:
        state_penalty += 0.15
        notes.append("third high-energy in a row")
    if state.consec_high_vocal >= 2 and profile.vocal_density >= 0.70:
        state_penalty += 0.15
        notes.append("third vocal-heavy in a row")
    if edge is not None and edge.best_rule == state.last_rule:
        state_penalty += 0.05  # rule monotony

    s = (
        0.45 * edge_score
        + 0.25 * role_fit
        + 0.20 * arch_step
        - state_penalty
    )
    return float(max(0.0, s)), notes


def _initial_paths(profiles: list[TrackProfile],
                   role_map: dict[str, RoleAssessment],
                   template: SetTemplate,
                   total_slots: int,
                   beam: int) -> list[_Path]:
    """Seed beam with best opener candidates."""
    seeds: list[tuple[float, TrackProfile]] = []
    for p in profiles:
        ra = role_map.get(p.track_id)
        slot_role = _slot_role_for(template, 0, total_slots)
        rf = _role_fit(ra.primary_role if ra else "groove_holder",
                       slot_role,
                       ra.role_candidates if ra else [])
        target = template.target_energy(0.0)
        arch = max(0.0, 1.0 - abs(p.dance_energy - target) * 2.0)
        s = 0.55 * rf + 0.45 * arch
        seeds.append((s, p))
    seeds.sort(key=lambda kv: kv[0], reverse=True)
    out: list[_Path] = []
    for s, p in seeds[:beam]:
        path = _Path(
            order=[p.track_id],
            transitions=[],
            used={p.track_id},
            recent_energy_window=[p.dance_energy],
            current_bpm=p.bpm,
            peak_count=1 if (role_map.get(p.track_id) and role_map[p.track_id].primary_role == "peak") else 0,
            reset_count=1 if (role_map.get(p.track_id) and role_map[p.track_id].primary_role == "reset") else 0,
            consec_high_energy=1 if p.dance_energy >= 0.75 else 0,
            consec_high_vocal=1 if p.vocal_density >= 0.70 else 0,
            last_rule="",
            role_history=[role_map.get(p.track_id).primary_role if role_map.get(p.track_id) else "groove_holder"],
            energy_curve=[p.dance_energy],
            cum_score=s,
        )
        out.append(path)
    return out


def _expand(path: _Path,
            profiles_by_id: dict[str, TrackProfile],
            role_map: dict[str, RoleAssessment],
            edges: dict[tuple[str, str], TransitionEdge],
            template: SetTemplate,
            total_slots: int) -> list[_Path]:
    """Generate all child paths for one beam state."""
    children: list[_Path] = []
    soft_children: list[_Path] = []   # D-edge children, used only as fallback
    last_id = path.order[-1]
    slot_idx = len(path.order)  # the slot we are about to fill
    for tid, prof in profiles_by_id.items():
        if tid in path.used:
            continue
        edge = edges.get((last_id, tid))
        if edge is None:
            continue
        ra = role_map.get(tid)
        s, notes = _step_score(template, prof, ra, edge, slot_idx, total_slots, path)
        # Soft D-edge handling: B-tier templates strongly prefer A/B/C, but if
        # the user's pool happens to have no good neighbours, we still produce
        # a set (heavy penalty + warning) instead of returning nothing. The
        # quality gate later flags the result with score_delta and warnings,
        # so the user sees 5 cards and can judge — empty UI is worse.
        is_d_below_floor = (
            edge.risk_level == "D"
            and template.allowed_risk in ("A", "B")
        )
        if is_d_below_floor:
            s *= 0.20
            notes = notes + [f"D-edge below {template.allowed_risk} floor"]
        new_role = ra.primary_role if ra else "groove_holder"
        new_path = _Path(
            order=path.order + [tid],
            transitions=path.transitions + [edge],
            used=path.used | {tid},
            recent_energy_window=(path.recent_energy_window + [prof.dance_energy])[-3:],
            current_bpm=prof.bpm,
            peak_count=path.peak_count + (1 if new_role == "peak" else 0),
            reset_count=path.reset_count + (1 if new_role == "reset" else 0),
            consec_high_energy=path.consec_high_energy + 1 if prof.dance_energy >= 0.75 else 0,
            consec_high_vocal=path.consec_high_vocal + 1 if prof.vocal_density >= 0.70 else 0,
            last_rule=edge.best_rule,
            role_history=path.role_history + [new_role],
            energy_curve=path.energy_curve + [prof.dance_energy],
            cum_score=path.cum_score + s,
            notes=path.notes + notes,
        )
        if is_d_below_floor:
            soft_children.append(new_path)
        else:
            children.append(new_path)
    # Use D-edge fallback only if no clean child exists at this step.
    return children if children else soft_children


def optimize_set(profiles: list[TrackProfile],
                 role_map: dict[str, RoleAssessment],
                 edges: dict[tuple[str, str], TransitionEdge],
                 template: SetTemplate,
                 target_length: int | None = None,
                 beam_width: int = 12) -> DJSet | None:
    """Beam search the best ordering for `template`.

    Returns None if no path of length target_length exists (e.g. all
    edges from one node are D-grade).
    """
    if not profiles:
        return None
    profiles_by_id = {p.track_id: p for p in profiles}
    n = len(profiles)
    target_length = target_length or n
    target_length = min(target_length, n)

    paths = _initial_paths(profiles, role_map, template, target_length, beam_width)
    for _ in range(target_length - 1):
        next_paths: list[_Path] = []
        for p in paths:
            next_paths.extend(_expand(p, profiles_by_id, role_map, edges,
                                      template, target_length))
        if not next_paths:
            return None
        next_paths.sort(key=lambda pp: pp.cum_score, reverse=True)
        paths = next_paths[:beam_width]

    # Final scoring on full sets
    best: tuple[float, _Path, dict[str, float]] | None = None
    for p in paths:
        score, breakdown = _final_set_score(template, profiles_by_id, role_map,
                                            p.order, p.transitions,
                                            p.energy_curve,
                                            p.peak_count, p.reset_count)
        if best is None or score > best[0]:
            best = (score, p, breakdown)
    if best is None:
        return None
    score, p, breakdown = best

    warnings: list[str] = []
    if p.peak_count == 0:
        warnings.append("set has no peak track")
    if any(e.risk_level == "D" for e in p.transitions):
        warnings.append("set contains a D-grade transition")
    if p.notes:
        warnings.extend(sorted(set(p.notes))[:5])

    return DJSet(
        template_name=template.name,
        ordered_tracks=p.order,
        transitions=p.transitions,
        score=score,
        score_breakdown=breakdown,
        narrative_arc=p.role_history,
        energy_curve=p.energy_curve,
        warnings=warnings,
    )


def optimize_all_templates(profiles: list[TrackProfile],
                           role_map: dict[str, RoleAssessment],
                           edges: dict[tuple[str, str], TransitionEdge],
                           templates: list[SetTemplate],
                           target_length: int | None = None,
                           beam_width: int = 12) -> list[DJSet]:
    """Run optimize_set for each template, dropping Nones."""
    out: list[DJSet] = []
    for tpl in templates:
        ds = optimize_set(profiles, role_map, edges, tpl,
                          target_length=target_length, beam_width=beam_width)
        if ds is not None:
            out.append(ds)
    return out
