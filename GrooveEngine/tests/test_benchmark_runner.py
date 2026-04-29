from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.benchmark_runner import _row_from_pair, fixed_benchmark_cases


def test_fixed_benchmark_cases_cover_required_categories() -> None:
    cases = fixed_benchmark_cases()
    names = {case["case_name"] for case in cases}

    assert "same_bpm" in names
    assert "near_bpm" in names
    assert "medium_bpm_delta" in names
    assert "long_overlap_case" in names
    assert "short_transition_case" in names


def test_benchmark_pair_row_exports_sync_fields() -> None:
    row = _row_from_pair(
        {
            "pair": ["track_a.groove.json", "track_b.groove.json"],
            "params": {"overlap_beats": 32},
            "summary": {
                "score": 0.75,
                "strategy": "clean_blend",
                "handoff_profile": "smooth_blend",
                "target_bpm": 101.0,
                "overlap_beats": 32,
                "render_anchor_delta_beats": 0.5,
                "render_phase_offset_applied": 0.25,
                "render_effective_phase_correction_beats": 0.25,
                "render_phase_error_estimate": 0.12,
                "render_drift_risk": 0.63,
                "render_long_blend_safe": False,
                "render_long_overlap_safe": False,
                "render_recommended_max_overlap_beats": 16,
                "render_sync_warning_count": 2,
                "render_peak_db": -1.0,
                "render_rms_db": -12.0,
                "render_headroom_db": 1.0,
                "render_spectral_conflict": 0.35,
                "render_loudness_delta_db": 2.0,
                "render_trace_blocks": 8,
                "notes": [
                    "Requested overlap 32 exceeds recommended safe max 16.",
                    "Drift risk is elevated for this render (0.63).",
                ],
            },
            "artifact_path": "artifact.json",
            "wav_path": "render.wav",
        }
    )

    assert row["render_anchor_delta_beats"] == 0.5
    assert row["render_phase_offset_applied"] == 0.25
    assert row["render_effective_phase_correction_beats"] == 0.25
    assert row["render_phase_error_estimate"] == 0.12
    assert row["render_drift_risk"] == 0.63
    assert row["render_long_blend_safe"] is False
    assert row["render_long_overlap_safe"] is False
    assert row["render_recommended_max_overlap_beats"] == 16
    assert row["sync_warning_count"] == 2
    assert "overlap" in row["sync_warning_summary"].lower()
