"""Filter transitions unit tests."""
import pytest

from app.modules.dj_control.spotify_mix.filter_transitions import (
    FULL_FREQ,
    HIGHPASS_MAX,
    HIGHPASS_MIN,
    LOWPASS_MIN,
    generate_combined_filter,
    generate_dj_filter_curve,
    generate_filter_transition,
    generate_highpass_filter_in,
    generate_highpass_filter_out,
    generate_lowpass_filter_in,
    generate_lowpass_filter_out,
)


class TestFilterTransitions:
    def test_lowpass_in_starts_at_full_freq(self):
        result = generate_lowpass_filter_in(16, 120)
        first_freq = result["frequency"][0][1]
        assert first_freq == pytest.approx(FULL_FREQ, rel=0.01)
        assert result["filter_type"] == "lowpass"

    def test_lowpass_in_ends_at_target(self):
        result = generate_lowpass_filter_in(16, 120, target_freq=300)
        last_freq = result["frequency"][-1][1]
        assert last_freq == pytest.approx(300, rel=0.05)

    def test_lowpass_out_reverses(self):
        result = generate_lowpass_filter_out(16, 120, start_freq=300)
        assert result["frequency"][0][1] == pytest.approx(300, rel=0.05)
        assert result["frequency"][-1][1] == pytest.approx(FULL_FREQ, rel=0.01)

    def test_highpass_in_starts_low(self):
        result = generate_highpass_filter_in(16, 120)
        assert result["frequency"][0][1] == pytest.approx(HIGHPASS_MIN, rel=0.01)
        assert result["filter_type"] == "highpass"

    def test_highpass_out_reverses(self):
        result = generate_highpass_filter_out(16, 120)
        assert result["frequency"][0][1] == pytest.approx(HIGHPASS_MAX, rel=0.01)
        assert result["frequency"][-1][1] == pytest.approx(HIGHPASS_MIN, rel=0.01)

    def test_dj_filter_negative_is_lowpass(self):
        result = generate_dj_filter_curve(16, 120, [-1.0, -0.5, 0.0, 0.5, 1.0])
        assert result["filter_types"][0] == "lowpass"
        assert result["filter_types"][2] == "bypass"
        assert result["filter_types"][4] == "highpass"

    def test_unknown_filter_raises(self):
        with pytest.raises(ValueError):
            generate_filter_transition("invalid", 16, 120)

    def test_combined_filter(self):
        result = generate_combined_filter("lowpass_in", "highpass_out", 16, 120)
        assert "deck_a" in result
        assert "deck_b" in result
        assert result["deck_a"]["filter_type"] == "lowpass"
        assert result["deck_b"]["filter_type"] == "highpass"
