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
    transition_id: str | None = None
    fade_curve: str = "equal_power"
    # DJ/Spotify Mix 风格 preset。默认 smooth = 原等功率 cos/sin。
    style: str = "smooth"
    fallback_style: str | None = None
    # Sprint 4 beatmatch metadata. Intervals are seconds/beat. tempo_ratio is
    # kept as supplied by Jetson for diagnostics; RK derives the stretch from
    # intervals when available.
    tempo_ratio: float | None = None
    from_beat_interval_sec: float | None = None
    to_beat_interval_sec: float | None = None
    phase_anchor_sec: float | None = None
    vocal_handoff_ratio: float | None = None
    stem_curves: dict | None = None
    eq_curves: dict | None = None


@dataclass
class NormalizedPlan:
    plan_id: str | None
    tracks: list[int | str]
    transitions: list[Transition]
    # 每首歌的元数据（响度归一用）：{str(song_id): {"replay_gain_db": float, "loudness_lufs": float}}
    track_meta: dict[str, dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.track_meta is None:
            self.track_meta = {}


def _song_id(item: dict) -> int | str | None:
    for key in ("song_id", "library_song_id", "id"):
        if key in item and item[key] is not None:
            return item[key]
    return None


def _f(value, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_mix_plan(raw: dict) -> NormalizedPlan:
    tracks: list[int | str] = []
    track_meta: dict[str, dict] = {}

    def _absorb_meta(item: dict, sid: int | str) -> None:
        meta: dict = {}
        tempo = _f(item.get("tempo"), _f(item.get("bpm")))
        if tempo is None:
            mf = item.get("music_features") or {}
            tempo = _f(mf.get("tempo"), _f(mf.get("bpm")))
        if tempo is not None and tempo > 0:
            meta["tempo"] = tempo
        beats = item.get("beats")
        if beats is None:
            beats = item.get("beat_points")
        if isinstance(beats, list):
            meta["beats"] = [float(t) for t in beats if isinstance(t, (int, float))]
        rg = _f(item.get("replay_gain_db"))
        if rg is None:
            mf = item.get("music_features") or {}
            rg = _f(mf.get("replay_gain_db"))
        if rg is not None:
            # 限幅 ±8dB 防止极端 gain 爆音
            meta["replay_gain_db"] = max(-8.0, min(8.0, rg))
        lufs = _f(item.get("loudness_lufs"))
        if lufs is None:
            mf = item.get("music_features") or {}
            lufs = _f(mf.get("loudness_lufs"))
        if lufs is not None:
            meta["loudness_lufs"] = lufs
        if meta:
            track_meta[str(sid)] = meta

    if "tracks" in raw:
        ordered = sorted(raw["tracks"], key=lambda t: t.get("order", 0))
        for t in ordered:
            sid = _song_id(t)
            if sid is not None:
                tracks.append(sid)
                _absorb_meta(t, sid)
    elif "playlist" in raw:
        for item in raw["playlist"]:
            sid = _song_id(item)
            if sid is not None:
                tracks.append(sid)
                _absorb_meta(item, sid)

    transitions: list[Transition] = []

    for tr in raw.get("transitions") or []:
        transitions.append(
            Transition(
                from_song_id=tr["from_song"],
                to_song_id=tr["to_song"],
                from_at_sec=float(tr.get("from_at_sec", 0)),
                to_at_sec=float(tr.get("to_at_sec", 0)),
                fade_sec=float(tr.get("fade_sec", 8)),
                transition_id=tr.get("transition_id"),
                fade_curve=str(tr.get("fade_curve", "equal_power")),
                style=str(tr.get("style", tr.get("transition_type", "smooth"))),
                fallback_style=tr.get("fallback_style"),
                tempo_ratio=_f(tr.get("tempo_ratio")),
                from_beat_interval_sec=_f(tr.get("from_beat_interval_sec")),
                to_beat_interval_sec=_f(tr.get("to_beat_interval_sec")),
                phase_anchor_sec=_f(tr.get("phase_anchor_sec")),
                vocal_handoff_ratio=_f(tr.get("vocal_handoff_ratio"), _f(tr.get("handoff_ratio"), _f(tr.get("vocal_cut_ratio")))),
                stem_curves=tr.get("stem_curves"),
                eq_curves=tr.get("eq_curves"),
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
                transition_id=tr.get("transition_id"),
                fade_curve=str(tr.get("fade_curve", "equal_power")),
                style=str(tr.get("transition_type", tr.get("style", "smooth"))),
                fallback_style=tr.get("fallback_style"),
                tempo_ratio=_f(tr.get("tempo_ratio")),
                from_beat_interval_sec=_f(tr.get("from_beat_interval_sec")),
                to_beat_interval_sec=_f(tr.get("to_beat_interval_sec")),
                phase_anchor_sec=_f(tr.get("phase_anchor_sec")),
                vocal_handoff_ratio=_f(tr.get("vocal_handoff_ratio"), _f(tr.get("handoff_ratio"), _f(tr.get("vocal_cut_ratio")))),
                stem_curves=tr.get("stem_curves"),
                eq_curves=tr.get("eq_curves"),
            )
        )

    return NormalizedPlan(
        plan_id=raw.get("plan_id"),
        tracks=tracks,
        transitions=transitions,
        track_meta=track_meta,
    )
