"""Track Profiler — single-source-of-truth profile for every track.

Profile is computed on-demand from LibrarySong + cached on the in-memory
TrackProfile dataclass. Reuses existing fields where available and uses
zero-cost proxies for fields that aren't measured yet (stem RMS, etc).

A profile is **read-only** and **deterministic** — the same LibrarySong
always produces the same profile. This lets the optimizer reason about
edges without re-querying the DB.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.modules.dj_control.energy_hiphop import (
    EnergyBreakdown,
    compute_dance_energy,
)
from app.modules.dj_set.section_energy import (
    SectionEnergy,
    compute_section_energy_map,
)
from app.modules.dj_set.track_analysis_adapter import build_track_analysis_v2


@dataclass(frozen=True)
class TrackProfile:
    """Read-only feature profile for a single LibrarySong.

    Fields fall into three buckets:
      - **identity**: id / title / duration / bpm / key / camelot
      - **energy**: global, dance breakdown, section-aware windows
      - **structure**: cue points, phrase map, safe entry/exit
      - **stems**: availability + per-stem quality proxy
    """

    # ----- identity -----
    track_id: str
    title: str
    artist: str | None
    duration: float
    bpm: float
    camelot_key: str | None
    musical_key: str | None
    genre: str | None

    # ----- core energy (whole track) -----
    global_energy: float           # legacy song.energy (RMS-derived)
    dance_energy: float            # EnergyBreakdown.total
    vocal_density: float           # 0..1 — how much vocal activity
    groove_energy: float           # rhythm steadiness × low_mid weight
    impact_energy: float           # kick + snare punch combined
    density_energy: float          # beat density-driven thickness
    tension_energy: float          # phrase change rate / vocal urgency

    # ----- dance breakdown (from compute_dance_energy) -----
    kick_punch: float
    snare_crack: float
    groove_tightness: float
    low_mid_density: float
    beat_confidence: float         # 0..1 — how trustworthy beatgrid is

    # ----- section-aware energy -----
    sections: list[SectionEnergy]  # ordered by start time

    # ----- structure -----
    phrase_map: list[dict]
    cue_points: list[dict]
    downbeats: list[float]
    beat_points: list[float]
    safe_entry_points: list[float]  # phrase-aligned entries (>=1.5s in)
    safe_exit_points: list[float]   # phrase-aligned exits (<=duration-3s)

    # ----- stems -----
    stems_available: bool
    stem_quality: dict[str, float] = field(default_factory=dict)
    # Keys: vocals / drums / bass / other — value 0..1.

    def section_at(self, t: float) -> SectionEnergy | None:
        """Return the section containing time t (or None if before first / after last)."""
        for sec in self.sections:
            if sec.start <= t < sec.end:
                return sec
        return self.sections[-1] if self.sections else None

    def windows_around(self, t: float, *, window_sec: float = 8.0) -> SectionEnergy | None:
        """Return the section that covers [t-w, t+w] best — used for transition windows."""
        if not self.sections:
            return None
        # Pick the section whose midpoint is closest to t.
        return min(self.sections, key=lambda s: abs((s.start + s.end) / 2 - t))


def _vocal_density_from_phrase(phrase_map: list[dict], duration: float) -> float:
    """Approx vocal density: count phrases labelled verse/chorus/hook divided by minutes."""
    if not phrase_map or duration <= 0:
        return 0.5
    vocal_labels = {"verse", "chorus", "hook", "bridge", "rap"}
    count = sum(1 for ph in phrase_map if str(ph.get("label", "")).lower() in vocal_labels)
    per_min = count / max(0.1, duration / 60.0)
    return float(min(1.0, per_min / 6.0))


def _safe_entries(phrase_map: list[dict], cue_points: list[dict], downbeats: list[float],
                  duration: float) -> list[float]:
    """First 'real start' candidates that skip the intro. Sorted ascending."""
    out: set[float] = set()
    for cue in cue_points or []:
        label = str(cue.get("label", "")).lower()
        if label in {"verse", "chorus", "drop", "hook", "main"}:
            t = float(cue.get("time") or 0.0)
            if 0.5 < t < duration - 5.0:
                out.add(round(t, 3))
    for ph in phrase_map or []:
        label = str(ph.get("label", "")).lower()
        if label in {"verse", "chorus", "drop", "hook", "main"}:
            t = float(ph.get("start") or ph.get("time") or 0.0)
            if 0.5 < t < duration - 5.0:
                out.add(round(t, 3))
    if not out and downbeats:
        for db in downbeats[:8]:
            t = float(db)
            if 1.5 < t < duration - 5.0:
                out.add(round(t, 3))
                break
    return sorted(out)


def _safe_exits(phrase_map: list[dict], cue_points: list[dict], duration: float,
                bpm: float) -> list[float]:
    """Phrase-aligned exit candidates, leaving >=3s of tail."""
    if duration <= 0:
        return []
    out: set[float] = set()
    bar = 4 * 60.0 / bpm if bpm > 0 else 2.0
    for cue in cue_points or []:
        label = str(cue.get("label", "")).lower()
        if label in {"outro", "break", "bridge", "verse", "chorus"}:
            t = float(cue.get("time") or 0.0)
            if 10.0 < t < duration - 3.0:
                out.add(round(t, 3))
    for ph in phrase_map or []:
        label = str(ph.get("label", "")).lower()
        if label in {"outro", "break", "bridge", "verse", "chorus"}:
            t = float(ph.get("start") or ph.get("time") or 0.0)
            if 10.0 < t < duration - 3.0:
                out.add(round(t, 3))
    # Always include "1 bar before duration-3" as a last-resort musical exit
    if duration > 8.0:
        out.add(round(max(10.0, duration - 3.0 - bar), 3))
    return sorted(out)


def _stem_quality_for(song) -> tuple[bool, dict[str, float]]:
    """Best-effort stem quality. Without measuring stems we report:
       - 1.0 if the stem field exists and is truthy (assume separation OK)
       - 0.0 if stems block is missing
       Future hook: read RMS of cached stem.wav to detect bleed.
    """
    stems = getattr(song, "stems", None)
    if not stems or not isinstance(stems, dict):
        return False, {"vocals": 0.0, "drums": 0.0, "bass": 0.0, "other": 0.0}
    quality = {
        "vocals": 1.0 if stems.get("vocals") else 0.0,
        "drums":  1.0 if stems.get("drums")  else 0.0,
        "bass":   1.0 if stems.get("bass")   else 0.0,
        "other":  1.0 if stems.get("other")  else 0.0,
    }
    has_all = all(v > 0 for v in quality.values())
    return has_all, quality


def _beat_confidence(song, sections: list[SectionEnergy]) -> float:
    """How trustworthy is this track's beatgrid for long mixing?

    Aggregate of per-section groove tightness, weighted by section duration.
    A track with 8 sections all scoring 0.9 groove → confidence 0.9; if a
    chunk drops to 0.3 (rubato section) the average pulls down.
    """
    if not sections:
        return 0.5
    total_dur = sum(s.end - s.start for s in sections) or 1.0
    weighted = sum((s.end - s.start) * (0.6 * (
        # tight groove + impact stability is the strongest beat-confidence
        # signal we can derive without listening.
        0.7 * (s.section_groove_energy if hasattr(s, "section_groove_energy") else 0.5)
        + 0.3 * (s.section_impact_energy if hasattr(s, "section_impact_energy") else 0.5)
    )) for s in sections)
    return float(min(1.0, weighted / total_dur))


def _composite_energies(breakdown: EnergyBreakdown,
                        sections: list[SectionEnergy],
                        vocal_density: float) -> dict[str, float]:
    """Aggregate composite energies from the dance breakdown + sections."""
    if sections:
        groove = sum((s.end - s.start) * s.section_groove_energy for s in sections)
        impact = sum((s.end - s.start) * s.section_impact_energy for s in sections)
        density = sum((s.end - s.start) * s.section_density_energy for s in sections)
        tension = sum((s.end - s.start) * s.section_tension_energy for s in sections)
        total_dur = sum(s.end - s.start for s in sections) or 1.0
        groove /= total_dur
        impact /= total_dur
        density /= total_dur
        tension /= total_dur
    else:
        groove = 0.5 * (breakdown.groove_tightness + breakdown.low_mid_density)
        impact = 0.5 * (breakdown.kick_punch + breakdown.snare_crack)
        density = breakdown.low_mid_density
        tension = breakdown.vocal_urgency
    return {
        "groove_energy": float(groove),
        "impact_energy": float(impact),
        "density_energy": float(density),
        "tension_energy": float(tension),
        "vocal_density": float(vocal_density),
    }


def build_track_profile(song) -> TrackProfile:
    """Compute the full TrackProfile for a LibrarySong.

    Pure function — no DB writes. Caller is responsible for caching the
    result if many calls are expected.
    """
    analysis = build_track_analysis_v2(song)
    duration = float(analysis.get("duration_sec") or 0)
    bpm = float(analysis.get("bpm") or 0)
    breakdown = compute_dance_energy(song)
    sections = compute_section_energy_map(song)

    phrase_map = list(analysis.get("phrase_map") or [])
    cue_points = list(analysis.get("cue_points") or [])
    downbeats = list(analysis.get("downbeats") or [])
    beat_points = list(analysis.get("beat_points") or [])

    vocal_density = _vocal_density_from_phrase(phrase_map, duration)
    composite = _composite_energies(breakdown, sections, vocal_density)
    safe_entries = _safe_entries(phrase_map, cue_points, downbeats, duration)
    safe_exits = _safe_exits(phrase_map, cue_points, duration, bpm)
    has_stems, stem_quality = _stem_quality_for(song)
    confidence = _beat_confidence(song, sections)

    return TrackProfile(
        track_id=str(getattr(song, "id", "")),
        title=str(getattr(song, "title", "") or ""),
        artist=getattr(song, "artist", None),
        duration=duration,
        bpm=bpm,
        camelot_key=getattr(song, "camelot_key", None),
        musical_key=getattr(song, "key", None),
        genre=getattr(song, "genre", None),

        global_energy=float(getattr(song, "energy", 0.5) or 0.5),
        dance_energy=breakdown.total,
        vocal_density=composite["vocal_density"],
        groove_energy=composite["groove_energy"],
        impact_energy=composite["impact_energy"],
        density_energy=composite["density_energy"],
        tension_energy=composite["tension_energy"],

        kick_punch=breakdown.kick_punch,
        snare_crack=breakdown.snare_crack,
        groove_tightness=breakdown.groove_tightness,
        low_mid_density=breakdown.low_mid_density,
        beat_confidence=confidence,

        sections=sections,

        phrase_map=phrase_map,
        cue_points=cue_points,
        downbeats=[float(d) for d in downbeats],
        beat_points=[float(b) for b in beat_points],
        safe_entry_points=safe_entries,
        safe_exit_points=safe_exits,

        stems_available=has_stems,
        stem_quality=stem_quality,
    )
