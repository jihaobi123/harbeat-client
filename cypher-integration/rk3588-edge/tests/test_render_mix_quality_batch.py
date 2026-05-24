import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "audio-engine" / "scripts"))

from render_mix_quality import SR, render_batch_report  # noqa: E402


def _write_track(root: Path, song_id: str, freq: float) -> dict:
    track_dir = root / song_id
    track_dir.mkdir()
    t = np.linspace(0, 4.0, SR * 4, endpoint=False)
    base = np.column_stack([np.sin(2 * np.pi * freq * t), np.sin(2 * np.pi * freq * t)]).astype("float32") * 0.08
    stems = {}
    for idx, stem in enumerate(("vocals", "drums", "bass", "other")):
        path = track_dir / f"{stem}.wav"
        sf.write(path, base * (1.0 - idx * 0.12), SR)
        stems[stem] = {"path": str(path), "format": "wav"}
    original = track_dir / "original.wav"
    sf.write(original, base, SR)
    return {"original": {"path": str(original), "format": "wav"}, "stems": stems}


def test_render_batch_report_renders_transition_style_and_fallback(tmp_path):
    report = {
        "tracks": [
            {"song_id": "a", "files": _write_track(tmp_path, "a", 220.0)},
            {"song_id": "b", "files": _write_track(tmp_path, "b", 330.0)},
        ],
        "mix_plan": {
            "transitions": [
                {
                    "from_song": "a",
                    "to_song": "b",
                    "style": "vocal_handoff",
                    "fallback_style": "blend",
                    "from_at_sec": 0.0,
                    "to_at_sec": 0.0,
                    "fade_sec": 2.0,
                }
            ]
        },
    }
    report_path = tmp_path / "batch_report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    rendered = render_batch_report(report_path, tmp_path / "renders")

    styles = {item["style"] for item in rendered}
    assert styles == {"vocal_handoff", "blend"}
    assert all(Path(item["path"]).exists() for item in rendered)
    assert all(item["metrics"]["silence_ratio"] < 0.5 for item in rendered)
