"""Track Role Classifier.

Each track gets up to 3 role candidates and a list of "not good for" roles.
Roles describe **what slot in a DJ set this track fits**, not just energy.

Roles:
  opener            — calm intro feel; mid energy, low impact, vocal OK
  builder           — pushes from groove → peak; rising tension, mid-high impact
  groove_holder     — steady mid-energy track that locks in a BPM lane
  peak              — high impact + density + tempo; the chorus moment
  reset             — release after peak; drops energy + density
  bridge            — connects two style/BPM lanes; mid energy, neutral
  closer            — graceful exit; energy descending, low tension
  weapon            — battle-ready, very high impact (kick+snare both >0.7)
  vocal_moment      — strong vocal hook for crowd recognition
"""
from __future__ import annotations

from dataclasses import dataclass

from app.modules.dj_set.track_profiler import TrackProfile


ALL_ROLES = (
    "opener", "builder", "groove_holder", "peak", "reset",
    "bridge", "closer", "weapon", "vocal_moment",
)


@dataclass(frozen=True)
class RoleAssessment:
    track_id: str
    role_candidates: list[str]
    not_good_for: list[str]
    role_scores: dict[str, float]
    primary_role: str

    def as_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "primary_role": self.primary_role,
            "candidates": list(self.role_candidates),
            "not_good_for": list(self.not_good_for),
            "scores": {k: round(v, 3) for k, v in self.role_scores.items()},
        }


def _score_opener(p: TrackProfile) -> float:
    # Mid energy (0.35-0.55), low-mid impact, OK with vocals.
    e = p.dance_energy
    e_fit = 1.0 - min(1.0, abs(e - 0.45) / 0.30)
    impact_fit = 1.0 - min(1.0, max(0.0, p.impact_energy - 0.6) / 0.4)
    confidence_fit = p.beat_confidence
    return float(0.45 * e_fit + 0.30 * impact_fit + 0.25 * confidence_fit)


def _score_builder(p: TrackProfile) -> float:
    # Mid-high energy with rising tension; impact 0.5-0.75
    e = p.dance_energy
    e_fit = 1.0 - min(1.0, abs(e - 0.65) / 0.25)
    tension_fit = min(1.0, p.tension_energy / 0.7)
    impact_fit = 1.0 - min(1.0, abs(p.impact_energy - 0.6) / 0.35)
    return float(0.40 * e_fit + 0.30 * tension_fit + 0.30 * impact_fit)


def _score_groove_holder(p: TrackProfile) -> float:
    # Tight groove, mid energy, low tension swing
    return float(
        0.45 * p.groove_tightness
        + 0.25 * (1.0 - min(1.0, abs(p.dance_energy - 0.55) / 0.30))
        + 0.30 * p.beat_confidence
    )


def _score_peak(p: TrackProfile) -> float:
    # High impact, high density, BPM ≥ 110
    e_fit = min(1.0, p.dance_energy / 0.85)
    impact_fit = min(1.0, p.impact_energy / 0.80)
    density_fit = min(1.0, p.density_energy / 0.75)
    bpm_fit = 1.0 if p.bpm >= 110 else max(0.0, (p.bpm - 90) / 20.0)
    return float(0.30 * e_fit + 0.30 * impact_fit + 0.25 * density_fit + 0.15 * bpm_fit)


def _score_reset(p: TrackProfile) -> float:
    # Lower energy, lower impact, fewer phrase changes
    e_fit = 1.0 - min(1.0, abs(p.dance_energy - 0.40) / 0.30)
    impact_fit = 1.0 - min(1.0, p.impact_energy / 0.70)
    tension_fit = 1.0 - min(1.0, p.tension_energy / 0.70)
    return float(0.40 * e_fit + 0.30 * impact_fit + 0.30 * tension_fit)


def _score_bridge(p: TrackProfile) -> float:
    # Neutral on energy, has stems (so we can do clean fades), good groove
    has_stems = 1.0 if p.stems_available else 0.4
    neutral = 1.0 - min(1.0, abs(p.dance_energy - 0.55) / 0.35)
    return float(0.40 * neutral + 0.30 * has_stems + 0.30 * p.groove_tightness)


def _score_closer(p: TrackProfile) -> float:
    # Lower energy at the end, calmer impact
    e_fit = 1.0 - min(1.0, p.dance_energy / 0.55)
    impact_fit = 1.0 - min(1.0, p.impact_energy / 0.55)
    duration_fit = 1.0 if 120 <= p.duration <= 300 else 0.5
    return float(0.40 * e_fit + 0.35 * impact_fit + 0.25 * duration_fit)


def _score_weapon(p: TrackProfile) -> float:
    # Both kick AND snare must be punchy + low_mid thick
    if p.kick_punch < 0.6 or p.snare_crack < 0.6:
        return 0.0
    return float(0.40 * p.kick_punch + 0.40 * p.snare_crack + 0.20 * p.low_mid_density)


def _score_vocal_moment(p: TrackProfile) -> float:
    # High vocal density + decent energy
    e_fit = min(1.0, p.dance_energy / 0.70)
    return float(0.55 * p.vocal_density + 0.45 * e_fit)


_SCORERS = {
    "opener": _score_opener,
    "builder": _score_builder,
    "groove_holder": _score_groove_holder,
    "peak": _score_peak,
    "reset": _score_reset,
    "bridge": _score_bridge,
    "closer": _score_closer,
    "weapon": _score_weapon,
    "vocal_moment": _score_vocal_moment,
}


def classify_track(profile: TrackProfile) -> RoleAssessment:
    scores = {role: _SCORERS[role](profile) for role in ALL_ROLES}
    sorted_roles = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    # Candidates: top 3 with score >= 0.5; primary = #1.
    candidates = [r for r, s in sorted_roles if s >= 0.50][:3]
    if not candidates:
        candidates = [sorted_roles[0][0]]
    primary = candidates[0]

    not_good = [r for r, s in scores.items() if s < 0.30]

    return RoleAssessment(
        track_id=profile.track_id,
        role_candidates=candidates,
        not_good_for=not_good,
        role_scores=scores,
        primary_role=primary,
    )
