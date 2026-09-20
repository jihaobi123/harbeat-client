from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import app
from app.modules.dj_control import cut_strategy
from app.modules.dj_control.schemas import CutPlanRequest


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
        dance_style_scores={"popping": 0.8, "locking": 0.2},
        genre_profile={},
        energy_curve=[],
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_target_style_selects_cached_high_confidence_candidate():
    current = song("current", 62, dance_style_scores={"hiphop": 0.9})
    ready = song(
        "ready",
        78,
        bpm=102.0,
        transition_windows=[{"start": 8.0, "end": 16.0}],
        dance_style_scores={"popping": 0.92, "locking": 0.1},
        genre_profile={
            "style_evidence_v1": {
                "popping": {
                    "final_score": 0.92,
                    "external_source_scores": {
                        "discogs": {"matched_labels": ["electro", "funk", "boogie"]},
                    },
                }
            }
        },
    )
    risky = song(
        "risky",
        76,
        bpm=135.0,
        dance_style_scores={"popping": 0.95},
        vocal_events=[1, 2, 3, 4],
        bass_risk_windows=[1, 2, 3, 4],
    )
    wrong_style = song("wrong", 80, dance_style_scores={"popping": 0.30, "locking": 0.9})

    plan = cut_strategy.plan_target_style_cut(
        current_song=current,
        cursor_sec=10.0,
        target_style="popping",
        active_queue=[risky],
        style_reserve_pool=[ready, wrong_style],
        current_style="hiphop",
        cached_song_ids={"ready"},
        prefer_cached=True,
    )

    assert plan["selected_song"]["song_id"] == "ready"
    assert plan["selected_song"]["cache_status"] == "ready"
    assert plan["fallback"] is False
    assert plan["recommended_transition_hint"] == "percussion_bridge"
    assert "electro" in plan["selected_song"]["matched_labels"]


def test_cut_plan_request_allows_target_style_without_strategy():
    payload = CutPlanRequest(
        intent="target_dance_style",
        current_song_id="current",
        target_style="popping",
        active_queue_song_ids=["a", "b"],
        style_reserve_pool_song_ids=["c"],
    )

    assert payload.strategy is None
    assert payload.intent == "target_dance_style"
    assert payload.target_style == "popping"


def test_validation_error_no_longer_requires_strategy_for_target_style_shape():
    client = TestClient(app)
    response = client.post(
        "/api/dj/cut/plan",
        json={
            "intent": "target_dance_style",
            "current_song_id": "current",
            "target_style": "popping",
            "active_queue_song_ids": ["a", "b"],
            "style_reserve_pool_song_ids": ["c"],
        },
    )

    assert response.status_code != 422
