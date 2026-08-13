import math
import os
import sys
import types
from pathlib import Path

import numpy as np
import soundfile as sf


TEST_HOME = Path("/tmp/harbeat-engine-test-home")
(TEST_HOME / "cache").mkdir(parents=True, exist_ok=True)
(TEST_HOME / "samples").mkdir(parents=True, exist_ok=True)
os.environ["CYPHER_HOME"] = str(TEST_HOME)

sys.modules.setdefault("sounddevice", types.SimpleNamespace(query_devices=lambda *args, **kwargs: []))

from harbeat_audio_runtime.engine import AudioEngineMVP, Deck, STEM_AWARE_STYLES, SongCacheError  # noqa: E402
from harbeat_audio_runtime.mix_plan import Transition  # noqa: E402


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


def _scheduled_render_fixture(tmp_path: Path):
    render_dir = tmp_path / "pair"
    render_dir.mkdir(parents=True)
    render_path = render_dir / "transition_render.wav"
    audio = np.full((44100 * 2, 2), 0.2, dtype=np.float32)
    sf.write(render_path, audio, 44100)
    (render_dir / "transition_render_meta.json").write_text(
        '{"audio_feature_source":"dj_structure_precomputed_window_v2",'
        '"renderer_version":"three_band_default_v9_fast_phase_window",'
        '"render_strategy":"three_band_default"}',
        encoding="utf-8",
    )
    target_dir = TEST_HOME / "cache" / "next"
    target_dir.mkdir(parents=True, exist_ok=True)
    sf.write(target_dir / "original.wav", np.full((44100 * 20, 2), 0.3, dtype=np.float32), 44100)
    plan = {
        "pair_id": "fc-test",
        "from_song_id": "current",
        "to_song_id": "next",
        "from_at_sec": 5.0,
        "to_at_sec": 10.0,
        "resume_at_sec": 12.0,
        "duration_sec": 2.0,
        "audio_feature_source": "dj_structure_precomputed_window_v2",
        "renderer_version": "three_band_default_v9_fast_phase_window",
        "render_strategy": "three_band_default",
        "transition_render_path": str(render_path),
        "default_mix": {
            "pair_id": "fc-test",
            "from_song_id": "current",
            "to_song_id": "next",
            "from_at_sec": 5.0,
            "to_at_sec": 10.0,
            "resume_at_sec": 12.0,
            "audio_feature_source": "dj_structure_precomputed_window_v2",
            "renderer_version": "three_band_default_v9_fast_phase_window",
            "render_strategy": "three_band_default",
        },
    }
    return render_path, plan


def _playing_engine(position_sec: float = 1.0) -> AudioEngineMVP:
    engine = AudioEngineMVP()
    engine.deck_a.audio = np.full((44100 * 20, 2), 0.1, dtype=np.float32)
    engine.deck_a.song_id = "current"
    engine.deck_a.pos = int(position_sec * 44100)
    engine._active = "a"
    engine._playing = True
    engine._paused = False
    return engine


def test_scheduled_default_render_rejects_short_lead(tmp_path):
    _, plan = _scheduled_render_fixture(tmp_path)
    engine = _playing_engine(position_sec=4.0)

    try:
        engine.schedule_default_render(plan, to_song_id="next", min_lead_sec=1.5)
    except SongCacheError as exc:
        assert exc.code == 409
        assert "lead too short" in str(exc)
    else:
        raise AssertionError("short-lead schedule must be rejected")


def test_scheduled_default_render_triggers_on_local_sample_clock(tmp_path):
    _, plan = _scheduled_render_fixture(tmp_path)
    engine = _playing_engine(position_sec=1.0)
    result = engine.schedule_default_render(plan, to_song_id="next", min_lead_sec=1.5)

    assert result["action"] == "default_render_scheduled"
    engine.deck_a.pos = int(4.99 * 44100)
    out = np.zeros((2048, 2), dtype=np.float32)
    engine._callback(out, 2048, None, None)

    assert engine._last_transition_result["action"] == "default_render_playback"
    assert abs(engine._last_transition_result["trigger_error_ms"]) <= 1.0
    assert engine.active_deck.song_id == "next"
    assert np.max(np.abs(out)) > 0.0


def test_scheduled_default_render_resumes_without_zero_padding(tmp_path):
    _, plan = _scheduled_render_fixture(tmp_path)
    engine = _playing_engine(position_sec=1.0)
    engine.schedule_default_render(plan, to_song_id="next", min_lead_sec=1.5)
    engine.deck_a.pos = int(4.99 * 44100)
    first = np.zeros((2048, 2), dtype=np.float32)
    engine._callback(first, 2048, None, None)

    engine.active_deck.pos = len(engine.active_deck.audio) - 256
    out = np.zeros((2048, 2), dtype=np.float32)
    engine._callback(out, 2048, None, None)

    assert engine._last_transition_result["action"] == "default_render_resume"
    assert engine.active_deck.song_id == "next"
    assert np.min(np.abs(out[300:])) > 0.0


def test_prepared_default_render_uses_predecoded_decks_at_manual_trigger(tmp_path):
    _, plan = _scheduled_render_fixture(tmp_path)
    engine = _playing_engine(position_sec=1.0)

    prepared = engine.prepare_default_render(plan, to_song_id="next")

    assert prepared["action"] == "default_render_prepared"
    assert prepared["cached"] is False

    original_load = Deck.load

    def fail_if_redecoded(*args, **kwargs):
        raise AssertionError("manual trigger must use the prepared decks")

    Deck.load = fail_if_redecoded
    try:
        engine.deck_a.pos = int(4.99 * 44100)
        result = engine.default_render_playback(plan, to_song_id="next")
    finally:
        Deck.load = original_load

    assert result["action"] == "default_render_playback"
    assert result["preloaded"] is True
    assert engine._prepared_default_render is None
    assert engine._default_resume_after_render["resume_deck"].audio is not None


def test_scheduled_default_render_reuses_predecoded_decks(tmp_path):
    _, plan = _scheduled_render_fixture(tmp_path)
    engine = _playing_engine(position_sec=1.0)
    engine.prepare_default_render(plan, to_song_id="next")

    original_load = Deck.load

    def fail_if_redecoded(*args, **kwargs):
        raise AssertionError("scheduled transition must reuse prepared decks")

    Deck.load = fail_if_redecoded
    try:
        result = engine.schedule_default_render(plan, to_song_id="next", min_lead_sec=1.5)
    finally:
        Deck.load = original_load

    assert result["action"] == "default_render_scheduled"
    assert engine._prepared_default_render is None


def test_scheduled_default_render_accepts_verified_fast_cut_renderer(tmp_path):
    render_path, plan = _scheduled_render_fixture(tmp_path)
    fast_version = "three_band_default_v7_standalone_curve_no_energy_floor"
    plan["renderer_version"] = fast_version
    plan["default_mix"]["renderer_version"] = fast_version
    (render_path.parent / "transition_render_meta.json").write_text(
        '{"audio_feature_source":"dj_structure_precomputed_window_v2",'
        f'"renderer_version":"{fast_version}",'
        '"render_strategy":"three_band_default"}',
        encoding="utf-8",
    )
    engine = _playing_engine(position_sec=1.0)

    result = engine.schedule_default_render(plan, to_song_id="next", min_lead_sec=1.5)

    assert result["action"] == "default_render_scheduled"


def test_repeated_default_render_schedule_for_same_pair_is_idempotent(tmp_path):
    _, plan = _scheduled_render_fixture(tmp_path)
    engine = _playing_engine(position_sec=1.0)

    first = engine.schedule_default_render(plan, to_song_id="next", min_lead_sec=1.5)
    second = engine.schedule_default_render(plan, to_song_id="next", min_lead_sec=1.5)

    assert first["action"] == "default_render_scheduled"
    assert second["action"] == "default_render_scheduled"
    assert second["cached"] is True


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
