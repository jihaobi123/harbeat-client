import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_envelope_runner():
    from harbeat_audio_runtime import envelope_runner
    return envelope_runner


def test_eval_deck_interpolates_fader_eq_and_filter():
    runner = _load_envelope_runner()
    deck = {
        "fader": [[0, 0.0], [8, 1.0]],
        "eq": {
            "low": [[0, -24], [8, 0]],
            "mid": [[0, -12], [8, 0]],
            "high": [[0, -6], [8, 0]],
        },
        "filter": {"type": "highpass", "cutoff_hz": [[0, 900], [8, 30]]},
    }

    params = runner.eval_deck(deck, 4.0)

    assert params["fader"] == 0.5
    assert params["low_db"] == -12.0
    assert params["mid_db"] == -6.0
    assert params["hi_db"] == -3.0
    assert params["filter"]["type"] == "highpass"
    assert 450 < params["filter"]["cutoff_hz"] < 500
