"""Adapter bridging GrooveEngine DJ planning → existing playlists API schemas.

Converts database LibrarySong data into GrooveEngine TrackMetadata,
runs PlaylistPlanner / TransitionPlanner, and maps results back to
DjMixPlanResult / DjTransitionPlanItem that the frontend already expects.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Optional

import numpy as np

# ── GrooveEngine is a sibling directory without a top-level __init__.py.
#    Its internal imports use bare module names (``from core.datatypes …``),
#    so we add GrooveEngine/ to *sys.path* once.
_GE_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "GrooveEngine"))
if _GE_ROOT not in sys.path:
    sys.path.insert(0, _GE_ROOT)

from core.datatypes import (  # noqa: E402 – path-dependent import
    AutomationLane,
    BeatAnalysis,
    BeatGrid,
    BeatPoint,
    EnergyPoint,
    MusicalKey,
    PhraseAnchor,
    PhraseSegment,
    TrackMetadata,
    TransitionPlan,
)
from core.enums import FXType, PhraseType  # noqa: E402
from logic.brain import TransitionPlanner  # noqa: E402
from logic.playlist import PlaylistPlanner  # noqa: E402

from app.modules.playlists.online_mix_planner import build_online_transition_payload
from app.modules.playlists.schemas import (
    DjFxAutomationPoint,
    DjMixPlanResult,
    DjTransitionPlanItem,
    PlaylistSongData,
)

# ---------------------------------------------------------------------------
#  Label → PhraseType mapping (analysis.py produces these labels)
# ---------------------------------------------------------------------------
_LABEL_TO_PHRASE: dict[str, PhraseType] = {
    "intro": PhraseType.INTRO,
    "outro": PhraseType.OUTRO,
    "drop": PhraseType.DROP,
    "buildup": PhraseType.BUILD,
    "build": PhraseType.BUILD,
    "breakdown": PhraseType.BRIDGE,
    "break": PhraseType.BRIDGE,
    "bridge": PhraseType.BRIDGE,
    "verse": PhraseType.VERSE,
    "chorus": PhraseType.CHORUS,
}

# Camelot key parsing for MusicalKey
_CAMELOT_TO_KEY: dict[str, tuple[str, str]] = {
    "1A": ("Ab", "minor"), "2A": ("Eb", "minor"), "3A": ("Bb", "minor"),
    "4A": ("F", "minor"),  "5A": ("C", "minor"),  "6A": ("G", "minor"),
    "7A": ("D", "minor"),  "8A": ("A", "minor"),  "9A": ("E", "minor"),
    "10A": ("B", "minor"), "11A": ("F#", "minor"), "12A": ("C#", "minor"),
    "1B": ("B", "major"),  "2B": ("F#", "major"),  "3B": ("Db", "major"),
    "4B": ("Ab", "major"), "5B": ("Eb", "major"),  "6B": ("Bb", "major"),
    "7B": ("F", "major"),  "8B": ("C", "major"),   "9B": ("G", "major"),
    "10B": ("D", "major"), "11B": ("A", "major"),  "12B": ("E", "major"),
}
_KEY_TO_CAMELOT: dict[str, str] = {}
for _cam, (_tonic, _mode) in _CAMELOT_TO_KEY.items():
    _KEY_TO_CAMELOT[f"{_tonic} {_mode}"] = _cam


# ===================================================================
#  1. Build GrooveEngine TrackMetadata from database fields
# ===================================================================

def library_song_to_track_metadata(
    *,
    song_id: int,
    title: str,
    artist: str,
    duration: float,
    bpm: Optional[float],
    key: Optional[str],
    camelot_key: Optional[str],
    energy: Optional[float],
    beat_points: list[float],
    downbeats: list[float],
    phrase_map: list[dict],
    beat_confidence: Optional[float],
    audio_path: str,
) -> TrackMetadata:
    """Convert database / LibrarySong fields into a GrooveEngine TrackMetadata."""

    effective_bpm = bpm or 120.0
    effective_duration = max(duration, 1.0)

    beatgrid = _build_beatgrid(effective_bpm, beat_points, downbeats, effective_duration)
    phrases = _build_phrases(phrase_map, beatgrid)
    energy_bars = _build_energy_bars(energy, beatgrid)
    musical_key = _build_musical_key(key, camelot_key)
    beat_analysis = _build_beat_analysis(beat_confidence, beatgrid, beat_points, downbeats)
    phrase_anchors = _build_phrase_anchors(phrases)

    return TrackMetadata(
        track_id=str(song_id),
        title=title,
        artist=artist or None,
        path=audio_path or "",
        duration_seconds=effective_duration,
        sample_rate=44100,
        channels=2,
        beatgrid=beatgrid,
        beat_analysis=beat_analysis,
        phrases=phrases,
        phrase_anchors=phrase_anchors,
        energy_bars=energy_bars,
        key=musical_key,
    )


# -------------------------------------------------------------------
#  BeatGrid
# -------------------------------------------------------------------

def _build_beatgrid(
    bpm: float, beat_points: list[float], downbeats: list[float], duration: float,
) -> BeatGrid:
    beats_sorted = sorted(beat_points) if beat_points else []

    # Synthesise a beat grid if none exists
    if not beats_sorted:
        interval = 60.0 / bpm
        n = max(4, int(duration / interval))
        beats_sorted = [round(i * interval, 4) for i in range(n)]

    db_sorted = sorted(downbeats) if downbeats else []

    # Determine bar-phase offset from downbeats
    offset = 0
    if db_sorted and beats_sorted:
        first_db = db_sorted[0]
        min_dist = float("inf")
        for i, t in enumerate(beats_sorted[:16]):
            d = abs(t - first_db)
            if d < min_dist:
                min_dist = d
                offset = i % 4

    beat_list: list[BeatPoint] = []
    for idx, t in enumerate(beats_sorted):
        adj = idx - offset
        if adj < 0:
            bar = 1
            bib = idx + 1
        else:
            bar = adj // 4 + 1
            bib = (adj % 4) + 1
        bib = min(bib, 4)
        beat_list.append(
            BeatPoint(
                index=idx + 1,
                time=round(t, 4),
                bar=bar,
                beat_in_bar=bib,
                is_downbeat=(bib == 1),
            )
        )

    total_bars = max(1, beat_list[-1].bar) if beat_list else 1
    final_downbeats = db_sorted or [b.time for b in beat_list if b.is_downbeat]

    return BeatGrid(bpm=bpm, beats=beat_list, bars=total_bars, downbeats=final_downbeats)


# -------------------------------------------------------------------
#  Phrases
# -------------------------------------------------------------------

def _time_to_bar(time_sec: float, beatgrid: BeatGrid) -> int:
    best_bar = 1
    for beat in beatgrid.beats:
        if beat.time <= time_sec + 0.05:
            best_bar = beat.bar
        else:
            break
    return best_bar


def _build_phrases(phrase_map: list[dict], beatgrid: BeatGrid) -> list[PhraseSegment]:
    if not phrase_map:
        return [
            PhraseSegment(
                phrase_type=PhraseType.UNKNOWN,
                start_time=0.0,
                end_time=beatgrid.beats[-1].time if beatgrid.beats else 0.0,
                start_bar=1,
                end_bar=beatgrid.bars,
            )
        ]

    segments: list[PhraseSegment] = []
    for entry in phrase_map:
        start_t = float(entry.get("start", 0))
        end_t = float(entry.get("end", 0))
        label = str(entry.get("label", "")).lower().strip()
        phrase_type = _LABEL_TO_PHRASE.get(label, PhraseType.UNKNOWN)

        start_bar = _time_to_bar(start_t, beatgrid)
        end_bar = _time_to_bar(end_t, beatgrid)
        if end_bar < start_bar:
            end_bar = start_bar

        segments.append(
            PhraseSegment(
                phrase_type=phrase_type,
                start_time=start_t,
                end_time=end_t,
                start_bar=max(1, start_bar),
                end_bar=max(1, end_bar),
            )
        )
    return segments


# -------------------------------------------------------------------
#  Energy bars
# -------------------------------------------------------------------

def _build_energy_bars(energy: Optional[float], beatgrid: BeatGrid) -> list[EnergyPoint]:
    e = max(0.0, min(1.0, energy if energy is not None else 0.5))
    total_bars = beatgrid.bars

    # Pre-compute bar → (start_time, end_time) from beats
    bar_times: dict[int, tuple[float, float]] = {}
    for beat in beatgrid.beats:
        bar = beat.bar
        if bar not in bar_times:
            bar_times[bar] = (beat.time, beat.time)
        else:
            bar_times[bar] = (bar_times[bar][0], beat.time)

    points: list[EnergyPoint] = []
    for bar in range(1, total_bars + 1):
        st, et = bar_times.get(bar, (0.0, 0.0))
        points.append(
            EnergyPoint(bar=bar, start_time=st, end_time=et, rms=e, spectral_flux=0.0, combined=e)
        )
    return points


# -------------------------------------------------------------------
#  MusicalKey
# -------------------------------------------------------------------

def _build_musical_key(key: Optional[str], camelot_key: Optional[str]) -> MusicalKey:
    camelot = _normalize_camelot(camelot_key)

    if camelot and camelot in _CAMELOT_TO_KEY:
        tonic, mode = _CAMELOT_TO_KEY[camelot]
        return MusicalKey(tonic=tonic, mode=mode, camelot=camelot)

    if key:
        parts = key.strip().split()
        if len(parts) >= 2:
            tonic = parts[0]
            mode = "minor" if "min" in parts[-1].lower() else "major"
            cam = _KEY_TO_CAMELOT.get(f"{tonic} {mode}")
            return MusicalKey(tonic=tonic, mode=mode, camelot=cam)
        return MusicalKey(tonic=parts[0])

    return MusicalKey()


def _normalize_camelot(key: Optional[str]) -> Optional[str]:
    if not key:
        return None
    s = key.strip().upper()
    if len(s) < 2:
        return None
    num, mode = s[:-1], s[-1]
    if not num.isdigit() or mode not in {"A", "B"}:
        return None
    n = int(num)
    return f"{n}{mode}" if 1 <= n <= 12 else None


# -------------------------------------------------------------------
#  BeatAnalysis
# -------------------------------------------------------------------

def _build_beat_analysis(
    beat_confidence: Optional[float],
    beatgrid: BeatGrid,
    beat_points: list[float],
    downbeats: list[float],
) -> BeatAnalysis:
    conf = max(0.0, min(1.0, beat_confidence)) if beat_confidence is not None else 0.5
    has_good_beats = bool(beat_points) and len(beat_points) >= 8
    has_downbeats = bool(downbeats) and len(downbeats) >= 4

    return BeatAnalysis(
        beat_confidence=conf,
        downbeat_confidence=min(conf, 0.7) if has_downbeats else 0.35,
        bar_phase_confidence=min(conf, 0.65) if has_downbeats else 0.3,
        sub_beat_confidence=min(conf, 0.6),
        beat_count=len(beat_points),
        local_tempo_stability=0.7 if has_good_beats else 0.4,
        downbeat_regularness=0.65 if has_downbeats else 0.35,
        local_window_stability_min=0.55 if has_good_beats else 0.35,
        local_window_stability_mean=0.65 if has_good_beats else 0.45,
        phase_drift_risk=0.35 if has_good_beats else 0.65,
        long_blend_stability=0.6 if has_good_beats else 0.3,
        estimated_phase_error_beats=0.15 if has_good_beats else 0.5,
        recommended_max_overlap_beats=16 if has_good_beats else 8,
        beat_usable=has_good_beats,
        phrase_sync_usable=has_good_beats and has_downbeats,
        long_blend_usable=has_good_beats and has_downbeats and conf >= 0.5,
        drift_prone=not has_good_beats,
        usable_for_long_blend=has_good_beats and has_downbeats and conf >= 0.5,
        usable_for_phrase_sync=has_good_beats and has_downbeats,
        ambiguous_bar_phase=not has_downbeats,
    )


# -------------------------------------------------------------------
#  Phrase anchors
# -------------------------------------------------------------------

def _build_phrase_anchors(phrases: list[PhraseSegment]) -> list[PhraseAnchor]:
    anchors: list[PhraseAnchor] = []
    for phrase in phrases:
        anchors.append(
            PhraseAnchor(
                bar=phrase.start_bar,
                anchor_type="phrase_start",
                strength=0.7,
                phrase_type=phrase.phrase_type,
            )
        )
        if phrase.end_bar != phrase.start_bar:
            anchors.append(
                PhraseAnchor(
                    bar=phrase.end_bar,
                    anchor_type="phrase_end",
                    strength=0.6,
                    phrase_type=phrase.phrase_type,
                )
            )
    return anchors


# ===================================================================
#  2. Convert GrooveEngine TransitionPlan → API DjTransitionPlanItem
# ===================================================================

def _camelot_relation(a: Optional[str], b: Optional[str]) -> str:
    if not a or not b:
        return "unknown"
    if a == b:
        return "same-key"
    try:
        na, ma = int(a[:-1]), a[-1]
        nb, mb = int(b[:-1]), b[-1]
    except (ValueError, IndexError):
        return "unknown"
    if ma == mb and ((na - nb) % 12 in {1, 11}):
        return "neighbor"
    if na == nb and ma != mb:
        return "relative"
    return "clash"


def transition_plan_to_dj_item(
    plan: TransitionPlan,
    from_song_id: int,
    to_song_id: int,
    from_meta: TrackMetadata,
    to_meta: TrackMetadata,
    energy_target: Optional[str] = None,
) -> DjTransitionPlanItem:
    """Convert a GrooveEngine TransitionPlan to the API DjTransitionPlanItem."""

    target_bpm = plan.target_bpm
    beat_interval = 60.0 / target_bpm
    crossfade_sec = plan.overlap_duration_beats * beat_interval

    # Exit time = mix_start_time of track A
    exit_time = plan.mix_start_time

    # Entry time = start of entry bar in track B
    entry_time = 0.0
    entry_beat = 1
    for beat in to_meta.beatgrid.beats:
        if beat.bar == plan.track_b_entry_bar and beat.beat_in_bar == 1:
            entry_time = beat.time
            entry_beat = beat.index
            break

    # Exit beat index in track A
    exit_beat = 1
    for beat in from_meta.beatgrid.beats:
        if beat.bar == plan.track_a_exit_bar and beat.beat_in_bar == 1:
            exit_beat = beat.index
            break

    tempo_ratio = round(target_bpm / from_meta.beatgrid.bpm, 4)
    key_rel = _camelot_relation(from_meta.key.camelot, to_meta.key.camelot)

    from_interval = 60.0 / from_meta.beatgrid.bpm
    to_interval = 60.0 / to_meta.beatgrid.bpm

    fx_points = _automation_to_fx_points(plan.automation, beat_interval)

    return DjTransitionPlanItem(
        from_song_id=from_song_id,
        to_song_id=to_song_id,
        entry_beat=entry_beat,
        exit_beat=exit_beat,
        entry_time_sec=round(entry_time, 3),
        exit_time_sec=round(exit_time, 3),
        from_beat_interval_sec=round(from_interval, 4),
        to_beat_interval_sec=round(to_interval, 4),
        phase_anchor_sec=round(max(0.0, exit_time - crossfade_sec), 3),
        crossfade_sec=round(crossfade_sec, 3),
        tempo_ratio=tempo_ratio,
        key_relation=key_rel,
        transition_technique=plan.strategy.value,
        energy_target=energy_target or "medium",
        fx_automation=fx_points,
        score=round(plan.score_breakdown.total_score, 4),
    )


# -------------------------------------------------------------------
#  Automation conversion (beat-based → time-based EQ points)
# -------------------------------------------------------------------

def _automation_to_fx_points(
    automation: list[AutomationLane], beat_interval: float,
) -> list[DjFxAutomationPoint]:
    """Flatten GrooveEngine AutomationLane points into DjFxAutomationPoint list.

    Each unique (deck, beat_offset) combination becomes one point with all
    EQ/filter fields merged.  FXType values are mapped to the closest
    parametric EQ / filter field the frontend supports.
    """

    # Group by (deck_target, beat_offset)
    grouped: dict[tuple[str, float], dict[str, float]] = {}

    for lane in automation:
        for pt in lane.points:
            deck_target = "from" if pt.deck == "A" else "to"
            key = (deck_target, pt.beat_offset)
            if key not in grouped:
                grouped[key] = {
                    "gain_db": 0.0,
                    "lowpass_hz": 18000.0,
                    "highpass_hz": 30.0,
                    "eq_low_db": 0.0,
                    "eq_mid_db": 0.0,
                    "eq_high_db": 0.0,
                }
            state = grouped[key]
            _apply_fx(state, pt.fx_type, pt.value)

    result: list[DjFxAutomationPoint] = []
    for (target, beat_offset) in sorted(grouped, key=lambda k: (k[0], k[1])):
        state = grouped[(target, beat_offset)]
        result.append(
            DjFxAutomationPoint(
                target=target,  # type: ignore[arg-type]
                time_sec=round(beat_offset * beat_interval, 3),
                gain_db=round(state["gain_db"], 2),
                lowpass_hz=round(state["lowpass_hz"], 1),
                highpass_hz=round(state["highpass_hz"], 1),
                eq_low_db=round(state["eq_low_db"], 2),
                eq_mid_db=round(state["eq_mid_db"], 2),
                eq_high_db=round(state["eq_high_db"], 2),
            )
        )
    return result


def _apply_fx(state: dict[str, float], fx_type: FXType, value: float) -> None:
    """Merge a single GrooveEngine FXType/value into the EQ parameter dict."""

    if fx_type == FXType.VOLUME:
        state["gain_db"] = max(-20.0, 20.0 * math.log10(max(value, 0.01)))
    elif fx_type == FXType.HIGH_PASS:
        state["highpass_hz"] = 30.0 + value * 4000.0
    elif fx_type == FXType.LOW_EQ:
        state["eq_low_db"] = (value - 1.0) * 12.0
    elif fx_type == FXType.MID_EQ:
        state["eq_mid_db"] = (value - 1.0) * 12.0
    elif fx_type == FXType.HIGH_EQ:
        state["eq_high_db"] = (value - 1.0) * 12.0
    elif fx_type == FXType.DELAY_MIX:
        # Echo send → approximate as a high-end dip
        state["eq_high_db"] = min(state["eq_high_db"], -3.0 * value)
    elif fx_type == FXType.REVERB_MIX:
        # Reverb send → approximate as a mid-range softening
        state["eq_mid_db"] = min(state["eq_mid_db"], -2.0 * value)
    elif fx_type in (FXType.NOISE_LEVEL, FXType.DELAY_FEEDBACK):
        pass  # no direct EQ mapping


# ===================================================================
#  3. Top-level: run GrooveEngine planning → DjMixPlanResult
# ===================================================================

def run_groove_engine_plan(
    track_metas: list[TrackMetadata],
    song_playlist_data: dict[int, PlaylistSongData],
    processed_files: dict[int, str],
    style_meta: dict[int, dict[str, str]],
    energy_target: Optional[str] = None,
) -> DjMixPlanResult:
    """Run GrooveEngine planning and return an API-ready DjMixPlanResult.

    Parameters
    ----------
    track_metas : list[TrackMetadata]
        GrooveEngine metadata for each candidate track (built via
        ``library_song_to_track_metadata``).
    song_playlist_data : dict[int, PlaylistSongData]
        Map song_id → PlaylistSongData (for the response playlist).
    processed_files / style_meta :
        Pass-through from the style-mix step.
    energy_target :
        Optional energy hint (``"low"``/``"medium"``/``"high"``).
    """

    planner = PlaylistPlanner(TransitionPlanner())
    playlist_plan = planner.plan(track_metas)

    # song_id is stored as str(int) in TrackMetadata.track_id
    meta_by_id: dict[str, TrackMetadata] = {m.track_id: m for m in track_metas}

    ordered_playlist: list[PlaylistSongData] = []
    for idx, tid in enumerate(playlist_plan.ordered_track_ids):
        song_id = int(tid)
        data = song_playlist_data.get(song_id)
        if data:
            ordered_playlist.append(data.model_copy(update={"order_index": idx}))

    transition_items: list[DjTransitionPlanItem] = []
    for tr in playlist_plan.transitions:
        from_sid = int(tr.track_a_id)
        to_sid = int(tr.track_b_id)
        from_meta = meta_by_id[tr.track_a_id]
        to_meta = meta_by_id[tr.track_b_id]
        item = transition_plan_to_dj_item(
            plan=tr.plan,
            from_song_id=from_sid,
            to_song_id=to_sid,
            from_meta=from_meta,
            to_meta=to_meta,
            energy_target=energy_target,
        )
        online_payload = build_online_transition_payload(from_meta, to_meta, item)
        item.online_mix_safety = online_payload["online_mix_safety"]
        item.mix_control_timeline = online_payload["mix_control_timeline"]
        transition_items.append(item)

    return DjMixPlanResult(
        playlist=ordered_playlist,
        processed_files=processed_files,
        meta=style_meta,
        transition_plan=transition_items,
    )


def identify_loop_friendly_segments(
    metadata: TrackMetadata,
    min_bars: int = 4,
    max_bars: int = 16,
) -> list[dict]:
    """Identify segments suitable for looping (consistent BPM, key, and energy).

    Finds contiguous bar ranges where:
    - BPM stability is adequate (beat_analysis.local_window_stability_min >= 0.6)
    - Energy variance is low (stddev of energy_bars in range < 0.15)
    - Phrase type is suitable (CHORUS, DROP, or VERSE)

    Returns list of dicts with ``start_bar``, ``end_bar``, ``phrase_type``.
    """
    from core.enums import PhraseType

    suitable_phrases = {PhraseType.CHORUS, PhraseType.DROP, PhraseType.VERSE}
    stable = metadata.beat_analysis.local_window_stability_min >= 0.6

    segments: list[dict] = []
    for phrase in metadata.phrases:
        if phrase.phrase_type not in suitable_phrases:
            continue
        length = phrase.end_bar - phrase.start_bar + 1
        if length < min_bars or length > max_bars:
            continue

        # Check energy variance in this phrase range
        energies = [
            e.combined
            for e in metadata.energy_bars
            if phrase.start_bar <= e.bar <= phrase.end_bar
        ]
        if energies and len(energies) >= 2:
            variance = float(np.std(energies))
            if variance > 0.15:
                continue

        segments.append({
            "start_bar": phrase.start_bar,
            "end_bar": phrase.end_bar,
            "phrase_type": phrase.phrase_type.value,
            "confidence": phrase.confidence,
            "stable": stable,
        })

    return segments
