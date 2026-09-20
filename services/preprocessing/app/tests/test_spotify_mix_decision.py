"""Spotify Mix decision engine tests."""
import pytest

from app.modules.dj_control.spotify_mix.camelot_distance import (
    camelot_distance,
    is_harmonic_compatible,
    parse_camelot,
)
from app.modules.dj_control.spotify_mix.compatibility_score import (
    calculate_spotify_compatibility,
)
from app.modules.dj_control.spotify_mix.presets import get_preset_definition, list_presets
from app.modules.dj_control.spotify_mix.transition_selector import (
    select_transition_preset,
)


class TestCamelotDistance:
    def test_same_key(self):
        assert camelot_distance('8A', '8A') == 0

    def test_adjacent_same_letter(self):
        assert camelot_distance('8A', '9A') == 1
        assert camelot_distance('8A', '7A') == 1

    def test_inner_outer_swap(self):
        assert camelot_distance('8A', '8B') == 1

    def test_distance_2(self):
        assert camelot_distance('8A', '6A') == 2
        assert camelot_distance('8A', '10A') == 2

    def test_circular(self):
        assert camelot_distance('1A', '12A') == 1
        assert camelot_distance('12A', '1A') == 1

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_camelot('13A')
        with pytest.raises(ValueError):
            parse_camelot('8C')

    def test_harmonic_compatible(self):
        assert is_harmonic_compatible('8A', '9A')
        assert is_harmonic_compatible('8A', '8B')
        assert not is_harmonic_compatible('8A', '3A')


class TestCompatibilityScore:
    def test_perfect_match(self):
        prev = {'bpm': 120, 'camelot_key': '8A', 'energy': 0.7, 'loudness': -8}
        next_song = {'bpm': 121, 'camelot_key': '8A', 'energy': 0.72, 'loudness': -8}
        result = calculate_spotify_compatibility(prev, next_song)
        assert result['score'] >= 95

    def test_bpm_mismatch(self):
        prev = {'bpm': 84, 'camelot_key': '8A', 'energy': 0.7, 'loudness': -8}
        next_song = {'bpm': 140, 'camelot_key': '8A', 'energy': 0.7, 'loudness': -8}
        result = calculate_spotify_compatibility(prev, next_song)
        assert result['score'] < 60
        assert any('BPM' in issue for issue in result['issues'])

    def test_key_conflict(self):
        prev = {'bpm': 120, 'camelot_key': '8A', 'energy': 0.7, 'loudness': -8}
        next_song = {'bpm': 120, 'camelot_key': '3A', 'energy': 0.7, 'loudness': -8}
        result = calculate_spotify_compatibility(prev, next_song)
        assert result['key_distance'] >= 2


class TestPresets:
    def test_get_preset_definition(self):
        fade = get_preset_definition('fade')
        assert fade['name'] == 'Fade'
        assert fade['volume_curve'] == 'equal_power_sine'

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError):
            get_preset_definition('invalid')

    def test_list_presets(self):
        presets = list_presets()
        assert len(presets) == 5
        keys = [p['key'] for p in presets]
        assert 'fade' in keys
        assert 'rise' in keys


class TestTransitionSelector:
    def test_user_override(self):
        prev = {'bpm': 120, 'camelot_key': '8A', 'energy': 0.5}
        next_song = {'bpm': 120, 'camelot_key': '8A', 'energy': 0.5}
        result = select_transition_preset(prev, next_song, user_preference='cut')
        assert result['preset'] == 'cut'

    def test_auto_selects_blend_for_compatible(self):
        prev = {'bpm': 120, 'camelot_key': '8A', 'energy': 0.7, 'loudness': -8}
        next_song = {'bpm': 122, 'camelot_key': '9A', 'energy': 0.72, 'loudness': -8}
        result = select_transition_preset(prev, next_song)
        assert result['preset'] in ['blend', 'fade']

    def test_auto_selects_cut_for_large_bpm_diff(self):
        prev = {'bpm': 84, 'camelot_key': '8A', 'energy': 0.5, 'loudness': -8}
        next_song = {'bpm': 140, 'camelot_key': '8A', 'energy': 0.5, 'loudness': -8}
        result = select_transition_preset(prev, next_song)
        assert result['preset'] == 'cut'

    def test_auto_selects_rise_for_energy_jump(self):
        prev = {'bpm': 120, 'camelot_key': '8A', 'energy': 0.3, 'loudness': -10}
        next_song = {'bpm': 122, 'camelot_key': '9A', 'energy': 0.85, 'loudness': -7}
        result = select_transition_preset(prev, next_song)
        assert result['preset'] == 'rise'
