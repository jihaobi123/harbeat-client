"""Transition Plan — thin wrapper over mixer_rules.build_transition_spec.

The dj_set pipeline picks the rule (using role + section + edge analysis),
but the *spec* a transition produces — `from_at_sec`, `to_at_sec`,
`duration_sec`, `eq_curve`, `stem_curves`, `beat_reinforce`, `target_bpm`,
`tempo_ratio`, `align_strategy` — is whatever mixer_rules.build_transition_spec
returns. That keeps the audio path single-source-of-truth at the spec layer
and lets the dj_set side own the *what to play next* decision.

Why no actions list anymore:
  RK audio-engine consumes the spec format above directly. The earlier
  abstract `actions: [bass_drop_b, fader_xfade, ...]` had no consumer —
  mobile would still translate it back to mixer_rules style, doubling the
  surface area and risking drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid5, NAMESPACE_URL

from app.modules.dj_control import mixer_rules
from app.modules.dj_set.edge_analyzer import TransitionEdge
from app.modules.dj_set.purpose_planner import TransitionPurpose


@dataclass(frozen=True)
class TransitionPlan:
    from_track_id: str
    to_track_id: str
    rule: str           # one of mixer_rules.py's 18 rule_keys
    purpose: str
    spec: dict          # exact dict mixer_rules.build_transition_spec returns
    transition_id: str
    fallback_spec: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        selected = {
            "transition_id": self.transition_id,
            "from_track_id": self.from_track_id,
            "to_track_id": self.to_track_id,
            "from_at_sec": self.spec.get("from_at_sec"),
            "to_at_sec": self.spec.get("to_at_sec"),
            "fade_sec": self.spec.get("duration_sec"),
            "style": self.spec.get("rule_key", self.rule),
            "fallback_style": self.fallback_spec.get("rule_key"),
            "tempo_ratio": self.spec.get("tempo_ratio"),
            "phase_anchor_sec": self.spec.get("phase_anchor_sec"),
            "automation": {
                "stem_curves": self.spec.get("stem_curves") or {},
                "eq_curves": self.spec.get("eq_curves") or self.spec.get("eq_curve") or {},
                "fx": self.spec.get("fx") or [],
            },
        }
        return {
            "from": self.from_track_id,
            "to": self.to_track_id,
            "rule": self.rule,
            "purpose": self.purpose,
            "transition_id": self.transition_id,
            "spec": dict(self.spec),
            "selected": selected,
            "fallback": dict(self.fallback_spec),
        }


def build_transition_plan(edge: TransitionEdge,
                          purpose: TransitionPurpose,
                          a_song,
                          b_song) -> TransitionPlan:
    """Build a plan for one transition by delegating spec generation to
    mixer_rules.build_transition_spec.

    Parameters
    ----------
    a_song, b_song
        LibrarySong-shaped objects (need bpm, beat_points, downbeats,
        phrase_map, cue_points, energy, stems). Plain SimpleNamespace works
        in tests.
    """
    rule_key = purpose.rule_recommendation or edge.best_rule
    cursor_sec = float(edge.exit_time)
    transition_id = str(uuid5(
        NAMESPACE_URL,
        f"harbeat-transition:{edge.from_track_id}:{edge.to_track_id}:"
        f"{edge.exit_time:.3f}:{edge.entry_time:.3f}:{edge.fade_sec:.3f}:{rule_key}",
    ))
    spec = mixer_rules.build_transition_spec(
        a_song,
        b_song,
        cursor_sec,
        rule_key=rule_key,
        forced_from_at_sec=edge.exit_time,
        forced_to_at_sec=edge.entry_time,
        forced_fade_sec=edge.fade_sec,
    )
    spec["transition_id"] = transition_id
    spec["phase_anchor_sec"] = spec.get("phase_anchor_sec", spec.get("from_at_sec"))
    fallback_spec = mixer_rules.build_transition_spec(
        a_song,
        b_song,
        cursor_sec,
        rule_key="raw_xfade_6s",
        forced_from_at_sec=edge.exit_time,
        forced_to_at_sec=edge.entry_time,
        forced_fade_sec=max(6.0, min(10.0, float(edge.fade_sec or 6.0))),
        enable_cross_style=False,
    )
    fallback_spec["transition_id"] = f"{transition_id}:fallback"
    # If mixer_rules silently fell back to a different rule (e.g. RAW because
    # one side lacks beats), keep the actual rule it picked.
    actual_rule = str(spec.get("rule_key", rule_key))
    spec["fallback_style"] = fallback_spec.get("rule_key")
    return TransitionPlan(
        from_track_id=edge.from_track_id,
        to_track_id=edge.to_track_id,
        rule=actual_rule,
        purpose=purpose.purpose,
        spec=spec,
        transition_id=transition_id,
        fallback_spec=fallback_spec,
    )


def build_all_plans(dj_set_transitions: list[TransitionEdge],
                    purposes: list[TransitionPurpose],
                    songs_by_id: dict[str, Any]) -> list[TransitionPlan]:
    if len(dj_set_transitions) != len(purposes):
        raise ValueError("transitions vs purposes length mismatch")
    out: list[TransitionPlan] = []
    for edge, purp in zip(dj_set_transitions, purposes):
        a = songs_by_id.get(edge.from_track_id)
        b = songs_by_id.get(edge.to_track_id)
        if a is None or b is None:
            continue
        out.append(build_transition_plan(edge, purp, a, b))
    return out
