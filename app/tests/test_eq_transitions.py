"""EQ transitions unit tests."""
import numpy as np
import pytest

from app.modules.dj_control.spotify_mix.eq_transitions import (
    generate_eq_transition,
    generate_head_bass_swap,
    generate_mid_bass_swap,
    generate_tail_bass_swap,
    generate_three_band_fade,
)


class TestEQTransitions:
    def test_three_band_fade_starts_at_full(self):
        result = generate_three_band_fade(32, 120)
        assert result["deck_a"]["low"][0][1] == pytest.approx(1.0, abs=0.01)
        assert result["deck_b"]["low"][0][1] < 0.01

    def test_three_band_fade_ends_at_zero(self):
        result = generate_three_band_fade(32, 120)
        assert result["deck_a"]["low"][-1][1] < 0.01
        assert result["deck_b"]["low"][-1][1] > 0.99

    def test_three_band_fade_equal_power(self):
        result = generate_three_band_fade(32, 120)
        deck_a = np.array([v for _, v in result["deck_a"]["low"]])
        deck_b = np.array([v for _, v in result["deck_b"]["low"]])
        power_sum = deck_a ** 2 + deck_b ** 2
        # Equal power crossfade: a^2 + b^2 ≈ 1
        assert power_sum.min() > 0.95
        assert power_sum.max() < 1.05

    def test_mid_bass_swap_low_changes_at_midpoint(self):
        result = generate_mid_bass_swap(32, 120)
        steps = len(result["deck_a"]["low"])
        mid = steps // 2
        # Before midpoint: deck_a low full, deck_b low silent
        assert result["deck_a"]["low"][mid - 1][1] == pytest.approx(1.0, abs=0.01)
        assert result["deck_b"]["low"][mid - 1][1] < 0.01
        # After midpoint: deck_a low silent, deck_b low rising
        assert result["deck_a"]["low"][mid + 1][1] < 0.01

    def test_tail_bass_swap_holds_then_drops(self):
        result = generate_tail_bass_swap(32, 120)
        steps = len(result["deck_a"]["low"])
        # First 75%: deck_a low holds at 1.0
        check_idx = int(steps * 0.5)
        assert result["deck_a"]["low"][check_idx][1] == pytest.approx(1.0, abs=0.01)
        # End: drops to 0
        assert result["deck_a"]["low"][-1][1] < 0.01

    def test_head_bass_swap_silent_then_rises(self):
        result = generate_head_bass_swap(32, 120)
        steps = len(result["deck_b"]["low"])
        # First 25%: deck_b low silent
        check_idx = int(steps * 0.1)
        assert result["deck_b"]["low"][check_idx][1] < 0.01
        # End: rises high
        assert result["deck_b"]["low"][-1][1] > 0.5

    def test_unknown_eq_type_raises(self):
        with pytest.raises(ValueError):
            generate_eq_transition("invalid_type", 32, 120)

    def test_zero_bpm_handled(self):
        result = generate_eq_transition("three_band_fade", 32, 0)
        assert "deck_a" in result
        assert len(result["deck_a"]["low"]) > 0
