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
