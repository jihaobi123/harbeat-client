import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.instrument_analysis.schemas import InstrumentAnalysisDocument


ROOT = Path(__file__).resolve().parents[2]


def ready_payload() -> dict:
    return {
        "schema_name": "harbeat.instrument_analysis",
        "schema_version": "0.1.0",
        "track_id": "track_001",
        "status": "ready",
        "duration_sec": 4.0,
        "timeline_fingerprint": "a" * 64,
        "taxonomy_version": "instrument_taxonomy@0.1.0",
        "models": {
            "adtof": {
                "model_id": "adtof-pytorch",
                "model_version": "upstream",
                "deployment_status": "shadow",
                "availability": "available",
                "checkpoint_sha256": "b" * 64,
                "source_revision": "c" * 40,
                "license_status": "review_required",
                "error": None,
            },
            "panns": {
                "model_id": "panns-cnn14",
                "model_version": "upstream",
                "deployment_status": "shadow",
                "availability": "available",
                "checkpoint_sha256": "d" * 64,
                "source_revision": "e" * 40,
                "license_status": "review_required",
                "error": None,
            },
        },
        "bars": [
            {
                "bar_index": 0,
                "start_sec": 0.0,
                "end_sec": 4.0,
                "drum_events": [
                    {
                        "time_sec": 1.0,
                        "drum_class": "kick",
                        "confidence": 0.9,
                        "bar_index": 0,
                        "beat_index_in_bar": 1,
                        "beat_position": 2.0,
                    }
                ],
                "drum_summary": {
                    "event_counts": {
                        "kick": 1,
                        "snare": 0,
                        "hihat": 0,
                        "tom": 0,
                        "cymbal": 0,
                    },
                    "density_per_sec": 0.25,
                },
                "instrument_probabilities": [
                    {
                        "instrument_class": "bass",
                        "mean_probability": 0.5,
                        "max_probability": 0.8,
                        "active_coverage": 0.5,
                    }
                ],
                "validation_status": "unreviewed",
            }
        ],
        "warnings": [],
    }


def test_ready_sidecar_requires_bar_results_and_provenance():
    payload = ready_payload()
    payload["bars"] = []
    with pytest.raises(ValidationError):
        InstrumentAnalysisDocument.model_validate(payload)


def test_classifier_status_is_shadow_only():
    payload = ready_payload()
    payload["models"]["panns"]["deployment_status"] = "production"
    with pytest.raises(ValidationError):
        InstrumentAnalysisDocument.model_validate(payload)


def test_bars_are_monotonic_and_events_fit_track_duration():
    payload = ready_payload()
    payload["bars"].append({**payload["bars"][0], "bar_index": 0})
    with pytest.raises(ValidationError):
        InstrumentAnalysisDocument.model_validate(payload)

    payload = ready_payload()
    payload["bars"][0]["drum_events"][0]["time_sec"] = 4.1
    with pytest.raises(ValidationError):
        InstrumentAnalysisDocument.model_validate(payload)


def test_model_manifest_v1_1_adds_shadow_without_mutating_v1():
    v1 = json.loads((ROOT / "schemas/music_analysis/model_manifest_v1.schema.json").read_text())
    v1_1 = json.loads(
        (ROOT / "schemas/music_analysis/model_manifest_v1_1.schema.json").read_text()
    )
    assert "shadow" not in v1["properties"]["status"]["enum"]
    assert "shadow" in v1_1["properties"]["status"]["enum"]
    assert v1_1["properties"]["schema_version"]["const"] == "1.1.0"


def test_fixture_matches_runtime_contract():
    payload = json.loads(
        (ROOT / "app/tests/fixtures/instrument-analysis-ready.json").read_text()
    )
    assert InstrumentAnalysisDocument.model_validate(payload).track_id == "track_001"
