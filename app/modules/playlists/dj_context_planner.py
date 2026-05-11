"""Two-tier DJ planner: macro energy/style + micro GrooveEngine transition scoring.

Fuses FinalReco's DJContextPlanner (energy-curve-driven stage allocation)
with GrooveEngine's TransitionPlanner (11-factor bar-level scoring).

Outer loop (macro): Stage-based energy curve matching + style ratio quotas.
Inner loop (micro): GrooveEngine 11-factor transition scoring per pair.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

SCENE_TYPES = {"battle", "cypher", "party", "exercise"}

# Default energy curves per scene type
_SCENE_CURVES: Dict[str, List[float]] = {
    "battle": [8.2, 8.6, 9.0, 8.8, 9.1, 8.9],
    "exercise": [7.0, 7.2, 7.4, 7.3, 7.5, 7.4],
    "party": [6.8, 7.6, 8.4, 7.3, 8.5, 7.8],
    "cypher": [7.2, 7.6, 8.0, 7.4, 7.9, 7.5],
}


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
    song_id: int = 0

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "TrackCandidate":
        md = row.get("metadata") if isinstance(row.get("metadata"), dict) else row
        track_id = str(
            row.get("spotify_id") or row.get("track_id")
            or md.get("spotify_id") or md.get("track_id")
            or row.get("id") or md.get("id") or ""
        )
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
            track_id=track_id,
            bpm=max(0.0, bpm),
            key=str(key_raw or "").strip().upper(),
            energy=max(1.0, min(10.0, energy)),
            dominant_styles=styles,
            semantic_distance=semantic_distance,
        )


@dataclass
class _Transition:
    from_track: str
    to_track: str
    strategy: str
    score: float
    fallback_reason: Optional[str] = None
    groove_score: float = 0.0  # from GrooveEngine if available


@dataclass
class _BeamState:
    selected_indices: List[int]
    transitions: List[_Transition]
    total_score: float
    explain_steps: List[dict]


class DJContextPlanner:
    """Two-tier DJ planner: macro energy/style + micro GrooveEngine transition scoring.

    Outer loop (macro): Energy curve matching + style quota.
    Inner loop (micro): GrooveEngine 11-factor scoring when metadata is available.
    """

    W_ENERGY = 0.62
    W_STYLE = 0.23
    W_TRANSITION = 0.15

    BEAM_WIDTH = 10
    BPM_SMOOTH_THRESHOLD = 0.06

    def __init__(self, transition_planner=None):
        """Optionally inject a GrooveEngine TransitionPlanner for micro-scoring."""
        self.transition_planner = transition_planner  # None = use heuristics only

    def generate_plan(
        self,
        candidates: list[dict],
        context: SessionContext,
        target_length: int,
        target_energy_curve: Optional[List[float]] = None,
        stage_candidates: Optional[List[dict]] = None,
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
                "stage_report": [],
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

                    score, strategy, fallback, detail, groove_score = self._score_candidate(
                        track=track,
                        prev_track=prev_track,
                        target_energy=step_target_energy,
                        context=context,
                    )

                    new_transitions = list(state.transitions)
                    if prev_track is not None:
                        new_transitions.append(
                            _Transition(
                                from_track=prev_track.track_id,
                                to_track=track.track_id,
                                strategy=strategy,
                                score=round(max(0.0, min(1.0, score)), 4),
                                fallback_reason=fallback,
                                groove_score=round(groove_score, 4),
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
        ordered_tracks = [tracks[i] for i in best.selected_indices]

        transitions_json: List[dict] = []
        for i, tr in enumerate(best.transitions):
            entry = {
                "from_track": tr.from_track,
                "to_track": tr.to_track,
                "score": tr.score,
                "strategy": tr.strategy,
                "groove_score": tr.groove_score,
                "sync_target_bpm": round(
                    self._sync_target_bpm_by_ids(tr.from_track, tr.to_track, tracks), 2
                ),
            }
            if tr.fallback_reason:
                entry["fallback_reason"] = tr.fallback_reason
            if explain and i + 1 < len(best.explain_steps):
                entry["explain"] = best.explain_steps[i + 1]
            transitions_json.append(entry)

        stage_report = self._build_stage_report(ordered_tracks, stage_candidates)

        output: Dict[str, Any] = {
            "session_context": {
                "scene": context.scene_type,
                "dominant_styles": self._dominant_styles(context),
            },
            "ordered_tracks": [t.track_id for t in ordered_tracks],
            "transitions": transitions_json,
            "stage_report": stage_report,
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
    ) -> Tuple[float, str, Optional[str], dict, float]:
        energy_match = max(0.0, min(1.0, 1.0 - abs(track.energy - target_energy) / 10.0))
        semantic_bonus = 1.0 / (1.0 + max(0.0, track.semantic_distance))
        style_bonus = max(
            (context.style_ratios.get(s, 0.0) for s in track.dominant_styles), default=0.0
        )
        semantic_style = 0.6 * semantic_bonus + 0.4 * style_bonus

        transition_score = 0.7
        groove_score = 0.0
        strategy = "Smooth Blend"
        fallback_reason: Optional[str] = None

        if prev_track is not None:
            bpm_rel = self._bpm_rel_diff(prev_track.bpm, track.bpm)
            key_score = self._camelot_score(prev_track.key, track.key)
            smooth = max(0.0, 1.0 - min(1.0, bpm_rel / 0.12))
            transition_score = 0.65 * smooth + 0.35 * key_score

            # Try GrooveEngine micro-scoring if available
            if self.transition_planner is not None:
                try:
                    groove_score = self._groove_micro_score(
                        prev_track, track, self.transition_planner
                    )
                    transition_score = 0.4 * transition_score + 0.6 * groove_score
                except Exception:
                    groove_score = 0.0

            if bpm_rel > self.BPM_SMOOTH_THRESHOLD or key_score < 0.35:
                strategy = "Power Drop / Quick Cut"
                fallback_reason = (
                    f"Fallback: ΔBPM={round(bpm_rel * 100, 2)}%, "
                    f"key_score={round(key_score, 3)}; energy target prioritized."
                )
                transition_score = max(0.25, transition_score - 0.18)

        total = (
            self.W_ENERGY * energy_match
            + self.W_STYLE * semantic_style
            + self.W_TRANSITION * transition_score
        )

        detail = {
            "target_energy": round(target_energy, 3),
            "selected_energy": round(track.energy, 3),
            "energy_match": round(energy_match, 4),
            "semantic_style": round(semantic_style, 4),
            "transition_score": round(transition_score, 4),
            "groove_score": round(groove_score, 4),
            "strategy": strategy,
            "strategy_reason": fallback_reason or "Smooth transition conditions satisfied.",
            "weights": {"W1": self.W_ENERGY, "W2": self.W_STYLE, "W3": self.W_TRANSITION},
            "raw_total": round(total, 6),
        }
        return total, strategy, fallback_reason, detail, groove_score

    def _groove_micro_score(
        self,
        prev: TrackCandidate,
        nxt: TrackCandidate,
        tp,  # TransitionPlanner instance
    ) -> float:
        """Build minimal TrackMetadata for both candidates and score via GrooveEngine."""
        from core.datatypes import (
            BeatAnalysis,
            BeatGrid,
            BeatPoint,
            EnergyPoint,
            MusicalKey,
            PhraseSegment,
            TrackMetadata,
        )

        def _minimal_meta(c: TrackCandidate, name: str) -> TrackMetadata:
            duration = 180.0  # default 3 min
            bpm = c.bpm if c.bpm > 0 else 120.0
            bar_count = max(8, int(duration * bpm / 60 / 4))
            beats = [
                BeatPoint(
                    index=i + 1,
                    time=i * 60.0 / bpm,
                    bar=(i // 4) + 1,
                    beat_in_bar=(i % 4) + 1,
                    is_downbeat=(i % 4 == 0),
                )
                for i in range(bar_count * 4)
            ]
            return TrackMetadata(
                track_id=c.track_id,
                title=name,
                path="",
                duration_seconds=duration,
                sample_rate=44100,
                channels=2,
                beatgrid=BeatGrid(bpm=bpm, beats=beats, bars=bar_count, downbeats=[]),
                beat_analysis=BeatAnalysis(),
                phrases=[
                    PhraseSegment(
                        phrase_type=__import__("core.enums", fromlist=["PhraseType"]).PhraseType.UNKNOWN,
                        start_time=0.0,
                        end_time=duration,
                        start_bar=1,
                        end_bar=bar_count,
                    )
                ],
                energy_bars=[EnergyPoint(bar=b, start_time=0, end_time=0, rms=0, spectral_flux=0, combined=c.energy / 10.0) for b in range(1, bar_count + 1)],
                key=MusicalKey(tonic=c.key or "Unknown"),
            )

        meta_a = _minimal_meta(prev, prev.track_id)
        meta_b = _minimal_meta(nxt, nxt.track_id)
        candidates = tp.top_candidates(meta_a, meta_b, limit=1)
        return float(candidates[0].total_score) if candidates else 0.0

    def _build_energy_curve(
        self, target_length: int, scene: str, custom_curve: Optional[List[float]]
    ) -> List[float]:
        if custom_curve:
            curve = [max(1.0, min(10.0, float(v))) for v in custom_curve]
            if len(curve) >= target_length:
                return curve[:target_length]
            if curve:
                curve.extend([curve[-1]] * (target_length - len(curve)))
                return curve
        base = _SCENE_CURVES.get(scene, _SCENE_CURVES["cypher"])
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

    def _sync_target_bpm_by_ids(
        self, from_id: str, to_id: str, tracks: List[TrackCandidate]
    ) -> float:
        by_id = {t.track_id: t for t in tracks}
        a = by_id.get(from_id)
        b = by_id.get(to_id)
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

    def _build_stage_report(
        self,
        ordered_tracks: List[TrackCandidate],
        stage_targets: Optional[List[dict]],
    ) -> List[dict]:
        if not stage_targets:
            return []
        report: List[dict] = []
        cursor = 0
        for stage in stage_targets:
            slot_count = int(stage.get("slot_count") or 0)
            if slot_count <= 0:
                continue
            segment = ordered_tracks[cursor:cursor + slot_count]
            cursor += slot_count
            style_actual: Dict[str, int] = {}
            energies: List[float] = []
            for track in segment:
                energies.append(track.energy)
                key = track.dominant_styles[0] if track.dominant_styles else "unknown"
                style_actual[key] = style_actual.get(key, 0) + 1
            report.append({
                "stage_idx": stage.get("stage_idx"),
                "slot_count": slot_count,
                "energy_min": stage.get("energy_min"),
                "energy_max": stage.get("energy_max"),
                "target_curve": stage.get("target_curve") or [],
                "style_target": stage.get("style_target") or {},
                "style_actual": style_actual,
                "actual_avg_energy": round(sum(energies) / len(energies), 3) if energies else None,
            })
        return report
