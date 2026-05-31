"""解析 MixPlan（P2 + Jetson DjMixPlanResult）为统一结构。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Transition:
    from_song_id: int | str
    to_song_id: int | str
    from_at_sec: float
    to_at_sec: float
    fade_sec: float
    fade_curve: str = "equal_power"
    style: str = "smooth"
    # Phase 2: optional beatmatch hints. tempo_ratio = tempo_A / tempo_B,
    # i.e. multiply B's playback rate by ratio so its beat clock matches A's.
    # If both intervals are provided, ratio is computed from them.
    tempo_ratio: float | None = None
    from_beat_interval_sec: float | None = None
    to_beat_interval_sec: float | None = None
    phase_anchor_sec: float | None = None
    # Phase 3.1+: per-stem mix-curve names. dict shape:
    #   {"prev": {"vocals": "linear_out", ...},
    #    "next": {"vocals": "in_late",    ...}}
    # When set AND both decks have all 4 stems loaded, audio-engine evaluates
    # each curve per callback to drive a per-stem mix instead of the legacy
    # single-buffer fade. None = legacy path.
    stem_curves: dict | None = None
    # Phase 3.3: where in the fade vocal of next track is loud-handed-off.
    # Used by `vocal_handoff` style; None lets the engine pick a beat-aligned
    # value via _transition_handoff_ratio.
    vocal_handoff_ratio: float | None = None


@dataclass
class NormalizedPlan:
    plan_id: str | None
    tracks: list[int | str]
    transitions: list[Transition]


def _song_id(item: dict) -> int | str | None:
    for key in ("song_id", "library_song_id", "id"):
        if key in item and item[key] is not None:
            return item[key]
    return None


def normalize_mix_plan(raw: dict) -> NormalizedPlan:
    tracks: list[int | str] = []

    if "tracks" in raw:
        ordered = sorted(raw["tracks"], key=lambda t: t.get("order", 0))
        for t in ordered:
            sid = _song_id(t)
            if sid is not None:
                tracks.append(sid)
    elif "playlist" in raw:
        for item in raw["playlist"]:
            sid = _song_id(item)
            if sid is not None:
                tracks.append(sid)

    transitions: list[Transition] = []

    for tr in raw.get("transitions") or []:
        transitions.append(
            Transition(
                from_song_id=tr["from_song"],
                to_song_id=tr["to_song"],
                from_at_sec=float(tr.get("from_at_sec", 0)),
                to_at_sec=float(tr.get("to_at_sec", 0)),
                fade_sec=float(tr.get("fade_sec", 8)),
                fade_curve=str(tr.get("fade_curve", "equal_power")),
            )
        )

    for tr in raw.get("transition_plan") or []:
        transitions.append(
            Transition(
                from_song_id=tr["from_song_id"],
                to_song_id=tr["to_song_id"],
                from_at_sec=float(tr.get("from_out_sec", tr.get("from_at_sec", 0))),
                to_at_sec=float(tr.get("to_in_sec", tr.get("to_at_sec", 0))),
                fade_sec=float(tr.get("crossfade_sec", tr.get("fade_sec", 8))),
                fade_curve=str(tr.get("fade_curve", "equal_power")),
            )
        )

    return NormalizedPlan(
        plan_id=raw.get("plan_id"),
        tracks=tracks,
        transitions=transitions,
    )
