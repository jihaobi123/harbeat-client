from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.modules.library.background_tasks import apply_stem_analysis


def test_stem_analysis_persists_pre_style_features_without_overwriting_dj_features() -> None:
    feature_analysis = {
        "version": "pre_style_evidence_v3",
        "status": "ready",
        "selected_models": ["drum-model"],
    }
    result = {
        "stem_activity": {},
        "stem_activity_windows": [],
        "stem_quality_score": 0.9,
        "stem_quality_profile": {},
        "drum_analysis": {"version": "drum_transcription_consensus_v2"},
        "feature_analysis": feature_analysis,
        "intro_is_clean": False,
        "outro_is_clean": False,
        "intro_clean_score": 0.0,
        "outro_clean_score": 0.0,
        "has_drum_loop": False,
    }
    song = SimpleNamespace(
        stems={"drums": "drums.wav"},
        source_path="song.wav",
        bpm=120.0,
        beat_points=[],
        downbeats=[],
        vocal_events=[],
        transition_windows=[],
        music_features={"dj": {"bpm": 120.0}},
    )

    with (
        patch("app.modules.library.stem_analysis.analyze_stem_files", return_value=result),
        patch(
            "app.modules.library.high_frequency_style_classifier.classify_high_frequency_styles",
            return_value={"version": "high_frequency_style_analysis_v1", "top_styles": []},
        ),
        patch("app.modules.library.background_tasks.apply_dancefloor_profile"),
    ):
        apply_stem_analysis(song)

    assert song.music_features["dj"] == {"bpm": 120.0}
    assert song.music_features["pre_style_features"] == feature_analysis
    assert song.music_features["high_frequency_styles"]["version"] == "high_frequency_style_analysis_v1"


def test_style_persistence_does_not_overwrite_dance_or_legacy_genre_results() -> None:
    from app.modules.library.background_tasks import apply_high_frequency_style_analysis

    song = SimpleNamespace(
        music_features={"dj": {"bpm": 128}, "pre_style_features": {"version": "v3"}},
        dance_styles=[{"style": "hiphop"}],
        genre_profile={"primary_genre": "hip-hop"},
    )
    classified = {"version": "high_frequency_style_analysis_v1", "top_styles": [{"style_id": "boombap"}]}
    with patch(
        "app.modules.library.high_frequency_style_classifier.classify_high_frequency_styles",
        return_value=classified,
    ):
        result = apply_high_frequency_style_analysis(song)

    assert result == classified
    assert song.music_features["dj"] == {"bpm": 128}
    assert song.dance_styles == [{"style": "hiphop"}]
    assert song.genre_profile == {"primary_genre": "hip-hop"}
