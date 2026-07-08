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


def test_exact_target_wins_before_relaxed_cached_candidate():
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

    assert plan["selected_song"]["song_id"] == "c"
    assert plan["selected_song"]["cache_status"] == "missing"
    assert plan["fallback"] is False
    assert plan["fallback_reason"] is None


def test_relaxes_bucket_only_when_exact_bucket_has_no_candidate():
    current = song("current", 62)
    b = song("b", 76)

    plan = cut_strategy.plan_target_energy_cut(
        current_song=current,
        cursor_sec=10.0,
        active_queue=[b],
        reserve_pool=[],
        target_min=80,
        target_max=90,
        current_style="popping",
        cached_song_ids={"b"},
        prefer_cached=True,
    )

    assert plan["selected_song"]["song_id"] == "b"
    assert plan["selected_song"]["cache_status"] == "ready"
    assert plan["fallback"] is True
    assert plan["fallback_reason"]


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


def test_target_energy_can_select_song_by_entry_segment_energy():
    current = song("current", 55)
    whole_match = song("whole", 82, phrase_map=[
        {"label": "intro", "start": 0.0, "end": 16.0, "energy": 0.52},
        {"label": "verse", "start": 16.0, "end": 48.0, "energy": 0.62},
    ])
    segment_match = song("segment", 68, phrase_map=[
        {"label": "intro", "start": 0.0, "end": 16.0, "energy": 0.84},
        {"label": "verse", "start": 16.0, "end": 48.0, "energy": 0.62},
    ])

    plan = cut_strategy.plan_target_energy_cut(
        current_song=current,
        cursor_sec=10.0,
        active_queue=[whole_match, segment_match],
        reserve_pool=[],
        target_min=80,
        target_max=90,
        current_style="popping",
        prefer_cached=False,
    )

    assert plan["selected_song"]["song_id"] == "segment"
    assert plan["selected_song"]["energy_score"] < 80
    assert plan["selected_song"]["segment_energy_score"] == 84
    assert plan["selected_song"]["entry_start_sec"] == 0.0
    assert plan["fallback"] is False
    assert plan["score_breakdown"]["segment_energy_match"] > plan["score_breakdown"]["song_energy_match"]


def test_target_energy_allows_vocal_covered_high_energy_segment():
    current = song("current", 55)
    vocal_drop = song("vocal_drop", 62, phrase_map=[
        {"label": "drop", "start": 32.0, "end": 48.0, "energy": 0.9},
        {"label": "break", "start": 56.0, "end": 72.0, "energy": 0.72},
    ], vocal_events=[{"start": 30.0, "end": 55.0, "confidence": 1.0}])
    clean_drop = song("clean_drop", 62, phrase_map=[
        {"label": "intro", "start": 0.0, "end": 16.0, "energy": 0.62},
        {"label": "verse", "start": 32.0, "end": 48.0, "energy": 0.80},
    ], vocal_events=[{"start": 90.0, "end": 110.0, "confidence": 1.0}])

    plan = cut_strategy.plan_target_energy_cut(
        current_song=current,
        cursor_sec=10.0,
        active_queue=[vocal_drop, clean_drop],
        reserve_pool=[],
        target_min=80,
        target_max=90,
        current_style="popping",
        prefer_cached=False,
    )

    assert plan["selected_song"]["song_id"] == "vocal_drop"
    assert plan["selected_song"]["entry_start_sec"] == 32.0
    assert plan["score_breakdown"]["segment_vocal_density"] > 0.0
    assert plan["score_breakdown"]["segment_single_vocal_allowed"] is True
