from app.modules.library.bar_timeline import TimelineError, build_bar_timeline


def test_builds_half_open_bars_from_downbeats():
    timeline = build_bar_timeline(
        downbeats=[0.0, 2.0, 4.0, 6.0],
        beat_points=[i * 0.5 for i in range(16)],
        duration=7.0,
        time_signature={"numerator": 4, "denominator": 4, "confidence": 0.9},
        beat_confidence=0.9,
        beat_needs_review=False,
    )

    assert timeline.source == "downbeats"
    assert [
        (bar.index, bar.start_sec, bar.end_sec, bar.is_partial)
        for bar in timeline.bars
    ] == [
        (0, 0.0, 2.0, False),
        (1, 2.0, 4.0, False),
        (2, 4.0, 6.0, False),
        (3, 6.0, 7.0, True),
    ]


def test_rejects_timeline_marked_for_review():
    try:
        build_bar_timeline(
            downbeats=[0.0, 2.0],
            beat_points=[],
            duration=4.0,
            time_signature={"numerator": 4},
            beat_confidence=0.9,
            beat_needs_review=True,
        )
    except TimelineError as exc:
        assert exc.code == "timeline_needs_review"
    else:
        raise AssertionError("expected TimelineError")


def test_falls_back_to_confident_beat_grid():
    timeline = build_bar_timeline(
        downbeats=[],
        beat_points=[i * 0.5 for i in range(13)],
        duration=6.5,
        time_signature={"numerator": 4, "denominator": 4, "confidence": 0.95},
        beat_confidence=0.92,
        beat_needs_review=False,
    )

    assert timeline.source == "beat_grid"
    assert [bar.start_sec for bar in timeline.bars] == [0.0, 2.0, 4.0, 6.0]


def test_rejects_untrusted_beat_grid_fallback():
    try:
        build_bar_timeline(
            downbeats=[],
            beat_points=[0.0, 0.5, 1.0, 1.5, 2.0],
            duration=3.0,
            time_signature={"numerator": 4, "confidence": 0.4},
            beat_confidence=0.9,
            beat_needs_review=False,
        )
    except TimelineError as exc:
        assert exc.code == "missing_trusted_bar_grid"
    else:
        raise AssertionError("expected TimelineError")


def test_rejects_low_confidence_and_invalid_duration():
    for expected_code, kwargs in (
        (
            "low_timeline_confidence",
            {
                "downbeats": [0.0, 2.0],
                "beat_points": [],
                "duration": 4.0,
                "time_signature": {"numerator": 4},
                "beat_confidence": 0.49,
                "beat_needs_review": False,
            },
        ),
        (
            "invalid_duration",
            {
                "downbeats": [0.0, 2.0],
                "beat_points": [],
                "duration": 0.0,
                "time_signature": {"numerator": 4},
                "beat_confidence": 0.9,
                "beat_needs_review": False,
            },
        ),
    ):
        try:
            build_bar_timeline(**kwargs)
        except TimelineError as exc:
            assert exc.code == expected_code
        else:
            raise AssertionError(f"expected TimelineError({expected_code})")
