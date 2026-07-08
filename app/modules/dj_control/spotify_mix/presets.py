"""Spotify Mix preset definitions.

Six transition presets matching Spotify's Mix feature: Auto/Fade/Rise/Blend/Cut/Overlap.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List


class SpotifyPreset(str, Enum):
    """Spotify Mix transition presets."""
    AUTO = 'auto'
    FADE = 'fade'
    RISE = 'rise'
    BLEND = 'blend'
    CUT = 'cut'
    OVERLAP = 'overlap'


PRESET_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    'fade': {
        'name': 'Fade',
        'name_zh': '标准淡化',
        'description': 'Equal-power cosine/sine crossfade',
        'duration_beats': 16,
        'volume_curve': 'equal_power_sine',
        'eq_curve': None,
        'filter_curve': None,
        'use_cases': ['ambient', 'low_energy_change'],
    },
    'rise': {
        'name': 'Rise',
        'name_zh': '上升能量',
        'description': 'Highpass filter sweep with energy rise',
        'duration_beats': 16,
        'volume_curve': 'exponential_in',
        'eq_curve': None,
        'filter_curve': 'highpass_sweep',
        'filter_start_hz': 20,
        'filter_end_hz': 2000,
        'use_cases': ['energy_up', 'build_up'],
    },
    'blend': {
        'name': 'Blend',
        'name_zh': '混合',
        'description': 'Mid bass swap with equal-power fade',
        'duration_beats': 32,
        'volume_curve': 'equal_power_sine',
        'eq_curve': 'mid_bass_swap',
        'filter_curve': None,
        'use_cases': ['compatible_keys', 'similar_bpm'],
    },
    'cut': {
        'name': 'Cut',
        'name_zh': '硬切',
        'description': 'Instant switch on downbeat',
        'duration_beats': 1,
        'volume_curve': 'instant',
        'eq_curve': None,
        'filter_curve': None,
        'use_cases': ['style_change', 'large_bpm_diff'],
    },
    'overlap': {
        'name': 'Overlap',
        'name_zh': '重叠',
        'description': 'Simple overlap, no EQ processing',
        'duration_beats': 8,
        'volume_curve': 'linear',
        'eq_curve': None,
        'filter_curve': None,
        'use_cases': ['fast_transition', 'minimal_effect'],
    },
}


def get_preset_definition(preset: str) -> Dict[str, Any]:
    """Get a preset definition.

    Args:
        preset: Preset key (fade/rise/blend/cut/overlap).

    Returns:
        Preset definition dict (a copy, safe to mutate).

    Raises:
        ValueError: Unknown preset.
    """
    if preset not in PRESET_DEFINITIONS:
        raise ValueError(
            f"Unknown preset: {preset}. "
            f"Available: {list(PRESET_DEFINITIONS.keys())}"
        )
    return PRESET_DEFINITIONS[preset].copy()


def list_presets() -> List[Dict[str, Any]]:
    """List all presets."""
    return [
        {'key': key, **definition}
        for key, definition in PRESET_DEFINITIONS.items()
    ]
