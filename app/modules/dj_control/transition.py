"""DJ Control transition integration layer for HarBeat Mix effects.

Bridges LibrarySong objects to local transition-effect algorithms. These
functions reproduce a Spotify-Mix-like listening experience without calling
Spotify Web API or relying on Spotify catalog metadata.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.modules.dj_control.spotify_mix import (
    eq_transitions as eq_mod,
    filter_transitions as filter_mod,
    presets as preset_mod,
    smart_reorder as reorder_mod,
    transition_selector as selector_mod,
    volume_curves as volume_mod,
)


_PRESET_TO_STYLE = {
    "fade": "smooth",
    "rise": "rise",
    "blend": "blend",
    "cut": "cut",
    "overlap": "smooth",
}

_EQ_ALIASES = {
    "three_band_fade": "three_band_fade",
    "mid_bass_swap": "mid_bass_swap",
    "tail_bass_swap": "tail_bass_swap",
    "head_bass_swap": "head_bass_swap",
    "smooth_blend": "three_band_fade",
    "soft_bass_swap": "mid_bass_swap",
    "hard_bass_swap": "tail_bass_swap",
}

_FILTER_ALIASES = {
    "lowpass_in": "lowpass_in",
    "lowpass_out": "lowpass_out",
    "highpass_in": "highpass_in",
    "highpass_out": "highpass_out",
    "highpass_sweep": "highpass_in",
    "filter_sweep": "lowpass_in",
}


def _song_features(song) -> Dict[str, Any]:
    """Extract features from a LibrarySong-shaped object for Spotify Mix."""
    loudness = None
    loudness_profile = getattr(song, "loudness_profile", None)
    if isinstance(loudness_profile, dict):
        loudness = loudness_profile.get("integrated_lufs")
    return {
        "song_id": str(getattr(song, "id", "")),
        "bpm": getattr(song, "bpm", None) or 120.0,
        "camelot_key": getattr(song, "camelot_key", None) or "",
        "energy": getattr(song, "energy", None) or 0.5,
        "loudness": loudness if loudness is not None else -8.0,
    }


def decide_mix_preset(
    prev_song,
    next_song,
    user_preference: str = "auto",
) -> Dict[str, Any]:
    """Decide local HarBeat Mix preset for a song pair."""
    return selector_mod.select_transition_preset(
        _song_features(prev_song),
        _song_features(next_song),
        user_preference=user_preference,
    )


def mix_effect_presets() -> Dict[str, Any]:
    """Return the public local mix-effect preset catalog."""
    return {"presets": preset_mod.list_presets()}


def smart_reorder(
    songs: List[Any],
    bpm_tolerance: float = 0.03,
    prefer_energy_flow: bool = True,
) -> List[Any]:
    """Smart reorder a list of LibrarySong objects.

    Returns the songs in the new order (same objects, not features).
    """
    if len(songs) <= 1:
        return list(songs)
    features = [_song_features(s) for s in songs]
    by_id = {f["song_id"]: songs[i] for i, f in enumerate(features)}
    reordered_features = reorder_mod.smart_reorder(
        features, bpm_tolerance=bpm_tolerance, prefer_energy_flow=prefer_energy_flow,
    )
    return [by_id[f["song_id"]] for f in reordered_features if f["song_id"] in by_id]


def generate_eq_curve(eq_type: str, duration_beats: int, bpm: float) -> Dict[str, Any]:
    resolved = _EQ_ALIASES.get(eq_type, eq_type)
    return eq_mod.generate_eq_transition(resolved, duration_beats, bpm)


def generate_filter_curve(filter_type: str, duration_beats: int, bpm: float) -> Dict[str, Any]:
    resolved = _FILTER_ALIASES.get(filter_type, filter_type)
    return filter_mod.generate_filter_transition(resolved, duration_beats, bpm)


def generate_volume_curve(curve_type: str, duration_beats: int, bpm: float) -> Dict[str, Any]:
    return volume_mod.generate_volume_curve(curve_type, duration_beats, bpm)


def enrich_transition_plan_with_mix_effects(
    plan: Dict[str, Any],
    prev_song,
    next_song,
    user_preference: str = "auto",
) -> Dict[str, Any]:
    """Attach local mix-effect decision metadata and curves to a plan."""
    decision = decide_mix_preset(prev_song, next_song, user_preference)
    preset = str(decision.get("preset") or "fade")
    preset_def = decision.get("preset_definition") or preset_mod.get_preset_definition(preset)
    bpm = float(getattr(prev_song, "bpm", None) or getattr(next_song, "bpm", None) or 120.0)
    duration_beats = int(preset_def.get("duration_beats") or 16)

    volume_curve = generate_volume_curve(str(preset_def.get("volume_curve") or "equal_power_sine"), duration_beats, bpm)
    eq_curve = None
    filter_curve = None
    eq_name = preset_def.get("eq_curve")
    if eq_name:
        eq_curve = generate_eq_curve(str(eq_name), duration_beats, bpm)
    filter_name = preset_def.get("filter_curve")
    if filter_name:
        filter_curve = generate_filter_curve(str(filter_name), duration_beats, bpm)

    plan["mix_effects"] = {
        "preset": preset,
        "requested_preset": user_preference,
        "decision": decision,
        "preset_definition": preset_def,
    }
    plan["decision"] = decision
    plan["volume_curves"] = volume_curve
    plan["eq_curves"] = eq_curve
    plan["filter_curves"] = filter_curve
    plan["mix_preset"] = preset
    plan["duration_beats"] = duration_beats
    if volume_curve.get("duration_sec"):
        plan["duration_sec"] = round(float(volume_curve["duration_sec"]), 3)
        plan["fade_sec"] = plan["duration_sec"]
    plan["style"] = _PRESET_TO_STYLE.get(preset, plan.get("style") or "blend")
    plan["rk_style"] = plan["style"]
    return plan
