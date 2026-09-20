from __future__ import annotations

import json
import os
import tempfile

import numpy as np
import soundfile as sf

from app.modules.library.feature_review_artifacts import render_review_clips, render_review_html
from app.modules.library.feature_validation import ReviewPolicy, minimize_review_queue, triage_track_features
from app.modules.library.style_feature_evidence import unavailable_feature


def _feature(
    score: float,
    *,
    detected: bool,
    confidence: float,
    source_type: str,
    time_ranges: list[dict] | None = None,
    evidence: dict | None = None,
) -> dict:
    return {
        "availability": "available",
        "detected": detected,
        "score": score,
        "decision_threshold": 0.55,
        "confidence": confidence,
        "analysis_method": source_type,
        "sources": ["test"],
        "time_ranges": time_ranges or [],
        "evidence": {"source_type": source_type, **(evidence or {})},
    }


def test_triage_only_requests_risky_or_borderline_features() -> None:
    analysis = {"feature_groups": {
        "rhythm_grammar": {
            "four_on_floor": _feature(
                0.92, detected=True, confidence=0.93, source_type="deterministic_grid",
                evidence={"bars_analyzed": 32},
            ),
            "dembow": _feature(0.53, detected=False, confidence=0.51, source_type="deterministic_grid"),
        },
        "low_frequency": {
            "log_drum": _feature(
                0.67, detected=True, confidence=0.7, source_type="spectral_decay_proxy_v1",
                time_ranges=[{"start": 12.0, "end": 12.2}],
            ),
        },
        "percussion_timbre": {},
        "production": {
            "brightness": _feature(0.9, detected=True, confidence=0.9, source_type="dsp_fallback"),
        },
    }}
    result = triage_track_features(
        track_id="track-a", title="Track A", duration=120.0,
        feature_analysis=analysis, policy=ReviewPolicy(audit_percent=0.0),
    )

    reviewed = {(item["feature"], tuple(item["reasons"])) for item in result["manual_review"]}
    assert any(name == "log_drum" and "semantic_class_uses_proxy" in reasons for name, reasons in reviewed)
    assert any(name == "dembow" and "near_decision_threshold" in reasons for name, reasons in reviewed)
    assert {item["feature"] for item in result["auto_accept"]} == {"four_on_floor", "brightness"}


def test_sliding_808_candidate_remains_human_auditable() -> None:
    analysis = {"feature_groups": {
        "rhythm_grammar": {},
        "low_frequency": {
            "sliding_808": _feature(
                0.94,
                detected=True,
                confidence=0.95,
                source_type="bass_stft_event_fusion_v1",
                time_ranges=[{"start": 12.0, "end": 12.8}],
                evidence={"sub_808_identity_score": 0.9, "bass_slide_score": 0.94},
            ),
        },
        "percussion_timbre": {},
        "production": {},
    }}
    result = triage_track_features(
        track_id="track-a", title="Track A", duration=120.0,
        feature_analysis=analysis, policy=ReviewPolicy(audit_percent=0.0),
    )

    assert result["manual_review"][0]["feature"] == "sliding_808"
    assert "semantic_class_uses_proxy" in result["manual_review"][0]["reasons"]


def test_unavailable_v3_feature_is_not_counted_as_negative() -> None:
    analysis = {"feature_groups": {"low_frequency": {
        "sub_808": unavailable_feature(
            "bass_stem_unavailable",
            sources=["bass_stem"],
            analysis_method="bass_stft_event_fusion_v1",
        ),
    }}}

    result = triage_track_features(
        track_id="track-a", title="Track A", duration=120.0,
        feature_analysis=analysis, policy=ReviewPolicy(audit_percent=0.0),
    )

    assert result["auto_negative"] == []
    assert result["unavailable"][0]["feature"] == "sub_808"


def test_queue_limits_review_per_track_and_feature() -> None:
    tracks = []
    for track_index in range(4):
        tracks.append({
            "manual_review": [
                {
                    "review_id": f"t{track_index}:low_frequency:log_drum:0",
                    "track_id": f"t{track_index}",
                    "feature": "log_drum",
                    "priority": 0.9 - track_index * 0.01,
                },
                {
                    "review_id": f"t{track_index}:low_frequency:sub_808:0",
                    "track_id": f"t{track_index}",
                    "feature": "sub_808",
                    "priority": 0.8 - track_index * 0.01,
                },
            ],
            "auto_accept": [],
            "auto_negative": [],
        })
    queue = minimize_review_queue(
        tracks,
        policy=ReviewPolicy(max_items=3, max_items_per_track=1, max_items_per_feature=2),
    )

    assert queue["summary"]["manual_selected_count"] == 3
    assert len({item["track_id"] for item in queue["review_items"]}) == 3
    assert sum(item["feature"] == "log_drum" for item in queue["review_items"]) == 2


def test_queue_only_asks_once_per_track_feature() -> None:
    track = {
        "manual_review": [
            {
                "review_id": f"t1:low_frequency:log_drum:{index}",
                "track_id": "t1",
                "feature": "log_drum",
                "priority": 0.9 - index * 0.01,
            }
            for index in range(3)
        ],
        "auto_accept": [],
        "auto_negative": [],
    }
    queue = minimize_review_queue([track], policy=ReviewPolicy(max_items=3))

    assert queue["summary"]["manual_selected_count"] == 1


def test_review_artifacts_render_audio_and_exportable_html() -> None:
    with tempfile.TemporaryDirectory() as directory:
        sr = 8000
        t = np.arange(sr * 3) / sr
        audio = (0.2 * np.sin(2 * np.pi * 120 * t)).astype(np.float32)
        source = os.path.join(directory, "source.wav")
        bass = os.path.join(directory, "bass.wav")
        sf.write(source, audio, sr)
        sf.write(bass, audio, sr)
        queue = {
            "review_items": [{
                "review_id": "track-a:low_frequency:log_drum:0",
                "track_id": "track-a",
                "title": "Track A",
                "group": "low_frequency",
                "feature": "log_drum",
                "predicted": True,
                "score": 0.62,
                "confidence": 0.6,
                "source_type": "dsp_fallback",
                "reasons": ["semantic_class_uses_proxy"],
                "time_range": {"start": 0.0, "end": 2.0},
                "options": ["log_drum", "other_bass", "uncertain"],
            }],
            "summary": {},
        }
        output = os.path.join(directory, "review")
        os.makedirs(os.path.join(output, "clips"), exist_ok=True)
        stale = os.path.join(output, "clips", "stale.wav")
        sf.write(stale, audio, sr)
        rendered = render_review_clips(
            queue, {"track-a": {"source": source, "bass": bass}}, output,
        )
        html_path = render_review_html(rendered, output)

        assert os.path.isfile(os.path.join(output, rendered["review_items"][0]["audio"]["context"]))
        assert os.path.isfile(os.path.join(output, rendered["review_items"][0]["audio"]["focus"]))
        assert not os.path.exists(stale)
        assert "导出审核结果 JSON" in html_path.read_text(encoding="utf-8")
        assert json.loads(open(os.path.join(output, "review_queue.json"), encoding="utf-8").read())["review_items"]
