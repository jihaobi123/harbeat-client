"""Section-aware energy.

Splits a track into sections (using phrase_map/cue_points/downbeat windows)
and computes per-section energy/groove/impact/vocal/density/tension scores.

DJ排歌的关键观察：
  一首歌不是一个能量值，而是一条曲线。
  prev 出歌点用 prev outro 的 section 能量，
  next 入歌点用 next intro 的 section 能量。
  两段窗口能量差才是 transition 真实落差。

实现策略（不读音频，只用元数据 + 拍点）：
  1. 从 phrase_map / cue_points 拿到边界，没有就按 16-bar 切
  2. 每个 section 内的 beat 密度 + downbeat 间隔规律性 → groove
  3. 4×60/bpm 的 bar 内拍点位置 → kick/snare proxy
  4. phrase 标签里有"verse/chorus/hook/rap" → vocal_density
  5. 无标签时用拍密度兜底

与 energy_hiphop.compute_dance_energy 不同：那是整首一个值，
这里是每段一个 SectionEnergy。两者**互补**，不替代。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_VOCAL_LABELS = {"verse", "chorus", "hook", "rap", "bridge"}
_INSTRUMENTAL_LABELS = {"intro", "outro", "break", "drop", "build", "instrumental"}


@dataclass(frozen=True)
class SectionEnergy:
    """One section of a track, with per-section energy fields.

    Time fields in seconds. Energy fields all in [0, 1]."""

    start: float
    end: float
    label: str  # phrase/cue label or "auto" if synthesized

    section_dance_energy: float
    section_groove_energy: float
    section_impact_energy: float
    section_vocal_density: float
    section_kick_punch: float
    section_snare_crack: float
    section_low_mid_density: float
    section_density_energy: float
    section_tension_energy: float

    def as_dict(self) -> dict:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "label": self.label,
            "dance": round(self.section_dance_energy, 3),
            "groove": round(self.section_groove_energy, 3),
            "impact": round(self.section_impact_energy, 3),
            "vocal_density": round(self.section_vocal_density, 3),
            "kick_punch": round(self.section_kick_punch, 3),
            "snare_crack": round(self.section_snare_crack, 3),
            "low_mid_density": round(self.section_low_mid_density, 3),
            "density": round(self.section_density_energy, 3),
            "tension": round(self.section_tension_energy, 3),
        }


def _bar_seconds(bpm: float) -> float:
    return 4 * 60.0 / bpm if bpm > 0 else 2.0


def _build_section_boundaries(
    phrase_map: list[dict],
    cue_points: list[dict],
    duration: float,
    bpm: float,
) -> list[tuple[float, float, str]]:
    """Return list of (start, end, label) covering [0, duration]."""
    bounds: list[tuple[float, str]] = []  # (start, label)
    for ph in phrase_map or []:
        try:
            t = float(ph.get("start") or ph.get("time") or 0.0)
            label = str(ph.get("label") or "").lower() or "section"
            bounds.append((t, label))
        except (TypeError, ValueError):
            continue
    if not bounds:
        for cue in cue_points or []:
            try:
                t = float(cue.get("time") or 0.0)
                label = str(cue.get("label") or "").lower() or "section"
                bounds.append((t, label))
            except (TypeError, ValueError):
                continue
    if not bounds:
        # Synthesize 16-bar windows
        bar = _bar_seconds(bpm)
        win = bar * 16
        t = 0.0
        while t < duration:
            bounds.append((t, "auto"))
            t += win
    bounds.sort(key=lambda kv: kv[0])
    if not bounds or bounds[0][0] > 0.5:
        bounds.insert(0, (0.0, "intro"))
    # Build (start, end, label)
    sections: list[tuple[float, float, str]] = []
    for i, (start, label) in enumerate(bounds):
        end = bounds[i + 1][0] if i + 1 < len(bounds) else duration
        if end - start < 1.5:
            continue
        sections.append((float(start), float(end), label))
    if not sections:
        sections = [(0.0, duration, "auto")]
    return sections


def _beats_in(beat_points: list[float], start: float, end: float) -> list[float]:
    return [float(b) for b in (beat_points or []) if start - 0.05 <= float(b) < end + 0.05]


def _kick_punch_section(downbeats: list[float], start: float, end: float, bpm: float,
                        global_energy: float) -> float:
    """How regular are downbeats in this section? Stable downbeats -> punchy kick."""
    db_in = [float(d) for d in (downbeats or []) if start <= float(d) < end]
    if len(db_in) < 3 or bpm <= 0:
        return float(min(1.0, global_energy * 0.6))
    intervals = [db_in[i + 1] - db_in[i] for i in range(len(db_in) - 1)]
    expected = _bar_seconds(bpm)
    if expected <= 0:
        return global_energy * 0.5
    deviation = sum(abs(iv - expected) for iv in intervals) / len(intervals) / expected
    regularity = max(0.0, 1.0 - deviation * 4.0)
    return float(min(1.0, regularity * (0.5 + 0.5 * global_energy)))


def _snare_crack_section(beat_points: list[float], downbeats: list[float],
                         start: float, end: float, bpm: float) -> float:
    """Beats landing ~half-bar after a downbeat → backbeat snare proxy."""
    if bpm <= 0:
        return 0.4
    half_bar = 2 * 60.0 / bpm
    db_in = [float(d) for d in (downbeats or []) if start <= float(d) < end]
    bp_in = _beats_in(beat_points, start, end)
    if not db_in or not bp_in:
        return 0.4
    hits = 0
    for db in db_in:
        target = db + half_bar
        for bp in bp_in:
            if abs(bp - target) <= 0.12:
                hits += 1
                break
    return float(min(1.0, hits / max(1, len(db_in))))


def _groove_tightness_section(beat_points: list[float], start: float, end: float,
                              bpm: float) -> float:
    """1 - CV of inter-beat intervals."""
    bp = _beats_in(beat_points, start, end)
    if len(bp) < 6 or bpm <= 0:
        return 0.5
    intervals = [bp[i + 1] - bp[i] for i in range(len(bp) - 1)]
    expected = 60.0 / bpm
    if expected <= 0:
        return 0.5
    cv = sum(abs(iv - expected) for iv in intervals) / len(intervals) / expected
    return float(max(0.0, min(1.0, 1.0 - cv * 5.0)))


def _low_mid_section(beat_points: list[float], start: float, end: float,
                     global_energy: float) -> float:
    bp = _beats_in(beat_points, start, end)
    span = max(0.5, end - start)
    bd = len(bp) / span
    norm = min(1.0, bd / 2.5)
    return float(min(1.0, norm * (0.4 + 0.6 * global_energy)))


def _vocal_density_section(label: str, phrase_map: list[dict], start: float,
                           end: float) -> float:
    """Use label first; if generic, count overlapping phrases."""
    lab = label.lower()
    if lab in _VOCAL_LABELS:
        # Hook/chorus tend to be the most vocal-loaded
        if lab in {"chorus", "hook"}:
            return 0.85
        if lab == "rap":
            return 0.95
        return 0.7
    if lab in _INSTRUMENTAL_LABELS:
        return 0.15
    overlap = 0
    for ph in phrase_map or []:
        try:
            t = float(ph.get("start") or ph.get("time") or 0.0)
            phl = str(ph.get("label") or "").lower()
            if start - 1 <= t < end + 1 and phl in _VOCAL_LABELS:
                overlap += 1
        except (TypeError, ValueError):
            continue
    return float(min(1.0, 0.3 + overlap * 0.25))


def _density_section(beat_points: list[float], start: float, end: float) -> float:
    bp = _beats_in(beat_points, start, end)
    span = max(0.5, end - start)
    return float(min(1.0, (len(bp) / span) / 4.0))


def _tension_section(label: str, phrase_map: list[dict], start: float,
                     end: float, bpm: float) -> float:
    """Tension = phrase change rate near this section + label weight."""
    lab = label.lower()
    base = 0.4
    if lab in {"build", "drop", "bridge"}:
        base = 0.85
    elif lab == "outro":
        base = 0.2
    elif lab == "intro":
        base = 0.35
    nearby = 0
    for ph in phrase_map or []:
        try:
            t = float(ph.get("start") or ph.get("time") or 0.0)
            if start - 8 <= t < end + 8:
                nearby += 1
        except (TypeError, ValueError):
            continue
    return float(min(1.0, base * 0.7 + min(0.3, nearby * 0.05)))


def compute_section_energy_map(song) -> list[SectionEnergy]:
    """Build the per-section energy list for one LibrarySong."""
    duration = float(getattr(song, "duration", 0) or 0)
    bpm = float(getattr(song, "bpm", 0) or 0)
    global_energy = float(getattr(song, "energy", 0.5) or 0.5)
    phrase_map = list(getattr(song, "phrase_map", []) or [])
    cue_points = list(getattr(song, "cue_points", []) or [])
    downbeats = list(getattr(song, "downbeats", []) or [])
    beat_points = list(getattr(song, "beat_points", []) or [])

    if duration <= 0:
        return []

    sections = _build_section_boundaries(phrase_map, cue_points, duration, bpm)
    out: list[SectionEnergy] = []
    for start, end, label in sections:
        kp = _kick_punch_section(downbeats, start, end, bpm, global_energy)
        sc = _snare_crack_section(beat_points, downbeats, start, end, bpm)
        gt = _groove_tightness_section(beat_points, start, end, bpm)
        lm = _low_mid_section(beat_points, start, end, global_energy)
        vd = _vocal_density_section(label, phrase_map, start, end)
        dn = _density_section(beat_points, start, end)
        tn = _tension_section(label, phrase_map, start, end, bpm)

        # Composite scores (mirror compute_dance_energy weighting):
        impact = 0.55 * kp + 0.45 * sc
        groove = 0.55 * gt + 0.45 * lm
        section_dance = 0.30 * kp + 0.25 * sc + 0.15 * gt + 0.15 * lm + 0.10 * vd + 0.05 * min(1.0, bpm / 130.0 if bpm > 0 else 0.5)

        out.append(SectionEnergy(
            start=start, end=end, label=label,
            section_dance_energy=float(min(1.0, section_dance)),
            section_groove_energy=float(min(1.0, groove)),
            section_impact_energy=float(min(1.0, impact)),
            section_vocal_density=vd,
            section_kick_punch=kp,
            section_snare_crack=sc,
            section_low_mid_density=lm,
            section_density_energy=dn,
            section_tension_energy=tn,
        ))
    return out
