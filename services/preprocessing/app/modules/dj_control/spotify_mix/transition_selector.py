"""Auto-mode transition selector.

Picks the most appropriate Spotify Mix preset based on track compatibility.
"""
from __future__ import annotations

from typing import Any, Dict

from .compatibility_score import calculate_spotify_compatibility
from .presets import get_preset_definition


def select_transition_preset(
    prev_song: Dict[str, Any],
    next_song: Dict[str, Any],
    user_preference: str = 'auto',
) -> Dict[str, Any]:
    """Auto-select transition preset based on track compatibility.

    Args:
        prev_song: Current track features (bpm/camelot_key/energy/loudness).
        next_song: Next track features.
        user_preference: User override (auto/fade/rise/blend/cut/overlap).

    Returns:
        {
            'preset': 'fade' | 'rise' | 'blend' | 'cut' | 'overlap',
            'compatibility': {...},
            'reason': str,
            'preset_definition': {...}
        }
    """
    if user_preference != 'auto':
        return {
            'preset': user_preference,
            'compatibility': calculate_spotify_compatibility(prev_song, next_song),
            'reason': f'User selected: {user_preference}',
            'preset_definition': get_preset_definition(user_preference),
        }

    compat = calculate_spotify_compatibility(prev_song, next_song)
    score = compat['score']
    bpm_ratio = compat['bpm_ratio']
    key_dist = compat.get('key_distance')
    energy_delta = compat['energy_delta']

    energy1 = float(prev_song.get('energy') or 0.5)
    energy2 = float(next_song.get('energy') or 0.5)

    # Decision tree
    if bpm_ratio > 1.20:
        preset = 'cut'
        reason = f'BPM ratio {bpm_ratio:.2f} too large for smooth transition'
    elif energy_delta > 0.35 and energy2 > energy1:
        preset = 'rise'
        reason = f'Energy rises by {energy_delta:.2f}'
    elif score >= 80 and key_dist is not None and key_dist <= 1:
        preset = 'blend'
        reason = f'High compatibility (score={score:.0f}, key_dist={key_dist})'
    elif score >= 60:
        preset = 'fade'
        reason = f'Moderate compatibility (score={score:.0f})'
    elif score >= 40:
        preset = 'overlap'
        reason = f'Low compatibility (score={score:.0f}), minimal processing'
    else:
        preset = 'cut'
        reason = f'Very low compatibility (score={score:.0f})'

    return {
        'preset': preset,
        'compatibility': compat,
        'reason': reason,
        'preset_definition': get_preset_definition(preset),
    }
