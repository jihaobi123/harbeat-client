from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.library.background_tasks import (
    ANALYSIS_STAGE_KEYS,
    REQUIRED_CORE_ANALYSIS_VERSION,
    queue_song_analysis,
    run_analysis_and_separation,
)


class _FakeDb:
    def __init__(self, song):
        self.song = song
        self.commits = 0

    def get(self, _model, song_id):
        return self.song if song_id == self.song.id else None

    def add(self, _song):
        pass

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def _song(source_path: str):
    return SimpleNamespace(
        id="song-1",
        source_path=source_path,
        bpm=120.0,
        key="A minor",
        beat_points=[0.0, 0.5],
        cue_points=[{"time": 0.0}],
        transition_windows=[{"start": 0.0, "end": 8.0}],
        music_features={"dj": {"bpm": 120.0}},
        beat_confidence_details={"core_analysis_version": REQUIRED_CORE_ANALYSIS_VERSION},
        analysis_status="none",
        stems=None,
    )


def test_queue_song_analysis_preserves_features_and_initializes_all_stages(tmp_path: Path) -> None:
    song = _song(str(tmp_path / "song.wav"))

    queue_song_analysis(song)

    assert song.analysis_status == "pending"
    assert song.music_features["dj"] == {"bpm": 120.0}
    pipeline = song.music_features["analysis_pipeline"]
    assert pipeline["version"] == "song_analysis_pipeline_v1"
    assert pipeline["status"] == "pending"
    assert set(pipeline["stages"]) == set(ANALYSIS_STAGE_KEYS)
    assert {item["status"] for item in pipeline["stages"].values()} == {"pending"}


def test_full_pipeline_commits_each_stage_and_finishes_completed(tmp_path: Path) -> None:
    source_dir = tmp_path / "uploads" / "1"
    source_dir.mkdir(parents=True)
    source_path = source_dir / "song.wav"
    source_path.touch()
    stems_dir = tmp_path / "uploads" / "stems" / "htdemucs" / "song"
    stems_dir.mkdir(parents=True)
    for stem in ("vocals", "drums", "bass", "other"):
        (stems_dir / f"{stem}.wav").touch()

    song = _song(str(source_path))
    queue_song_analysis(song)
    db = _FakeDb(song)

    def fake_feature_analysis(target, *, classify_styles=True):
        assert classify_styles is False
        features = dict(target.music_features)
        features["pre_style_features"] = {"version": "pre_style_evidence_v3"}
        target.music_features = features

    def fake_style_analysis(target):
        features = dict(target.music_features)
        features["high_frequency_styles"] = {"version": "high_frequency_style_analysis_v1"}
        target.music_features = features
        return features["high_frequency_styles"]

    with (
        patch("app.modules.library.background_tasks.SessionLocal", return_value=db),
        patch("app.modules.library.background_tasks.apply_stem_analysis", side_effect=fake_feature_analysis),
        patch("app.modules.library.background_tasks.apply_high_frequency_style_analysis", side_effect=fake_style_analysis),
        patch("app.modules.library.background_tasks.apply_dj_fingerprint"),
        patch("app.modules.library.external_metadata.run_enrich_song_external_metadata"),
    ):
        run_analysis_and_separation(song.id)

    stages = song.music_features["analysis_pipeline"]["stages"]
    assert song.analysis_status == "completed"
    assert all(stages[name]["status"] == "completed" for name in ANALYSIS_STAGE_KEYS)
    assert song.music_features["pre_style_features"]["version"] == "pre_style_evidence_v3"
    assert song.music_features["high_frequency_styles"]["version"] == "high_frequency_style_analysis_v1"
    assert db.commits >= 8


def test_stem_failure_keeps_core_result_and_finishes_partial(tmp_path: Path) -> None:
    source_path = tmp_path / "song.wav"
    source_path.touch()
    song = _song(str(source_path))
    queue_song_analysis(song)
    db = _FakeDb(song)

    with (
        patch("app.modules.library.background_tasks.SessionLocal", return_value=db),
        patch("app.modules.library.background_tasks.subprocess.run", side_effect=subprocess.CalledProcessError(1, "demucs")),
        patch("app.modules.library.background_tasks.apply_dj_fingerprint"),
        patch("app.modules.library.external_metadata.run_enrich_song_external_metadata"),
    ):
        run_analysis_and_separation(song.id)

    stages = song.music_features["analysis_pipeline"]["stages"]
    assert song.analysis_status == "partial"
    assert stages["core"]["status"] == "completed"
    assert stages["stem_separation"]["status"] == "error"
    assert stages["feature_analysis"]["status"] == "blocked"
    assert stages["style_analysis"]["status"] == "blocked"


def test_missing_audio_file_finishes_error_instead_of_staying_pending(tmp_path: Path) -> None:
    song = _song(str(tmp_path / "missing.wav"))
    queue_song_analysis(song)
    db = _FakeDb(song)

    with patch("app.modules.library.background_tasks.SessionLocal", return_value=db):
        run_analysis_and_separation(song.id)

    stages = song.music_features["analysis_pipeline"]["stages"]
    assert song.analysis_status == "error"
    assert stages["core"]["status"] == "error"
    assert stages["stem_separation"]["status"] == "blocked"
