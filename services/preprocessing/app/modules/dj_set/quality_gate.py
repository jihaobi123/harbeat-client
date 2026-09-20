"""Set-level Quality Gate.

After optimizer + purpose + plan, every candidate DJSet must pass a
set of binary / scored checks before it's returned to the user.

Categories:
  STRUCTURE     opener exists, closer exists, ≥1 peak (per template)
  TRANSITIONS   no D-grade edges; no >1 consecutive C-grade
  ENERGY        no stale plateau (>3 tracks within ±0.05 dance_energy)
  VOCAL         no 3+ consecutive vocal-heavy
  ROLE          no 3+ consecutive same-role tracks
  DIVERSITY     ≥2 distinct rules across transitions

Output: QualityReport with passed (bool), errors[], warnings[], score_delta.
The router uses this to filter or downgrade a set before returning it.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.dj_set.role_classifier import RoleAssessment
from app.modules.dj_set.set_optimizer import DJSet
from app.modules.dj_set.set_templates import SetTemplate


@dataclass(frozen=True)
class QualityReport:
    passed: bool
    errors: list[str]
    warnings: list[str]
    score_delta: float        # negative = penalize the set
    checks: dict[str, bool]

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "score_delta": round(self.score_delta, 3),
            "checks": dict(self.checks),
        }


def _has_role(arc: list[str], role: str) -> bool:
    return role in arc


def _max_consecutive(arc: list, predicate) -> int:
    best = 0
    cur = 0
    for x in arc:
        if predicate(x):
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def evaluate_quality(dj_set: DJSet,
                     template: SetTemplate,
                     role_map: dict[str, RoleAssessment],
                     profiles_by_id: dict | None = None) -> QualityReport:
    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, bool] = {}
    score_delta = 0.0

    arc = dj_set.narrative_arc

    # ---- structure ----
    has_opener = arc[0] in {"opener", "groove_holder", "vocal_moment"} if arc else False
    has_closer = arc[-1] in {"closer", "reset", "groove_holder"} if arc else False
    peak_count = sum(1 for r in arc if r in {"peak", "weapon"})
    reset_count = sum(1 for r in arc if r == "reset")
    checks["has_opener_role"] = has_opener
    checks["has_closer_role"] = has_closer
    checks["has_peak_when_required"] = peak_count >= max(1, template.peak_count - 1)
    if not has_opener:
        warnings.append("opener slot weak (first track not opener-like)")
        score_delta -= 0.05
    if not has_closer:
        warnings.append("closer slot weak (last track not closer-like)")
        score_delta -= 0.05
    if template.peak_count > 0 and peak_count == 0:
        errors.append(f"template '{template.name}' expects ≥1 peak, found 0")
        score_delta -= 0.20

    # ---- transitions ----
    risks = [t.risk_level for t in dj_set.transitions]
    has_d = "D" in risks
    consec_c = _max_consecutive(risks, lambda r: r == "C")
    checks["no_d_edges"] = not has_d
    checks["no_double_c_edges"] = consec_c <= 1
    if has_d:
        errors.append("set contains a D-grade transition (default forbidden)")
        score_delta -= 0.25
    if consec_c >= 2:
        warnings.append(f"{consec_c} consecutive C-grade transitions — set may feel rough")
        score_delta -= 0.10

    # ---- energy plateau ----
    plateau_run = 0
    max_plateau = 0
    if dj_set.energy_curve:
        prev = dj_set.energy_curve[0]
        run = 1
        for e in dj_set.energy_curve[1:]:
            if abs(e - prev) <= 0.05:
                run += 1
            else:
                run = 1
                prev = e
            max_plateau = max(max_plateau, run)
    checks["no_long_plateau"] = max_plateau <= 3
    if max_plateau >= 4:
        warnings.append(f"{max_plateau} tracks in energy plateau (±0.05)")
        score_delta -= 0.08

    # ---- vocal stacking ----
    consec_vocal = 0
    if profiles_by_id:
        consec_vocal = _max_consecutive(
            dj_set.ordered_tracks,
            lambda tid: tid in profiles_by_id and profiles_by_id[tid].vocal_density >= 0.65,
        )
    checks["no_triple_vocal"] = consec_vocal <= 2
    if consec_vocal >= 3:
        warnings.append(f"{consec_vocal} vocal-heavy tracks in a row")
        score_delta -= 0.08

    # ---- role repetition ----
    consec_role = _max_consecutive(arc, lambda r: True) if not arc else 0
    if arc:
        same_run = 1
        max_same = 1
        for i in range(1, len(arc)):
            if arc[i] == arc[i - 1]:
                same_run += 1
                max_same = max(max_same, same_run)
            else:
                same_run = 1
        consec_role = max_same
    checks["no_role_repetition"] = consec_role <= 2
    if consec_role >= 3:
        warnings.append(f"{consec_role} same-role tracks in a row")
        score_delta -= 0.05

    # ---- rule diversity ----
    rules_used = {t.best_rule for t in dj_set.transitions}
    checks["rule_diversity"] = len(rules_used) >= 2 if len(dj_set.transitions) >= 2 else True
    if len(dj_set.transitions) >= 3 and len(rules_used) < 2:
        warnings.append("only one transition rule used across whole set")
        score_delta -= 0.05

    passed = not errors
    return QualityReport(
        passed=passed,
        errors=errors,
        warnings=warnings,
        score_delta=score_delta,
        checks=checks,
    )
