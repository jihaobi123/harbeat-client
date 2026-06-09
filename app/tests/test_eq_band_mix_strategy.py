from types import SimpleNamespace

from app.modules.dj_control.eq_transition_strategy import plan_eq_band_mix_transition


def song(**overrides):
    base = dict(
        id="song-a",
        title="A",
        artist="Artist",
        duration=180.0,
        bpm=96.0,
        camelot_key="8A",
        energy=0.65,
        music_features={},
        beat_points=[0.0, 0.625, 1.25, 1.875],
        downbeats=[0.0, 2.5, 5.0],
        phrase_map=[{"start_sec": 0.0}, {"start_sec": 10.0}, {"start_sec": 20.0}],
        cue_points=[],
        vocal_events=[],
        bass_risk_windows=[],
        transition_windows=[],
        intro_is_clean=True,
        outro_is_clean=True,
        has_drum_loop=True,
        loudness_profile={},
        stem_activity={},
        genre_profile={},
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_eq_band_mix_plan_contains_deck_curves_and_fallback_fields():
    prev = song(id="prev", energy=0.7)
    nxt = song(id="next", bpm=98.0, energy=0.82, camelot_key="8A")

    plan = plan_eq_band_mix_transition(
        prev,
        nxt,
        cursor_sec=42.0,
        eq_mix_user_mode="rhythm",
        target_style="hiphop",
    )

    assert plan["transition_mode"] == "eq_band_mix"
    assert plan["strategy"] == "hard_bass_swap"
    assert plan["target"]["song_id"] == "next"
    assert plan["deck_a"]["song_id"] == "prev"
    assert plan["deck_b"]["song_id"] == "next"
    assert plan["deck_a"]["eq"]["low"]
    assert plan["deck_b"]["fader"]
    assert plan["to_song_id"] == "next"
    assert plan["fade_sec"] > 0
    assert plan["fallback_style"]
    assert plan["safety"]["fallback_mode"] == "ordinary_xfade"


def test_eq_band_mix_user_mode_filter_forces_filter_strategy():
    prev = song(id="prev", bpm=90.0, camelot_key="1A")
    nxt = song(id="next", bpm=118.0, camelot_key="9B")

    plan = plan_eq_band_mix_transition(prev, nxt, cursor_sec=0.0, eq_mix_user_mode="filter")

    assert plan["strategy"] == "filter_sweep"
    assert plan["style"] == "filter"
    assert plan["deck_a"]["filter"]["type"] == "lowpass"
