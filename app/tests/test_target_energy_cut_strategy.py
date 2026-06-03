from types import SimpleNamespace

from app.modules.dj_control import cut_strategy


def song(song_id: str, energy: float, **overrides):
    base = dict(
        id=song_id,
        title=song_id,
        artist="Artist",
        energy=energy / 100.0,
        bpm=100.0,
        duration=180.0,
        beat_points=[],
        downbeats=[],
        phrase_map=[],
        cue_points=[],
        transition_windows=[],
        intro_clean_score=0.5,
        vocal_events=[],
        bass_risk_windows=[],
        stems={},
        dance_style_scores={"popping": 0.8},
        energy_curve=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_target_energy_exact_bucket_selects_matching_song():
    current = song("current", 62)
    a = song("a", 55)
    b = song("b", 76)
    c = song("c", 84)
    d = song("d", 96)

    plan = cut_strategy.plan_target_energy_cut(
        current_song=current,
        cursor_sec=10.0,
        active_queue=[a, b],
        reserve_pool=[c, d],
        target_min=80,
        target_max=90,
        current_style="popping",
        prefer_cached=False,
    )

    assert plan["selected_song"]["song_id"] == "c"
    assert plan["selected_song"]["energy_score"] == 84
    assert plan["fallback"] is False


def test_target_energy_lower_bucket_selects_matching_song():
    current = song("current", 62)
    e = song("e", 42)

    plan = cut_strategy.plan_target_energy_cut(
        current_song=current,
        cursor_sec=10.0,
        active_queue=[],
        reserve_pool=[e],
        target_min=40,
        target_max=50,
        current_style="popping",
        prefer_cached=False,
    )

    assert plan["selected_song"]["song_id"] == "e"
    assert plan["selected_song"]["bucket"] == "40-50"


def test_prefer_cached_can_choose_relaxed_cached_candidate():
    current = song("current", 62)
    b = song("b", 76)
    c = song("c", 84)

    plan = cut_strategy.plan_target_energy_cut(
        current_song=current,
        cursor_sec=10.0,
        active_queue=[b],
        reserve_pool=[c],
        target_min=80,
        target_max=90,
        current_style="popping",
        cached_song_ids={"b"},
        prefer_cached=True,
    )

    assert plan["selected_song"]["song_id"] == "b"
    assert plan["selected_song"]["cache_status"] == "ready"
    assert plan["fallback"] is True
    assert "放宽" in plan["fallback_reason"]


def test_cut_strategy_uses_unified_energy_profile(monkeypatch):
    calls = []

    def fake_profile(s):
        calls.append(s.id)
        return {
            "dance_energy_score": {"current": 62, "target": 84}[s.id],
            "score": {"current": 62, "target": 84}[s.id],
            "bucket": "80-90" if s.id == "target" else "60-70",
            "components": {},
            "curve": {},
            "source": "test",
        }

    monkeypatch.setattr(cut_strategy, "get_dance_energy_profile", fake_profile)

    plan = cut_strategy.plan_target_energy_cut(
        current_song=song("current", 0),
        cursor_sec=0.0,
        active_queue=[],
        reserve_pool=[song("target", 0)],
        target_min=80,
        target_max=90,
        prefer_cached=False,
    )

    assert plan["selected_song"]["song_id"] == "target"
    assert "current" in calls
    assert "target" in calls
