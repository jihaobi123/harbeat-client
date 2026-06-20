import math
import os
import sys
import types
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "audio-engine"))

TEST_HOME = Path("/tmp/harbeat-engine-test-home")
(TEST_HOME / "cache").mkdir(parents=True, exist_ok=True)
(TEST_HOME / "samples").mkdir(parents=True, exist_ok=True)
os.environ["CYPHER_HOME"] = str(TEST_HOME)

sys.modules.setdefault("sounddevice", types.SimpleNamespace(query_devices=lambda *args, **kwargs: []))

from engine import AudioEngineMVP, Deck, STEM_AWARE_STYLES  # noqa: E402
from mix_plan import Transition  # noqa: E402


def test_stem_aware_envelopes_have_no_silent_holes_or_double_bass_overload():
    for style in sorted(STEM_AWARE_STYLES | {"echo_freeze"}):
        for step in range(101):
            progress = step / 100.0
            a_gains, b_gains = AudioEngineMVP._style_envelopes(style, progress)
            for gain in (*a_gains.values(), *b_gains.values()):
                assert -1e-6 <= float(gain) <= 1.0 + 1e-6
            assert max(a_gains.values() or [0.0]) + max(b_gains.values() or [0.0]) > 0.0
            bass_sum = float(a_gains.get("bass", a_gains.get("full", 0.0))) + float(
                b_gains.get("bass", b_gains.get("full", 0.0))
            )
            assert bass_sum <= 1.65


def test_vocal_handoff_uses_transition_ratio_without_a_hard_vocal_cut():
    before_a, before_b = AudioEngineMVP._style_envelopes("vocal_handoff", 0.519, vocal_handoff_ratio=0.52)
    after_a, after_b = AudioEngineMVP._style_envelopes("vocal_handoff", 0.521, vocal_handoff_ratio=0.52)

    assert before_a["vocals"] > before_b["vocals"]
    assert after_b["vocals"] > after_a["vocals"]
    assert abs(after_a["vocals"] - before_a["vocals"]) < 0.12
    assert abs(after_b["vocals"] - before_b["vocals"]) < 0.12


def test_vocal_handoff_keeps_instrumental_bed_throughout_transition():
    previous = None
    for step in range(101):
        a, b = AudioEngineMVP._style_envelopes("vocal_handoff", step / 100.0, vocal_handoff_ratio=0.52)
        bed = a["drums"] + a["bass"] + a["other"] + b["drums"] + b["bass"] + b["other"]
        assert bed >= 0.95
        if previous is not None:
            assert max(abs(a[k] - previous[0][k]) for k in ("vocals", "drums", "bass", "other")) < 0.16
            assert max(abs(b[k] - previous[1][k]) for k in ("vocals", "drums", "bass", "other")) < 0.16
        previous = (a, b)


def test_playback_tier_reports_stem_aware_during_manual_stem_transition():
    engine = AudioEngineMVP()
    for deck in (engine.deck_a, engine.deck_b):
        deck.stems = {stem: object() for stem in ("vocals", "drums", "bass", "other")}
    engine._in_transition = True
    engine._plan_enabled = False

    assert engine._playback_tier() == "stem_aware"


def test_manual_filter_and_loudness_norm_update_active_deck_state():
    engine = AudioEngineMVP()

    filter_result = engine.apply_filter("active", "highpass", 900.0, q=0.9)
    loudness_result = engine.apply_loudness_norm("active", gain_db=-3.0, target_lufs=-14.0)

    assert filter_result["ok"] is True
    assert filter_result["deck"] == "a"
    assert filter_result["filter_type"] == "highpass"
    assert math.isclose(engine.active_deck.filter_cutoff_hz, 900.0)
    assert loudness_result["ok"] is True
    assert math.isclose(loudness_result["gain_db"], -3.0, abs_tol=0.05)
    assert math.isclose(engine.active_deck.gain, 10.0 ** (-3.0 / 20.0))


def test_eq_clamp_allows_spotify_style_deep_kill_values():
    deck = Deck()

    low, mid, hi = deck.set_eq(-60.0, -60.0, -60.0)

    assert low == -36.0
    assert mid == -24.0
    assert hi == -24.0


def test_eq_band_fader_uses_equal_power_shape():
    assert math.isclose(AudioEngineMVP._eq_band_equal_power_fader(0.0), 0.0)
    assert math.isclose(AudioEngineMVP._eq_band_equal_power_fader(1.0), 1.0)
    assert AudioEngineMVP._eq_band_equal_power_fader(0.5) > 0.5


def test_eq_band_full_band_unity_preserves_dry_signal():
    engine = AudioEngineMVP()
    deck = Deck()
    src = np.linspace(-0.5, 0.5, 2048, dtype=np.float32)
    deck.audio = np.column_stack([src, src[::-1]]).astype(np.float32)
    deck.pos = 0
    plan = {
        "fader": [[0.0, 1.0]],
        "eq": {
            "low": [[0.0, 0.0]],
            "mid": [[0.0, 0.0]],
            "high": [[0.0, 0.0]],
        },
    }

    out = engine._read_eq_band_deck(deck, plan, 0.0, 1024, "a")

    np.testing.assert_allclose(out, deck.audio[:1024], atol=1e-6)


def test_eq_band_transition_resets_limiter_gain():
    engine = AudioEngineMVP()
    engine._lim_gain = 0.25
    tr = Transition("a", "b", 0.0, 0.0, 16.0, style="eq_band_mix")

    engine._start_transition_locked(tr)

    assert engine._lim_gain == 1.0


def test_transition_handoff_ratio_prefers_metadata_then_beat_grid():
    engine = AudioEngineMVP()
    explicit = Transition("a", "b", 10.0, 20.0, 20.0, style="vocal_handoff", vocal_handoff_ratio=0.53)
    assert math.isclose(engine._transition_handoff_ratio(explicit), 0.53)

    engine.load_plan(
        {
            "tracks": [
                {"song_id": "a", "order": 0},
                {"song_id": "b", "order": 1, "beats": [20.0, 26.4, 29.6, 32.8]},
            ],
            "transitions": [
                {
                    "from_song": "a",
                    "to_song": "b",
                    "from_at_sec": 10.0,
                    "to_at_sec": 20.0,
                    "fade_sec": 20.0,
                    "style": "vocal_handoff",
                }
            ],
        }
    )
    inferred = engine._transition_handoff_ratio(engine._plan.transitions[0])

    assert math.isclose(inferred, 0.48)
