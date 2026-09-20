from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_ROOT = ROOT / "contracts" / "schemas" / "analysis"
FIXTURE_ROOT = ROOT / "contracts" / "fixtures" / "analysis"


def _read(name: str, root: Path) -> dict:
    return json.loads((root / name).read_text(encoding="utf-8"))


def test_same_style_contract_schemas_and_ready_fixtures_are_valid_json() -> None:
    for name in (
        "same-style-track-preprocess-v1.schema.json",
        "same-style-pair-score-v1.schema.json",
        "same-style-library-index-v1.schema.json",
    ):
        schema = _read(name, SCHEMA_ROOT)
        assert schema["$schema"].endswith("2020-12/schema")
        assert schema["additionalProperties"] is False

    track = _read("same-style-track-preprocess-v1.ready.json", FIXTURE_ROOT)
    pair = _read("same-style-pair-score-v1.ready.json", FIXTURE_ROOT)
    assert track["schema_version"] == "1.2.0"
    assert pair["schema_version"] == "1.0.0"


def test_track_fixture_uses_storage_keys_and_milliseconds() -> None:
    track = _read("same-style-track-preprocess-v1.ready.json", FIXTURE_ROOT)
    assets = [track["assets"]["master"], *track["assets"]["stems"].values()]
    assets.extend(
        value
        for key, value in track["assets"]["drum_stems"].items()
        if key != "status" and value is not None
    )
    for asset in assets:
        assert not asset["storage_key"].startswith("/")
        assert len(asset["sha256"]) == 64
        assert asset["duration_ms"] == track["source"]["duration_ms"]
    assert track["analysis"]["beat_grid"]["unit"] == "ms"
    assert all(
        isinstance(value, int)
        for value in track["analysis"]["beat_grid"]["beats_ms"]
    )


def test_pair_fixture_never_scores_style() -> None:
    pair = _read("same-style-pair-score-v1.ready.json", FIXTURE_ROOT)
    assert pair["scope"]["style_precondition"] == "caller_guaranteed_same_style"
    assert pair["scope"]["style_scoring_applied"] is False
    assert "style_score" not in pair["scores"]
