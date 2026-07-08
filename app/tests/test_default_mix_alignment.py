from types import SimpleNamespace

from app.modules.dj_control.default_mix.playlist_selector import plan_default_sequence
from app.modules.dj_control.default_mix.transition_planner import plan_default_transition


def _song(
    song_id: str,
    *,
    bpm: float = 96.0,
    camelot: str = "9A",
    energy: float = 0.35,
    duration: float = 240.0,
    transition_start: float = 172.0,
    entry_start: float = 8.0,
):
    beat = 60.0 / bpm
    beats = [round(i * beat, 3) for i in range(int(duration / beat))]
    downbeats = beats[::4]
    return SimpleNamespace(
        id=song_id,
        title=song_id,
        artist="artist",
        bpm=bpm,
        camelot_key=camelot,
        key=camelot,
        energy=energy,
        duration=duration,
        beat_points=beats,
        downbeats=downbeats,
        energy_curve=[{"time": i * 8.0, "energy": energy} for i in range(int(duration / 8))],
        transition_windows=[
            {
                "start": transition_start,
                "end": transition_start + 12.0,
                "mix_score": 0.8,
                "entry_start_sec": entry_start,
                "entry_score": 0.7,
            }
        ],
        stem_activity_windows=[],
        vocal_events=[],
        music_features={"dj": {"low_ratio": 0.4, "mid_ratio": 0.32, "high_ratio": 0.28}},
        genre_profile={"vocal_density": 0.28},
        loudness_profile={},
        source_path="",
    )


def test_default_sequence_filters_bpm_incompatible_candidate():
    songs = [
        _song("steady_a", bpm=95.0, camelot="9A", energy=0.34),
        _song("steady_b", bpm=96.0, camelot="9A", energy=0.35),
        _song("far_bpm", bpm=122.0, camelot="1A", energy=0.7),
    ]

    result = plan_default_sequence(songs)

    ordered_ids = [entry["song_id"] for entry in result["sequence"]]
    assert ordered_ids == ["steady_b", "steady_a"]
    assert all(pair["bpm_score"] > 0.0 for pair in result["pair_scores"])


def test_default_transition_scores_regions_then_aligns_to_grid():
    prev = _song("prev", bpm=96.0, transition_start=173.2)
    nxt = _song("next", bpm=96.0, entry_start=7.9)

    plan = plan_default_transition(prev, nxt)
    meta = plan["default_mix"]

    assert plan["transition_mode"] == "default_mix"
    assert plan["execution_mode"] == "default_render_playback"
    assert meta["source"] == "default_mix_v2_scored_alignment"
    assert meta["cut_point_policy"]["transition_windows_role"] == "candidate_regions_only"
    assert meta["exit_candidate"]["score"] > 0.0
    assert meta["entry_candidate"]["score"] > 0.0
    assert meta["alignment"]["from_anchor"] in {"downbeat", "beat", "raw"}
    assert meta["alignment"]["to_anchor"] in {"downbeat", "beat", "raw"}
    assert 171.2 <= plan["from_at_sec"] <= 186.7
    assert 2.0 <= plan["to_at_sec"] <= 12.0
