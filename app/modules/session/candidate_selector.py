"""C3 Candidate Selector — rule-based track recommendation engine.

Implements the CandidateSelector protocol from coordinator.py.
Scores and ranks tracks using DJ-relevant criteria:
  scene_fit, energy_fit, transition_compatibility,
  diversity, anti-repetition, cold_start_risk.

Reads C1 TrackAnalysis data (READ ONLY).
Stateless — all state comes from C6 session context.

This is the V0.1 rule engine. V0.2+ can add ML-based re-ranking
without changing the C6↔C3 interface.
"""

from __future__ import annotations

import logging
from typing import Any

from .schemas import Candidate, CandidateList, SceneConfig

logger = logging.getLogger(__name__)

# ── Scoring weights (tunable per scene) ──────────────────────────────────────
DEFAULT_WEIGHTS = {
    "scene_fit": 0.25,
    "danceability": 0.20,
    "energy_fit": 0.15,
    "transition_compat": 0.15,
    "group_preference": 0.10,
    "diversity_bonus": 0.10,
    "repetition_penalty": 0.10,   # applied as negative
    "cold_start_risk": 0.10,       # applied as negative
}

# BPM ratio compatibility tiers
BPM_SAFE_BLEND = 1.03     # ±3%
BPM_STRETCH_OK = 1.06     # ±6%
BPM_STYLE_CHANGE = 1.12   # ±12%
BPM_HARD_CUT = float("inf")


class CandidateSelector:
    """Rule-based next-track selector implementing the C6 protocol.

    Usage:
        selector = CandidateSelector(track_registry)
        candidates = selector.select_candidates(
            current_track_id="trk_001",
            session_state="build",
            target_energy=0.7,
            current_energy=0.55,
            avoid_ids=["trk_001", "trk_002"],
            intent="energy_up",
        )
    """

    def __init__(
        self,
        track_registry: dict[str, dict] | None = None,
        weights: dict[str, float] | None = None,
    ):
        """Initialize with a track registry.

        track_registry: {track_id: {bpm, key, camelot_key, energy, genre_profile,
                                    groove_profile, transition_windows,
                                    beat_confidence, intro_is_clean, ...}}
        """
        self._tracks: dict[str, dict] = track_registry or {}
        self._weights = {**DEFAULT_WEIGHTS, **(weights or {})}

    # ── public API (CandidateSelector protocol) ─────────────────────────

    def select_candidates(
        self,
        current_track_id: str = "",
        session_state: str = "warmup",
        target_energy: float = 0.5,
        current_energy: float = 0.5,
        avoid_ids: list[str] | None = None,
        intent: str | None = None,
        scene: SceneConfig | None = None,
        **_kwargs,
    ) -> CandidateList:
        """Score all available tracks and return ranked candidates.

        Returns CandidateList with best, safe, diverse candidates + fallback.
        """
        avoid = set(avoid_ids or [])
        if current_track_id:
            avoid.add(current_track_id)

        available = {
            tid: t for tid, t in self._tracks.items()
            if tid not in avoid
        }
        if not available:
            logger.warning("[c3] no available tracks after filtering")
            return CandidateList(candidates=[], fallback_track_id="")

        # Score every track
        scored: list[tuple[str, float, dict]] = []
        for tid, track in available.items():
            score, breakdown = self._score_track(
                track=track,
                current_track=self._tracks.get(current_track_id),
                target_energy=target_energy,
                current_energy=current_energy,
                session_state=session_state,
                intent=intent,
                scene=scene,
            )
            scored.append((tid, score, breakdown))

        scored.sort(key=lambda x: -x[1])

        # Build candidates
        candidates: list[Candidate] = []
        for tid, score, breakdown in scored[:10]:
            track = available[tid]
            candidates.append(Candidate(
                track_id=tid,
                score=round(score, 4),
                reason=self._build_reason(breakdown),
                template=self._pick_template(track, self._tracks.get(current_track_id)),
                energy_fit=round(breakdown.get("energy_fit", 0.0), 3),
                bpm_ratio=round(self._bpm_ratio(track, self._tracks.get(current_track_id)), 3),
                warnings=self._build_warnings(track, self._tracks.get(current_track_id)),
            ))

        # Select best, safe, diverse
        best = candidates[0] if candidates else None

        # Safe: highest score with beat_confidence > 0.85 + clean intro
        safe_candidates = [
            c for c in candidates
            if self._is_safe(available.get(c.track_id, {}))
        ]
        safe = safe_candidates[0] if safe_candidates else (candidates[1] if len(candidates) > 1 else best)

        # Diverse: high score but different genre from best
        best_genre = self._get_genre(available.get(best.track_id, {})) if best else ""
        diverse_candidates = [
            c for c in candidates
            if self._get_genre(available.get(c.track_id, {})) != best_genre
        ]
        diverse = diverse_candidates[0] if diverse_candidates else (candidates[2] if len(candidates) > 2 else safe)

        # Fallback: safest track overall (from safety pool criteria)
        fallback_id = ""
        for c in candidates:
            if self._is_safe(available.get(c.track_id, {})):
                fallback_id = c.track_id
                break
        if not fallback_id and candidates:
            fallback_id = candidates[0].track_id

        logger.info(
            "[c3] selected %d candidates: best=%s(%.2f) safe=%s diverse=%s",
            len(candidates),
            best.track_id if best else "?", best.score if best else 0,
            safe.track_id if safe else "?",
            diverse.track_id if diverse else "?",
        )

        return CandidateList(
            candidates=candidates[:5],
            best=best,
            safe=safe,
            diverse=diverse,
            fallback_track_id=fallback_id,
            context={
                "session_state": session_state,
                "target_energy": target_energy,
                "intent": intent,
            },
        )

    # ── scoring ─────────────────────────────────────────────────────────

    def _score_track(
        self,
        track: dict,
        current_track: dict | None,
        target_energy: float,
        current_energy: float,
        session_state: str,
        intent: str | None = None,
        scene: SceneConfig | None = None,
    ) -> tuple[float, dict]:
        """Score a single track. Returns (score, breakdown)."""
        w = self._weights
        breakdown: dict[str, float] = {}

        # 1. Scene fit: dance style match + genre match
        scene_fit = self._scene_fit(track, scene)
        breakdown["scene_fit"] = scene_fit

        # 2. Danceability
        groove = track.get("groove_profile", {})
        danceability = float(track.get("danceability_score", groove.get("score", 0.5)))
        breakdown["danceability"] = danceability

        # 3. Energy fit
        track_energy = float(track.get("energy", 0.5))
        energy_fit = 1.0 - min(1.0, abs(track_energy - target_energy) / 0.5)
        # If intent is energy_up, prefer slightly higher energy
        if intent == "energy_up" and track_energy > current_energy:
            energy_fit += 0.15
        elif intent == "energy_down" and track_energy < current_energy:
            energy_fit += 0.15
        energy_fit = min(1.0, energy_fit)
        breakdown["energy_fit"] = energy_fit

        # 4. Transition compatibility
        trans_compat = self._transition_compat(track, current_track)
        breakdown["transition_compat"] = trans_compat

        # 5. Group preference (from scene config)
        group_pref = self._group_pref(track, scene)
        breakdown["group_preference"] = group_pref

        # 6. Diversity bonus
        diversity = self._diversity_bonus(track, current_track)
        breakdown["diversity_bonus"] = diversity

        # 7. Repetition penalty (handled by avoid_ids in select_candidates)
        #    This residual penalty is for same-artist / same-remix
        rep_penalty = 0.0
        if current_track:
            if track.get("artist") == current_track.get("artist"):
                rep_penalty += 0.5
        breakdown["repetition_penalty"] = rep_penalty

        # 8. Cold start risk
        cold_start = self._cold_start_risk(track, session_state)
        breakdown["cold_start_risk"] = cold_start

        # Weighted sum
        score = (
            w["scene_fit"] * scene_fit
            + w["danceability"] * danceability
            + w["energy_fit"] * energy_fit
            + w["transition_compat"] * trans_compat
            + w["group_preference"] * group_pref
            + w["diversity_bonus"] * diversity
            - w["repetition_penalty"] * rep_penalty
            - w["cold_start_risk"] * cold_start
        )

        return max(0.0, score), breakdown

    def _scene_fit(self, track: dict, scene: SceneConfig | None) -> float:
        """How well does this track fit the scene/dance style?"""
        if not scene:
            return 0.5

        score = 0.5  # baseline

        # Dance style match
        dance_scores = track.get("dance_style_scores", {})
        for style in scene.dance_styles:
            s = dance_scores.get(style, 0.0)
            score = max(score, s)

        # Genre match
        genre_prof = track.get("genre_profile", {})
        primary_genre = str(genre_prof.get("primary_genre", "")).lower()
        # Map dance styles to preferred genres
        style_genre_map = {
            "hiphop": ["hip-hop", "funk", "r-and-b"],
            "house": ["house", "disco", "electronic"],
            "breaking": ["funk", "hip-hop", "breaks"],
            "krump": ["hip-hop", "dubstep"],
            "popping": ["funk", "electronic", "hip-hop"],
            "locking": ["funk", "disco", "house"],
            "waacking": ["disco", "house", "pop"],
        }
        for style in scene.dance_styles:
            preferred = style_genre_map.get(style, [])
            if primary_genre in preferred:
                score = max(score, 0.8)
                break

        return float(min(1.0, score))

    def _transition_compat(self, track: dict, current: dict | None) -> float:
        """Score BPM + key compatibility between two tracks."""
        if not current:
            return 0.6  # unknown, neutral

        score = 0.5

        # BPM compatibility
        bpm_a = float(current.get("bpm", 0))
        bpm_b = float(track.get("bpm", 0))
        if bpm_a > 0 and bpm_b > 0:
            ratio = max(bpm_a, bpm_b) / min(bpm_a, bpm_b)
            if ratio <= BPM_SAFE_BLEND:
                score += 0.35
            elif ratio <= BPM_STRETCH_OK:
                score += 0.20
            elif ratio <= BPM_STYLE_CHANGE:
                score += 0.05
            else:
                score -= 0.20

        # Key compatibility (Camelot)
        key_a = str(current.get("camelot_key", ""))
        key_b = str(track.get("camelot_key", ""))
        if key_a and key_b:
            try:
                from app.modules.library.analysis import camelot_distance
                dist = camelot_distance(key_a, key_b)
                if dist == 0:
                    score += 0.15
                elif dist == 1:
                    score += 0.10
                elif dist == 2:
                    score += 0.05
                # dist >= 3: no bonus, no penalty
            except Exception:
                pass

        # Stem compatibility (avoid double vocal, bass clash)
        stem_a = current.get("stem_activity", {})
        stem_b = track.get("stem_activity", {})
        if stem_a and stem_b:
            vocal_a = float(stem_a.get("vocals", 0))
            vocal_b = float(stem_b.get("vocals", 0))
            if vocal_a > 0.5 and vocal_b > 0.5:
                score -= 0.15  # double vocal risk
            bass_a = float(stem_a.get("bass", 0))
            bass_b = float(stem_b.get("bass", 0))
            if bass_a > 0.6 and bass_b > 0.6:
                score -= 0.10  # bass clash risk

        return float(max(0.0, min(1.0, score)))

    def _group_pref(self, track: dict, scene: SceneConfig | None) -> float:
        """Match against scene preference/avoidance tags."""
        if not scene:
            return 0.5
        score = 0.5
        genre_prof = track.get("genre_profile", {})
        genres = [g.get("name", "") for g in genre_prof.get("genres", [])]

        # Prefer tags match
        for tag in scene.prefer_tags:
            if tag.lower() in [g.lower() for g in genres]:
                score += 0.2

        # Avoid tags penalty
        for tag in scene.avoid_tags:
            if tag.lower() in [g.lower() for g in genres]:
                score -= 0.4

        return float(max(0.0, min(1.0, score)))

    def _diversity_bonus(self, track: dict, current: dict | None) -> float:
        """Reward tracks that are stylistically different from the current one."""
        if not current:
            return 0.5

        current_genre = self._get_genre(current)
        track_genre = self._get_genre(track)

        if current_genre and track_genre and current_genre != track_genre:
            return 0.7  # genre diversity bonus
        return 0.3  # same genre — still fine, just no bonus

    def _cold_start_risk(self, track: dict, session_state: str) -> float:
        """Penalize tracks that risk killing the energy."""
        risk = 0.0

        # Long intro risk
        if not track.get("intro_is_clean"):
            risk += 0.3

        # Weak beat risk
        beat_conf = float(track.get("beat_confidence", 1.0))
        if beat_conf < 0.7:
            risk += 0.3

        # Low energy in peak/build state
        if session_state in ("peak", "build"):
            energy = float(track.get("energy", 0.5))
            if energy < 0.3:
                risk += 0.4

        return float(min(1.0, risk))

    # ── helpers ─────────────────────────────────────────────────────────

    def _bpm_ratio(self, track: dict, current: dict | None) -> float:
        if not current:
            return 1.0
        a = float(current.get("bpm", 0))
        b = float(track.get("bpm", 0))
        if a <= 0 or b <= 0:
            return 1.0
        return round(max(a, b) / min(a, b), 3)

    @staticmethod
    def _get_genre(track: dict) -> str:
        gp = track.get("genre_profile", {})
        return str(gp.get("primary_genre", "")).lower()

    @staticmethod
    def _is_safe(track: dict) -> bool:
        """Check if a track is a 'safe' choice (reliable beat, clean structure)."""
        if float(track.get("beat_confidence", 0)) < 0.85:
            return False
        if not track.get("intro_is_clean"):
            return False
        if track.get("intro_clean_score") is not None:
            if float(track["intro_clean_score"]) < 0.6:
                return False
        return True

    @staticmethod
    def _pick_template(track: dict, current: dict | None) -> str:
        """Pick the best transition template."""
        if not current:
            return "safe_blend"
        ratio = max(
            float(current.get("bpm", 120)), float(track.get("bpm", 120))
        ) / min(
            float(current.get("bpm", 120)), float(track.get("bpm", 120))
        )
        if ratio <= BPM_SAFE_BLEND:
            return "safe_blend"
        elif ratio <= BPM_STRETCH_OK:
            return "safe_blend"  # with time-stretch
        elif ratio <= BPM_STYLE_CHANGE:
            return "drop_in"
        else:
            return "style_change"

    @staticmethod
    def _build_reason(breakdown: dict) -> str:
        """Build a human-readable reason from scoring breakdown."""
        parts = []
        top = sorted(breakdown.items(), key=lambda x: -x[1])
        for name, val in top[:3]:
            if val > 0.6:
                labels = {
                    "scene_fit": "舞种匹配", "danceability": "好跳",
                    "energy_fit": "能量合适", "transition_compat": "好接",
                    "group_preference": "符合偏好", "diversity_bonus": "风格多样",
                }
                parts.append(labels.get(name, name))
        return ", ".join(parts) if parts else "综合匹配"

    @staticmethod
    def _build_warnings(track: dict, current: dict | None) -> list[str]:
        """Generate transition warnings."""
        warnings = []
        if not current:
            return warnings

        # BPM jump warning
        bpm_a = float(current.get("bpm", 0))
        bpm_b = float(track.get("bpm", 0))
        if bpm_a > 0 and bpm_b > 0:
            ratio = max(bpm_a, bpm_b) / min(bpm_a, bpm_b)
            if ratio > BPM_STRETCH_OK:
                warnings.append(f"bpm_jump: {bpm_a:.0f}→{bpm_b:.0f}")

        # Key clash warning
        key_a = str(current.get("camelot_key", ""))
        key_b = str(track.get("camelot_key", ""))
        if key_a and key_b:
            try:
                from app.modules.library.analysis import camelot_distance
                if camelot_distance(key_a, key_b) >= 4:
                    warnings.append(f"key_clash: {key_a}→{key_b}")
            except Exception:
                pass

        # Vocal clash warning
        stem_a = current.get("stem_activity", {})
        stem_b = track.get("stem_activity", {})
        if (float(stem_a.get("vocals", 0)) > 0.5 and
                float(stem_b.get("vocals", 0)) > 0.5):
            warnings.append("double_vocal")

        # Clipping risk
        loud = track.get("loudness_profile", {})
        if loud.get("clipping_risk"):
            warnings.append("clipping")

        return warnings

    # ── track registry management ────────────────────────────────────────

    def register_track(self, track_id: str, analysis: dict) -> None:
        """Register or update a track's analysis data."""
        self._tracks[track_id] = analysis

    def register_batch(self, tracks: dict[str, dict]) -> None:
        """Register multiple tracks at once."""
        self._tracks.update(tracks)

    def remove_track(self, track_id: str) -> None:
        """Remove a track from the registry."""
        self._tracks.pop(track_id, None)

    @property
    def track_count(self) -> int:
        return len(self._tracks)

    @property
    def weights(self) -> dict:
        return dict(self._weights)
