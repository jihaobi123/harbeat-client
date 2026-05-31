"""
Strategy Selector: pick a transition preset from phrase, stem activity, key,
energy, BPM, and stem availability.

The selector accepts the old cue-only song dict, but it also understands richer
Jetson analysis payloads:
  - segments / sections with start/end/label
  - stem_activity_windows / stem_energy_windows
  - nested activity dicts such as {"stem_activity": {"vocals": 0.8, ...}}

All scores are heuristic, but the heuristics are built around DJ constraints:
avoid double bass, avoid double vocals, keep drums stable, and shorten risky
transitions when BPM/key/energy are not friendly.
"""

from __future__ import annotations

import logging
from typing import Any

from audio_analysis import (
    assess_grid_quality,
    detect_bpm,
    find_nearest_beat,
    find_nearest_downbeat,
    transition_alignment_score,
)

logger = logging.getLogger(__name__)

STEMS = ("vocals", "drums", "bass", "other")

STEM_AWARE_PRESETS = [
    "vocal_handoff",
    "bass_swap",
    "drum_swap",
    "vocal_ducking",
    "instrumental_only",
    "vocal_solo_intro",
]
NON_STEM_PRESETS = [
    "smooth",
    "blend",
    "filter",
    "echo_out",
    "echo_freeze",
    "fade",
    "rise",
    "power",
    "melt",
    "wave",
    "cut",
    "slam",
]
ALL_PRESETS = STEM_AWARE_PRESETS + NON_STEM_PRESETS


SECTION_ALIASES = {
    "intro": "Intro",
    "verse": "Verse",
    "prechorus": "PreChorus",
    "pre-chorus": "PreChorus",
    "pre_chorus": "PreChorus",
    "chorus": "Chorus",
    "hook": "Hook",
    "drop": "Drop",
    "bridge": "Bridge",
    "break": "Breakdown",
    "breakdown": "Breakdown",
    "build": "Build",
    "buildup": "Build",
    "build-up": "Build",
    "outro": "Outro",
    "tag": "Tag",
    "solo": "Solo",
    "instrumental": "Instrumental",
    "acapella": "Acapella",
    "a cappella": "Acapella",
}

SECTION_PROFILES = {
    "Intro":        {"vocals": 0.10, "drums": 0.45, "bass": 0.40, "other": 0.55},
    "Verse":       {"vocals": 0.85, "drums": 0.70, "bass": 0.75, "other": 0.60},
    "PreChorus":   {"vocals": 0.85, "drums": 0.75, "bass": 0.75, "other": 0.75},
    "Chorus":      {"vocals": 1.00, "drums": 1.00, "bass": 1.00, "other": 1.00},
    "Hook":        {"vocals": 0.95, "drums": 0.95, "bass": 0.95, "other": 0.90},
    "Drop":        {"vocals": 0.45, "drums": 1.00, "bass": 1.00, "other": 0.90},
    "Bridge":      {"vocals": 0.55, "drums": 0.55, "bass": 0.55, "other": 0.70},
    "Breakdown":   {"vocals": 0.25, "drums": 0.20, "bass": 0.30, "other": 0.45},
    "Build":       {"vocals": 0.45, "drums": 0.90, "bass": 0.80, "other": 0.80},
    "Outro":       {"vocals": 0.30, "drums": 0.45, "bass": 0.40, "other": 0.50},
    "Tag":         {"vocals": 0.70, "drums": 0.55, "bass": 0.55, "other": 0.50},
    "Solo":        {"vocals": 0.05, "drums": 0.70, "bass": 0.75, "other": 0.95},
    "Instrumental":{"vocals": 0.05, "drums": 0.85, "bass": 0.80, "other": 0.80},
    "Acapella":    {"vocals": 1.00, "drums": 0.05, "bass": 0.05, "other": 0.10},
    "Unknown":     {"vocals": 0.50, "drums": 0.50, "bass": 0.50, "other": 0.50},
}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def _norm_label(label: Any) -> str:
    key = str(label or "Unknown").strip()
    if not key:
        return "Unknown"
    return SECTION_ALIASES.get(key.lower(), key if key in SECTION_PROFILES else "Unknown")


def _stem_dict(raw: Any) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    out: dict[str, float] = {}
    aliases = {
        "vocal": "vocals",
        "voice": "vocals",
        "drum": "drums",
        "percussion": "drums",
        "low": "bass",
        "bassline": "bass",
        "melody": "other",
        "instrumental": "other",
        "inst": "other",
    }
    for key, value in raw.items():
        name = aliases.get(str(key).lower(), str(key).lower())
        if name in STEMS:
            try:
                out[name] = _clamp(float(value))
            except (TypeError, ValueError):
                continue
    return out if out else None


def _extract_cues(song: dict) -> list[tuple[float, str]]:
    cues: list[tuple[float, str]] = []
    for source_key in ("cues", "sections", "segments"):
        for item in song.get(source_key, []) or []:
            if isinstance(item, dict):
                t = item.get("time", item.get("start", item.get("start_sec", item.get("start_s"))))
                label = item.get("label", item.get("name", item.get("section", item.get("type"))))
            else:
                try:
                    t, label = item[0], item[1]
                except Exception:
                    continue
            try:
                cues.append((float(t), _norm_label(label)))
            except (TypeError, ValueError):
                continue
    cues.sort(key=lambda x: x[0])
    return cues


def _infer_section(t: float, cues: list[tuple[float, str]]) -> str:
    prev_cue, next_cue = None, None
    for ct, cl in cues:
        if ct <= t:
            prev_cue = (ct, cl)
        elif next_cue is None:
            next_cue = (ct, cl)
            break
    if prev_cue is None and next_cue:
        return next_cue[1]
    if next_cue is None and prev_cue:
        return prev_cue[1]
    if prev_cue and next_cue:
        pl, nl = prev_cue[1], next_cue[1]
        if pl == "Intro" and nl in ("Chorus", "Hook"):
            return "Verse"
        if pl == "Verse" and nl in ("Chorus", "Hook", "Drop"):
            return "PreChorus"
        if pl in ("Bridge", "Breakdown") and nl in ("Chorus", "Drop"):
            return "Build"
        if pl in ("Chorus", "Hook") and nl == "Outro":
            return "Chorus"
        return pl
    return "Unknown"


def _cue_activity(cues: list[tuple[float, str]], start_s: float, end_s: float) -> dict:
    dur = max(0.001, end_s - start_s)
    samples = [start_s + dur * p for p in (0.10, 0.30, 0.50, 0.70, 0.90)]
    sections: list[str] = []
    activity = {stem: 0.0 for stem in STEMS}
    for t in samples:
        label = _infer_section(t, cues)
        sections.append(label)
        profile = SECTION_PROFILES.get(label, SECTION_PROFILES["Unknown"])
        for stem in STEMS:
            activity[stem] += profile[stem] / len(samples)
    return {"sections": sorted(set(sections), key=sections.index), "activity": activity, "confidence": 0.55}


def _window_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _analysis_activity(song: dict, start_s: float, end_s: float) -> dict | None:
    windows: list[dict] = []
    for key in ("stem_activity_windows", "stem_energy_windows", "analysis_windows", "segments", "sections"):
        for item in song.get(key, []) or []:
            if isinstance(item, dict):
                windows.append(item)
    if not windows:
        return None

    total_w = 0.0
    activity = {stem: 0.0 for stem in STEMS}
    sections: list[str] = []
    for item in windows:
        try:
            s0 = float(item.get("start", item.get("start_sec", item.get("start_s", item.get("time", 0.0)))))
            s1 = float(item.get("end", item.get("end_sec", item.get("end_s", s0))))
        except (TypeError, ValueError):
            continue
        if s1 <= s0:
            s1 = s0 + float(item.get("duration", item.get("duration_sec", 0.0)) or 0.0)
        overlap = _window_overlap(start_s, end_s, s0, s1)
        if overlap <= 0:
            continue

        raw = (
            _stem_dict(item.get("stem_activity"))
            or _stem_dict(item.get("activity"))
            or _stem_dict(item.get("stems"))
            or _stem_dict(item)
        )
        if not raw:
            label = _norm_label(item.get("label", item.get("section", item.get("type"))))
            raw = SECTION_PROFILES.get(label, SECTION_PROFILES["Unknown"])
        label = _norm_label(item.get("label", item.get("section", item.get("type"))))
        sections.append(label)
        for stem in STEMS:
            activity[stem] += raw.get(stem, 0.5) * overlap
        total_w += overlap

    if total_w <= 0:
        return None
    return {
        "sections": sorted(set(sections or ["Unknown"]), key=(sections or ["Unknown"]).index),
        "activity": {stem: _clamp(activity[stem] / total_w) for stem in STEMS},
        "confidence": 0.85,
    }


def _classify_window(song: dict, start_s: float, end_s: float) -> dict:
    cues = _extract_cues(song)
    cue_based = _cue_activity(cues, start_s, end_s) if cues else {
        "sections": ["Unknown"],
        "activity": SECTION_PROFILES["Unknown"].copy(),
        "confidence": 0.35,
    }
    measured = _analysis_activity(song, start_s, end_s)
    if not measured:
        return cue_based

    # Blend measured analysis with cue priors. Measured data wins but cues keep
    # the selector sane when separation/energy extraction is noisy.
    activity = {
        stem: _clamp(measured["activity"][stem] * 0.75 + cue_based["activity"][stem] * 0.25)
        for stem in STEMS
    }
    sections = measured["sections"] or cue_based["sections"]
    return {"sections": sections, "activity": activity, "confidence": measured["confidence"]}


def camelot_distance(a: int, b: int) -> int:
    diff = abs(a - b) % 12
    return min(diff, 12 - diff)


def camelot_quality(a: int, b: int) -> str:
    d = camelot_distance(a, b)
    if d == 0:
        return "perfect"
    if d == 1:
        return "neighbor"
    if d == 7:
        return "complementary"
    if d == 2:
        return "ok"
    return "tense"


def _key_bonus(quality: str) -> float:
    return {
        "perfect": 0.16,
        "neighbor": 0.14,
        "complementary": 0.12,
        "ok": 0.08,
        "tense": 0.01,
    }.get(quality, 0.04)


def _bpm_metrics(a_bpm: float, b_bpm: float, a_conf: float = 0.5, b_conf: float = 0.5) -> dict:
    if a_bpm <= 0 or b_bpm <= 0:
        return {"delta": 0.0, "ratio": 0.0, "quality": "unknown", "score": 0.06, "confidence": 0.0}
    delta = abs(a_bpm - b_bpm)
    ratio = delta / min(a_bpm, b_bpm)
    if ratio <= 0.02:
        quality, score = "locked", 0.14
    elif ratio <= 0.06:
        quality, score = "comfortable", 0.11
    elif ratio <= 0.10:
        quality, score = "wide", 0.06
    else:
        quality, score = "risky", 0.01
    # Confidence discount: low BPM confidence → reduce score
    avg_conf = (a_conf + b_conf) / 2.0
    score *= 0.6 + 0.4 * avg_conf
    return {"delta": round(delta, 3), "ratio": round(ratio, 4), "quality": quality,
            "score": round(score, 4), "confidence": round(avg_conf, 3)}


def _score_energy_gap(gap: float) -> float:
    if gap <= 0.08:
        return 0.12
    if gap <= 0.18:
        return 0.08
    if gap <= 0.30:
        return 0.04
    return 0.01


def _append(scores: list, preset: str, score: float, reasons: list[str]) -> None:
    scores.append((preset, round(_clamp(score), 4), reasons))


def score_presets(
    a_activity: dict,
    b_activity: dict,
    camelot_a: int,
    camelot_b: int,
    energy_a: float,
    energy_b: float,
    bpm_a: float,
    bpm_b: float,
    stems_available: bool,
    *,
    a_analysis: dict | None = None,
    b_analysis: dict | None = None,
    exit_time: float | None = None,
    entry_time: float | None = None,
) -> list[tuple[str, float, list[str]]]:
    scores: list[tuple[str, float, list[str]]] = []

    a_v, b_v = a_activity.get("vocals", 0.5), b_activity.get("vocals", 0.5)
    a_b, b_b = a_activity.get("bass", 0.5), b_activity.get("bass", 0.5)
    a_d, b_d = a_activity.get("drums", 0.5), b_activity.get("drums", 0.5)
    a_o, b_o = a_activity.get("other", 0.5), b_activity.get("other", 0.5)
    key_q = camelot_quality(camelot_a, camelot_b)
    key_score = _key_bonus(key_q)
    energy_gap = abs(energy_a - energy_b)
    energy_score = _score_energy_gap(energy_gap)

    # ── Audio-analysis-aware BPM scoring ──
    a_bpm_conf = a_analysis.get("bpm_confidence", 0.5) if a_analysis else 0.5
    b_bpm_conf = b_analysis.get("bpm_confidence", 0.5) if b_analysis else 0.5
    # Use detected BPM if available and confident; fall back to metadata BPM
    if a_analysis and a_analysis.get("bpm_confidence", 0) > 0.4:
        bpm_a = a_analysis.get("bpm", bpm_a)
    if b_analysis and b_analysis.get("bpm_confidence", 0) > 0.4:
        bpm_b = b_analysis.get("bpm", bpm_b)
    bpm = _bpm_metrics(bpm_a, bpm_b, a_bpm_conf, b_bpm_conf)
    tempo_score = bpm["score"]
    stem_gate = 1.0 if stems_available else 0.0

    # ── Beatgrid quality ──
    a_grid = a_analysis.get("grid_quality", {}).get("score", 0.5) if a_analysis else 0.5
    b_grid = b_analysis.get("grid_quality", {}).get("score", 0.5) if b_analysis else 0.5
    grid_score = (a_grid + b_grid) / 2.0  # [0, 1]

    # ── Phrase/beat alignment ──
    align: dict = {}
    if (a_analysis and b_analysis and exit_time is not None
          and entry_time is not None):
        align = transition_alignment_score(
            exit_time, entry_time,
            a_analysis.get("beats", []),
            b_analysis.get("beats", []),
            a_analysis.get("downbeat_indices", []),
            b_analysis.get("downbeat_indices", []),
            a_analysis.get("phrases", []),
            b_analysis.get("phrases", []),
        )
    align_score = align.get("score", 0.0)

    double_vocal_risk = a_v * b_v
    bass_conflict = a_b * b_b
    drum_bridge = (a_d + b_d) / 2.0
    instrumental_b = (b_d + b_b + b_o) / 3.0 * (1.0 - b_v)

    def stem_score(raw: float, reasons: list[str], preset: str = "") -> float:
        if not stems_available:
            reasons.append("no complete stems - use non-stem fallback")
            return 0.0
        _is_structural = preset in ("vocal_handoff", "bass_swap", "drum_swap")
        if bpm["quality"] == "risky":
            reasons.append(f"BPM stretch risky ({bpm_a:.1f}->{bpm_b:.1f})")
            raw *= 0.88 if _is_structural else 0.75
        if key_q == "tense":
            reasons.append(f"tense key ({camelot_a}A->{camelot_b}A)")
            raw *= 0.90 if _is_structural else 0.75
        # Beatgrid bonus: good grid → stem presets work better
        if grid_score > 0.8 and _is_structural:
            raw += 0.04
            reasons.append(f"tight beatgrid ({grid_score:.2f}) boosts stem control")
        elif grid_score < 0.35:
            raw *= 0.85
            reasons.append(f"loose beatgrid ({grid_score:.2f}) reduces stem precision")
        return raw * stem_gate

    # ── Stem-aware presets ──
    reasons = [
        f"double vocal risk {double_vocal_risk:.2f}",
        f"key {key_q}",
        f"BPM {bpm['quality']} ({bpm_a:.1f}->{bpm_b:.1f})",
    ]
    raw = 0.16 + 0.28 * double_vocal_risk + key_score + energy_score + tempo_score
    _append(scores, "vocal_handoff", stem_score(raw, reasons, "vocal_handoff"), reasons)

    reasons = [
        f"bass conflict {bass_conflict:.2f}",
        f"drum bridge {drum_bridge:.2f}",
    ]
    raw = 0.12 + 0.34 * bass_conflict + 0.14 * drum_bridge + tempo_score + 0.05
    _append(scores, "bass_swap", stem_score(raw, reasons, "bass_swap"), reasons)

    reasons = [f"both drum activity {drum_bridge:.2f}", f"BPM {bpm['quality']}"]
    raw = 0.10 + 0.36 * drum_bridge + 0.08 * (1.0 - abs(a_d - b_d)) + tempo_score
    _append(scores, "drum_swap", stem_score(raw, reasons, "drum_swap"), reasons)

    reasons = [f"A vocal {a_v:.2f}", f"B vocal {b_v:.2f}", "duck A vocal under B entry"]
    raw = 0.10 + 0.24 * a_v + 0.16 * b_v + key_score * 0.7 + tempo_score
    _append(scores, "vocal_ducking", stem_score(raw, reasons, "vocal_ducking"), reasons)

    vocal_floor = max(a_v, b_v)
    reasons = [f"vocal activity A={a_v:.2f}, B={b_v:.2f}", "instrumental stems can overlap cleanly when vocals are sparse"]
    raw = 0.12 + 0.28 * (1.0 - max(a_v, b_v)) + 0.20 * drum_bridge + key_score + tempo_score
    if vocal_floor > 0.60:
        raw *= 0.65
        reasons.append("high vocal activity - instrumental-only is less suitable")
    _append(scores, "instrumental_only", stem_score(raw, reasons, "instrumental_only"), reasons)

    reasons = [f"A vocal {a_v:.2f}", f"B instrumental bed {instrumental_b:.2f}"]
    raw = 0.12 + 0.28 * a_v + 0.24 * instrumental_b + key_score + tempo_score * 0.7
    _append(scores, "vocal_solo_intro", stem_score(raw, reasons, "vocal_solo_intro"), reasons)

    # ── Non-stem presets ──
    # Phrase/beat alignment bonus: smooth transitions benefit from good alignment
    align_bonus = align_score * 0.12

    _append(scores, "blend", 0.30 + key_score * 0.5 + energy_score + tempo_score + align_bonus, ["universal equal-power blend"])
    _append(scores, "smooth", 0.26 + energy_score + tempo_score + align_bonus, ["simple beatmatched crossfade"])

    reasons = ["filter masks key/bass conflicts"]
    filter_score = 0.18 + (0.16 if key_q == "tense" else 0.06) + 0.08 * bass_conflict + tempo_score * 0.6
    # Filter transitions benefit from tight beatgrid
    if grid_score > 0.75:
        filter_score += 0.04
        reasons.append("tight grid enhances filter sweep timing")
    _append(scores, "filter", filter_score, reasons)

    reasons = [f"A vocal/tail activity {max(a_v, a_o):.2f}", "echo hides phrase exit"]
    _append(scores, "echo_out", 0.12 + 0.16 * max(a_v, a_o) + (0.08 if key_q == "tense" else 0.03), reasons)

    reasons = ["short echo freeze for risky key/BPM/vocal overlap"]
    freeze_score = 0.12 + 0.14 * double_vocal_risk
    if key_q == "tense":
        freeze_score += 0.12
    if bpm["quality"] in ("wide", "risky"):
        freeze_score += 0.10
    _append(scores, "echo_freeze", freeze_score, reasons)

    _append(scores, "fade", 0.11 + (0.10 if energy_gap > 0.18 else 0.03), ["clean fade for energy mismatch"])
    _append(scores, "rise", 0.10 + max(0.0, energy_b - energy_a) * 0.35 + tempo_score * 0.5, ["energy rise into B"])
    _append(scores, "power", 0.10 + 0.16 * drum_bridge + (0.06 if energy_gap < 0.12 else 0.0), ["aggressive high-energy crossfade"])
    _append(scores, "melt", 0.08 + 0.14 * a_v + (0.06 if energy_gap < 0.12 else 0.0), ["dreamy vocal dissolve"])
    _append(scores, "wave", 0.07 + 0.14 * drum_bridge + tempo_score * 0.4, ["rhythmic pulsed blend"])
    # cut/slam benefit from precise beat alignment
    cut_bonus = 0.04 if align.get("exit_on_downbeat") else 0.0
    _append(scores, "cut", 0.08 + (0.12 if bpm["quality"] == "locked" and drum_bridge > 0.75 else 0.02) + cut_bonus, ["downbeat hard cut"])
    slam_bonus = 0.04 if align.get("exit_on_downbeat") else 0.0
    _append(scores, "slam", 0.07 + (0.12 if energy_b > energy_a + 0.12 else 0.02) + slam_bonus, ["brief silence then impact entry"])

    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def select_preset(
    song_a: dict,
    song_b: dict,
    a_out_start: float,
    a_out_end: float,
    b_in_cue: float,
    stems_available: bool = True,
    *,
    a_analysis: dict | None = None,
    b_analysis: dict | None = None,
) -> dict:
    """Return the best preset and a ranked explanation list.

    When a_analysis / b_analysis are provided (from audio_analysis.analyze_track),
    beatgrid quality, BPM confidence, and phrase alignment are incorporated
    into the scoring as DJ-critical first-priority factors.
    """
    window_len = max(0.1, a_out_end - a_out_start)
    a_win = _classify_window(song_a, a_out_start, a_out_end)
    b_win = _classify_window(song_b, b_in_cue, b_in_cue + window_len)

    camelot_a = int(song_a.get("camelot", song_a.get("camelot_number", 1)) or 1)
    camelot_b = int(song_b.get("camelot", song_b.get("camelot_number", 1)) or 1)
    energy_a = _clamp(float(song_a.get("energy", 0.5) or 0.5))
    energy_b = _clamp(float(song_b.get("energy", 0.5) or 0.5))
    bpm_a = float(song_a.get("bpm", 0.0) or 0.0)
    bpm_b = float(song_b.get("bpm", 0.0) or 0.0)

    ranked = score_presets(
        a_win["activity"],
        b_win["activity"],
        camelot_a,
        camelot_b,
        energy_a,
        energy_b,
        bpm_a,
        bpm_b,
        stems_available,
        a_analysis=a_analysis,
        b_analysis=b_analysis,
        exit_time=a_out_start,
        entry_time=b_in_cue,
    )
    best = ranked[0]
    bpm = _bpm_metrics(bpm_a, bpm_b)
    key_q = camelot_quality(camelot_a, camelot_b)
    risks = {
        "double_vocal_risk": round(a_win["activity"]["vocals"] * b_win["activity"]["vocals"], 3),
        "bass_conflict_risk": round(a_win["activity"]["bass"] * b_win["activity"]["bass"], 3),
        "bpm_quality": bpm["quality"],
        "key_quality": key_q,
    }
    result = {
        "selected": best[0],
        "score": round(best[1], 3),
        "reasons": best[2],
        "rankings": [
            {"preset": p, "score": round(s, 3), "reasons": r}
            for p, s, r in ranked[:7]
        ],
        "window_analysis": {
            "a": {
                "sections": a_win["sections"],
                "activity": {k: round(v, 3) for k, v in a_win["activity"].items()},
                "confidence": a_win["confidence"],
            },
            "b": {
                "sections": b_win["sections"],
                "activity": {k: round(v, 3) for k, v in b_win["activity"].items()},
                "confidence": b_win["confidence"],
            },
        },
        "compatibility": {
            "camelot_distance": camelot_distance(camelot_a, camelot_b),
            "camelot_quality": key_q,
            "energy_gap": round(abs(energy_a - energy_b), 3),
            "bpm_delta": bpm["delta"],
            "bpm_ratio": bpm["ratio"],
            "bpm_quality": bpm["quality"],
        },
        "risks": risks,
        "fallback": "blend" if best[0] in STEM_AWARE_PRESETS else best[0],
    }
    # Attach audio-analysis diagnostics when available
    if a_analysis and b_analysis:
        result["beat_analysis"] = {
            "a_grid_quality": a_analysis.get("grid_quality", {}).get("score", 0.0),
            "b_grid_quality": b_analysis.get("grid_quality", {}).get("score", 0.0),
            "a_bpm_confidence": a_analysis.get("bpm_confidence", 0.0),
            "b_bpm_confidence": b_analysis.get("bpm_confidence", 0.0),
        }
        if a_analysis.get("beats") and b_analysis.get("beats"):
            result["beat_analysis"]["a_beats"] = len(a_analysis["beats"])
            result["beat_analysis"]["b_beats"] = len(b_analysis["beats"])
    return result
