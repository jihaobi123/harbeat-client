from pathlib import Path

from scripts.reanalyze_feature_test_library import render_report, stem_paths


def test_stem_paths_require_all_four_sources(tmp_path: Path) -> None:
    directory = tmp_path / "htdemucs" / "Song"
    directory.mkdir(parents=True)
    for name in ("vocals", "drums", "bass", "other"):
        (directory / f"{name}.wav").touch()
    assert set(stem_paths(tmp_path, "Song")) == {"vocals", "drums", "bass", "other"}


def test_report_counts_validation_states_without_style_claims() -> None:
    payload = {
        "updated_at": "now",
        "tracks": [{
            "title": "Song",
            "status": "completed",
            "stem_analysis": {"feature_analysis": {
                "status": "ready",
                "validation_summary": {"counts": {
                    "validated": 5, "failed_validation": 8,
                    "provisional": 20, "candidate_only": 10,
                }},
                "selected_models": ["adtof"],
            }},
            "feature_inventory": [],
        }],
    }
    report = render_report(payload)
    assert "| 5 | 8 | 30 | adtof |" in report
    assert "本报告只检查特征层" in report


def test_report_lists_validated_auxiliary_measurements() -> None:
    payload = {
        "updated_at": "now",
        "tracks": [{
            "title": "Song",
            "status": "completed",
            "stem_analysis": {"feature_analysis": {
                "status": "ready",
                "validation_summary": {"counts": {"validated": 1}},
                "selected_models": [],
            }},
            "feature_inventory": [{
                "path": "vocal_delivery.pitch_sustain_ratio",
                "score": 0.72,
                "probability": None,
                "decision": "measured",
                "validation_status": "validated",
                "style_required_allowed": False,
                "reliability": 0.8,
            }],
        }],
    }
    report = render_report(payload)
    assert "pitch_sustain_ratio" in report
    assert "连续测量证据" in report
