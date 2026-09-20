from types import SimpleNamespace

from app.modules.dj_control.energy_hiphop import energy_bucket, get_dance_energy_profile


def test_energy_bucket_boundaries():
    assert energy_bucket(0) == "0-10"
    assert energy_bucket(9.9) == "0-10"
    assert energy_bucket(10) == "10-20"
    assert energy_bucket(62) == "60-70"
    assert energy_bucket(100) == "90-100"
    assert energy_bucket(-1) == "0-10"
    assert energy_bucket(120) == "90-100"


def test_get_dance_energy_profile_falls_back_to_library_energy():
    song = SimpleNamespace(
        energy=0.62,
        bpm=None,
        beat_points=[],
        downbeats=[],
        phrase_map=[],
        duration=180.0,
        stems=None,
        energy_curve=[],
    )

    profile = get_dance_energy_profile(song)

    assert profile["dance_energy_score"] == 62
    assert profile["bucket"] == "60-70"
    assert profile["source"] == "fallback_library_energy"
