"""Shared mapping from analyzer output to a LibrarySong-like object."""
from __future__ import annotations

from typing import Any


def apply_analysis_result(song: Any, result: dict[str, Any]) -> None:
    """Persist the fields required by downstream timeline and Presence jobs."""
    song.bpm = result["bpm"]
    song.duration = result["duration"]
    song.key = result.get("key")
    song.camelot_key = result.get("camelot_key")
    song.energy = result.get("energy")
    song.beat_points = result.get("beat_points", [])
    song.bpm_curve = result.get("bpm_curve", [])
    song.tempo_stability = result.get("tempo_stability")
    song.beat_confidence = result.get("beat_confidence")
    song.beat_confidence_details = result.get("beat_confidence_details", {})
    song.beat_grid_offset = result.get("beat_grid_offset")
    song.beat_grid_interval = result.get("beat_grid_interval")
    song.beat_engines_used = result.get("beat_engines_used", [])
    song.beat_needs_review = int(result.get("beat_needs_review", False))
    song.time_signature = result.get("time_signature", {})
    song.energy_curve = result.get("energy_curve", [])
    song.transition_windows = result.get("transition_windows", [])
    song.downbeats = result.get("downbeats", [])
    song.phrase_map = result.get("phrase_map", [])
    song.key_confidence = result.get("key_confidence")
    raw_cues = result.get("cue_points", [])
    song_id = getattr(song, "id", "unknown")
    song.cue_points = [
        {
            "id": f"cue-{song_id}-{index}",
            "time": cue["time"],
            "label": cue["label"],
            "color": cue["color"],
        }
        for index, cue in enumerate(raw_cues)
    ]
