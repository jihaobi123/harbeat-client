"""Volume curves unit tests."""
import numpy as np
import pytest

from app.modules.dj_control.spotify_mix.volume_curves import (
    VOLUME_CURVE_GENERATORS,
    equal_power_sine,
    exponential_fade,
    generate_volume_curve,
    instant,
    linear_fade,
    overlap_fade,
    quick_out,
    smooth_fade,
)


class TestVolumeCurves:
    def test_equal_power_sine_squared_sum_is_one(self):
        fade_out, fade_in = equal_power_sine(100)
        power = fade_out ** 2 + fade_in ** 2
        # Equal power: |a|^2 + |b|^2 ≈ 1 everywhere
        assert power.min() > 0.99
        assert power.max() < 1.01

    def test_equal_power_sine_endpoints(self):
        fade_out, fade_in = equal_power_sine(100)
        assert fade_out[0] == pytest.approx(1.0, abs=0.01)
        assert fade_out[-1] == pytest.approx(0.0, abs=0.01)
        assert fade_in[0] == pytest.approx(0.0, abs=0.01)
        assert fade_in[-1] == pytest.approx(1.0, abs=0.01)

    def test_linear_fade_endpoints(self):
        fade_out, fade_in = linear_fade(100)
        assert fade_out[0] == 1.0
        assert fade_out[-1] == 0.0
        assert fade_in[0] == 0.0
        assert fade_in[-1] == 1.0

    def test_exponential_fade_endpoints(self):
        fade_out, fade_in = exponential_fade(100)
        assert fade_out[0] == pytest.approx(1.0, abs=0.001)
        assert fade_out[-1] == pytest.approx(0.0, abs=0.001)

    def test_smooth_fade_monotonic(self):
        fade_out, fade_in = smooth_fade(100)
        # Smooth fade should be monotonic
        diffs = np.diff(fade_in)
        assert (diffs >= -0.01).all()  # Non-decreasing

    def test_overlap_fade_has_full_volume_region(self):
        fade_out, fade_in = overlap_fade(100, overlap_pct=0.5)
        mid = 50
        # At midpoint, both should be at full
        assert fade_out[mid] == pytest.approx(1.0, abs=0.01)
        assert fade_in[mid] == pytest.approx(1.0, abs=0.01)

    def test_quick_out_fast_drop(self):
        fade_out, _ = quick_out(100)
        # By 30% point, fade_out should be 0
        assert fade_out[35] == pytest.approx(0.0, abs=0.01)

    def test_instant_at_midpoint(self):
        fade_out, fade_in = instant(100)
        assert fade_out[10] == 1.0  # Before midpoint
        assert fade_out[60] == 0.0  # After midpoint
        assert fade_in[10] == 0.0
        assert fade_in[60] == 1.0

    def test_generate_volume_curve(self):
        curve = generate_volume_curve("equal_power_sine", 16, 120)
        assert "deck_a" in curve
        assert "deck_b" in curve
        assert curve["curve_type"] == "equal_power_sine"
        assert curve["duration_sec"] == pytest.approx(8.0, rel=0.01)

    def test_unknown_curve_raises(self):
        with pytest.raises(ValueError):
            generate_volume_curve("invalid_curve", 16, 120)

    def test_all_curves_registered(self):
        expected = {
            "equal_power_sine", "linear", "exponential_in", "exponential",
            "smooth", "overlap", "quick_out", "instant",
        }
        assert expected.issubset(VOLUME_CURVE_GENERATORS.keys())
