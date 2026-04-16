from __future__ import annotations

"""Energy-curve-driven DJ planning with fallback transitions.

Design:
1) Use oversampled candidate pool (caller provides enough rows).
2) Prioritize Energy Curve matching for each slot.
3) Never dead-end on strict BPM/Key rules; allow fallback quick-cut transitions.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SCENE_TYPES = {"battle", "cypher", "party", "exercise"}


@dataclass
class SessionContext:
    scene_type: str
    style_ratios: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        scene = str(self.scene_type).strip().lower()
        if scene not in SCENE_TYPES:
            raise ValueError(f"scene_type must be one of {sorted(SCENE_TYPES)}")
        self.scene_type = scene

        cleaned: Dict[str, float] = {}
        for key, value in (self.style_ratios or {}).items():
            name = str(key).strip().lower()
            if not name:
                continue
            try:
                ratio = float(value)
            except (TypeError, ValueError):
                continue
            if ratio > 0:
                cleaned[name] = ratio
        total = sum(cleaned.values())
        self.style_ratios = {k: (v / total if total > 0 else 0.0) for k, v in cleaned.items()}


@dataclass
class TrackCandidate:
    track_id: str
    bpm: float
    key: str
    energy: float
    dominant_styles: List[str]
    semantic_distance: float

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "TrackCandidate":
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else row

        track_id = row.get("spotify_id") or row.get("track_id") or md.get("spotify_id") or md.get("track_id") or row.get("id") or md.get("id") or ""
        bpm_raw = row.get("bpm", md.get("bpm", md.get("BPM", 0.0)))
        energy_raw = row.get("energy", md.get("energy", 5.0))
        key_raw = row.get("key", md.get("key", ""))
        styles_raw = row.get("dominant_styles", md.get("dominant_styles", []))
        dist_raw = row.get("distance", row.get("semantic_distance", md.get("semantic_distance", 1.0)))

        try:
            bpm = float(bpm_raw)
        except (TypeError, ValueError):
            bpm = 0.0
        try:
            energy = float(energy_raw)
        except (TypeError, ValueError):
            energy = 5.0
        try:
            semantic_distance = float(dist_raw)
        except (TypeError, ValueError):
            semantic_distance = 1.0

        if isinstance(styles_raw, list):
            styles = [str(s).strip().lower() for s in styles_raw if str(s).strip()]
        elif styles_raw:
            styles = [str(styles_raw).strip().lower()]
        else:
            styles = []

        return cls(
            track_id=str(track_id),
            bpm=max(0.0, bpm),
            key=str(key_raw or "").strip().upper(),
            energy=max(1.0, min(10.0, energy)),
            dominant_styles=styles,
            semantic_distance=semantic_distance,
        )


@dataclass
class Transition:
    from_track: str
    to_track: str
    strategy: str
    score: float
    fallback_reason: Optional[str] = None


@dataclass
class _BeamState:
    selected_indices: List[int]
    transitions: List[Transition]
    total_score: float
    explain_steps: List[dict]


class DJContextPlanner:
    # Energy-first weights
    W1 = 0.62
    W2 = 0.23
    W3 = 0.15

    BEAM_WIDTH = 10
    BPM_SMOOTH_THRESHOLD = 0.06

    def generate_plan(
        self,
        candidates: List[dict],
        context: SessionContext,
        target_length: int,
        target_energy_curve: Optional[List[float]] = None,
        explain: bool = False,
    ) -> Dict[str, Any]:
        if target_length <= 0:
            raise ValueError("target_length must be > 0")

        tracks = [TrackCandidate.from_row(row) for row in candidates]
        tracks = [t for t in tracks if t.track_id]
        if not tracks:
            return {
                "session_context": {"scene": context.scene_type, "dominant_styles": self._dominant_styles(context)},
                "ordered_tracks": [],
                "transitions": [],
            }

        target = min(target_length, len(tracks))
        curve = self._build_energy_curve(target, context.scene_type, target_energy_curve)

        beam: List[_BeamState] = [
            _BeamState(selected_indices=[], transitions=[], total_score=0.0, explain_steps=[])
        ]

        for step in range(target):
            step_target_energy = curve[step]
            next_beam: List[_BeamState] = []

            for state in beam:
                used = set(state.selected_indices)
                prev_track = tracks[state.selected_indices[-1]] if state.selected_indices else None

                for idx, track in enumerate(tracks):
                    if idx in used:
                        continue

                    score, strategy, fallback_reason, detail = self._score_candidate(
                        track=track,
                        prev_track=prev_track,
                        target_energy=step_target_energy,
                        context=context,
                    )

                    new_transitions = list(state.transitions)
                    if prev_track is not None:
                        new_transitions.append(
                            Transition(
                                from_track=prev_track.track_id,
                                to_track=track.track_id,
                                strategy=strategy,
                                score=round(max(0.0, min(1.0, score)), 4),
                                fallback_reason=fallback_reason,
                            )
                        )

                    next_beam.append(
                        _BeamState(
                            selected_indices=state.selected_indices + [idx],
                            transitions=new_transitions,
                            total_score=state.total_score + score,
                            explain_steps=state.explain_steps + [detail],
                        )
                    )

            if not next_beam:
                break

            next_beam.sort(key=lambda s: s.total_score, reverse=True)
            beam = next_beam[: self.BEAM_WIDTH]

        best = max(beam, key=lambda s: (len(s.selected_indices), s.total_score))
        ordered_tracks = [tracks[i].track_id for i in best.selected_indices]

        transitions_json = []
        for i, transition in enumerate(best.transitions):
            item = {
                "from_track": transition.from_track,
                "to_track": transition.to_track,
                "score": transition.score,
                "strategy": transition.strategy,
                "sync_target_bpm": round(self._sync_target_bpm_by_ids(transition.from_track, transition.to_track, tracks), 2),
            }
            if transition.fallback_reason:
                item["fallback_reason"] = transition.fallback_reason
            if explain and i + 1 < len(best.explain_steps):
                item["explain"] = best.explain_steps[i + 1]
            transitions_json.append(item)

        output: Dict[str, Any] = {
            "session_context": {"scene": context.scene_type, "dominant_styles": self._dominant_styles(context)},
            "ordered_tracks": ordered_tracks,
            "transitions": transitions_json,
        }
        if explain:
            output["planner_debug"] = {
                "beam_width": self.BEAM_WIDTH,
                "target_length": target,
                "candidate_pool": len(tracks),
                "target_energy_curve": curve,
            }
        return output

    def _score_candidate(
        self,
        track: TrackCandidate,
        prev_track: Optional[TrackCandidate],
        target_energy: float,
        context: SessionContext,
    ) -> Tuple[float, str, Optional[str], dict]:
        # W1: energy match
        energy_match = max(0.0, min(1.0, 1.0 - abs(track.energy - target_energy) / 10.0))

        # W2: semantic/style
        semantic_bonus = 1.0 / (1.0 + max(0.0, track.semantic_distance))
        style_bonus = max((context.style_ratios.get(s, 0.0) for s in track.dominant_styles), default=0.0)
        semantic_style = 0.6 * semantic_bonus + 0.4 * style_bonus

        # W3: transition smoothness (fallback allowed)
        transition_score = 0.7
        strategy = "Smooth Blend"
        fallback_reason: Optional[str] = None

        if prev_track is not None:
            bpm_rel = self._bpm_rel_diff(prev_track.bpm, track.bpm)
            key_score = self._camelot_score(prev_track.key, track.key)
            smooth = max(0.0, 1.0 - min(1.0, bpm_rel / 0.12))
            transition_score = 0.65 * smooth + 0.35 * key_score

            if bpm_rel > self.BPM_SMOOTH_THRESHOLD or key_score < 0.35:
                strategy = "Power Drop / Quick Cut"
                fallback_reason = (
                    f"Fallback: ΔBPM={round(bpm_rel * 100, 2)}%, key_score={round(key_score, 3)}; "
                    "energy target prioritized."
                )
                transition_score = max(0.25, transition_score - 0.18)

        total = (self.W1 * energy_match) + (self.W2 * semantic_style) + (self.W3 * transition_score)

        detail = {
            "target_energy": round(target_energy, 3),
            "selected_energy": round(track.energy, 3),
            "energy_match": round(energy_match, 4),
            "semantic_style": round(semantic_style, 4),
            "transition_score": round(transition_score, 4),
            "strategy": strategy,
            "strategy_reason": fallback_reason or "Smooth transition conditions satisfied.",
            "weights": {"W1": self.W1, "W2": self.W2, "W3": self.W3},
            "raw_total": round(total, 6),
        }
        return total, strategy, fallback_reason, detail

    def _build_energy_curve(self, target_length: int, scene: str, custom_curve: Optional[List[float]]) -> List[float]:
        if custom_curve:
            curve = [max(1.0, min(10.0, float(v))) for v in custom_curve]
            if len(curve) >= target_length:
                return curve[:target_length]
            if curve:
                curve.extend([curve[-1]] * (target_length - len(curve)))
                return curve

        presets = {
            "battle": [8.2, 8.6, 9.0, 8.8, 9.1, 8.9],
            "exercise": [7.0, 7.2, 7.4, 7.3, 7.5, 7.4],
            "party": [6.8, 7.6, 8.4, 7.3, 8.5, 7.8],
            "cypher": [7.2, 7.6, 8.0, 7.4, 7.9, 7.5],
        }
        base = presets.get(scene, presets["cypher"])
        if target_length <= len(base):
            return base[:target_length]
        out = base[:]
        while len(out) < target_length:
            out.append(base[len(out) % len(base)])
        return out[:target_length]

    def _bpm_rel_diff(self, bpm_a: float, bpm_b: float) -> float:
        if bpm_a <= 0 or bpm_b <= 0:
            return 1.0
        return abs(bpm_a - bpm_b) / max(bpm_a, 1e-9)

    def _camelot_score(self, key_a: str, key_b: str) -> float:
        pa = self._parse_camelot(key_a)
        pb = self._parse_camelot(key_b)
        if pa is None or pb is None:
            return 0.4
        na, ma = pa
        nb, mb = pb
        if na == nb and ma == mb:
            return 1.0
        if na == nb and ma != mb:
            return 0.6
        left = 12 if na == 1 else na - 1
        right = 1 if na == 12 else na + 1
        if ma == mb and nb in {left, right}:
            return 0.8
        return 0.2

    def _parse_camelot(self, value: str) -> Optional[Tuple[int, str]]:
        key = str(value or "").strip().upper()
        if len(key) < 2:
            return None
        mode = key[-1]
        if mode not in {"A", "B"}:
            return None
        try:
            num = int(key[:-1])
        except ValueError:
            return None
        if not (1 <= num <= 12):
            return None
        return num, mode

    def _dominant_styles(self, context: SessionContext) -> List[str]:
        ranked = sorted(context.style_ratios.items(), key=lambda x: x[1], reverse=True)
        return [name for name, _ in ranked]

    def _sync_target_bpm_by_ids(self, from_track_id: str, to_track_id: str, tracks: List[TrackCandidate]) -> float:
        by_id = {t.track_id: t for t in tracks}
        a = by_id.get(from_track_id)
        b = by_id.get(to_track_id)
        if not a and not b:
            return 120.0
        if not a:
            return float(b.bpm)
        if not b:
            return float(a.bpm)
        if a.bpm <= 0 and b.bpm <= 0:
            return 120.0
        if a.bpm <= 0:
            return float(b.bpm)
        if b.bpm <= 0:
            return float(a.bpm)
        return float((a.bpm + b.bpm) / 2.0)
