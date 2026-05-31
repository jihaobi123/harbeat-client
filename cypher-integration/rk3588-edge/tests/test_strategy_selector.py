import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "audio-engine"))

from strategy_selector import select_preset  # noqa: E402


def _song(**overrides):
    data = {
        "camelot": 4,
        "energy": 0.72,
        "bpm": 93.0,
        "segments": [
            {
                "start": 140.0,
                "end": 170.0,
                "label": "Chorus",
                "stem_activity": {
                    "vocals": 1.0,
                    "drums": 0.95,
                    "bass": 0.95,
                    "other": 0.9,
                },
            }
        ],
    }
    data.update(overrides)
    return data


def test_stem_aware_selector_prefers_vocal_handoff_for_double_vocal_overlap():
    a = _song()
    b = _song(
        camelot=5,
        energy=0.68,
        bpm=90.0,
        segments=[
            {
                "start": 32.0,
                "end": 54.0,
                "label": "Verse",
                "stem_activity": {
                    "vocals": 0.96,
                    "drums": 0.72,
                    "bass": 0.70,
                    "other": 0.65,
                },
            }
        ],
    )

    result = select_preset(a, b, 144.615, 165.26, 32.16, stems_available=True)

    assert result["selected"] == "vocal_handoff"
    assert result["risks"]["double_vocal_risk"] >= 0.8
    assert result["compatibility"]["bpm_quality"] in {"comfortable", "wide"}


def test_selector_never_returns_stem_aware_style_without_complete_stems():
    a = _song(camelot=4, bpm=93.0)
    b = _song(camelot=10, bpm=83.3)

    result = select_preset(a, b, 144.615, 165.26, 32.16, stems_available=False)

    stem_presets = {
        "vocal_handoff",
        "bass_swap",
        "drum_swap",
        "vocal_ducking",
        "instrumental_only",
        "vocal_solo_intro",
    }
    assert result["selected"] not in stem_presets
    assert result["fallback"] == result["selected"]
