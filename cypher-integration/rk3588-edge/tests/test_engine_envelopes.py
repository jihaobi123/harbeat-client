import math
import os
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "audio-engine"))

TEST_HOME = Path("/tmp/harbeat-engine-test-home")
(TEST_HOME / "cache").mkdir(parents=True, exist_ok=True)
(TEST_HOME / "samples").mkdir(parents=True, exist_ok=True)
os.environ["CYPHER_HOME"] = str(TEST_HOME)

sys.modules.setdefault("sounddevice", types.SimpleNamespace(query_devices=lambda *args, **kwargs: []))

from engine import AudioEngineMVP, STEM_AWARE_STYLES  # noqa: E402
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


def test_vocal_handoff_cut_point_uses_transition_ratio_not_fixed_midpoint():
    before_a, before_b = AudioEngineMVP._style_envelopes("vocal_handoff", 0.519, vocal_handoff_ratio=0.52)
    after_a, after_b = AudioEngineMVP._style_envelopes("vocal_handoff", 0.521, vocal_handoff_ratio=0.52)

    assert math.isclose(before_a["vocals"], 1.0)
    assert math.isclose(before_b["vocals"], 0.0)
    assert math.isclose(after_a["vocals"], 0.0)
    assert math.isclose(after_b["vocals"], 1.0)


def test_playback_tier_reports_stem_aware_during_manual_stem_transition():
    engine = AudioEngineMVP()
    for deck in (engine.deck_a, engine.deck_b):
        deck.stems = {stem: object() for stem in ("vocals", "drums", "bass", "other")}
    engine._in_transition = True
    engine._plan_enabled = False

    assert engine._playback_tier() == "stem_aware"


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
