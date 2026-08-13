import pytest

from harbeat_transition_orchestrator import (
    OrchestrationValidationError,
    accept_task,
    build_priority_sync_request,
    public_task,
    transition_task,
    validate_request,
)


def make_request(**overrides):
    plan = {
        "pair_id": "pair-a-b",
        "from_song_id": "a",
        "to_song_id": "b",
        "from_at_sec": 14.5,
        "audio_feature_source": "dj_structure_precomputed_window_v2",
        "renderer_version": "three_band_default_v7_standalone_curve_no_energy_floor",
        "default_mix": {
            "pair_id": "pair-a-b",
            "from_song_id": "a",
            "to_song_id": "b",
            "from_at_sec": 14.5,
            "audio_feature_source": "dj_structure_precomputed_window_v2",
            "renderer_version": "three_band_default_v7_standalone_curve_no_energy_floor",
        },
    }
    manifest = {
        "pair_id": "pair-a-b",
        "audio_feature_source": "dj_structure_precomputed_window_v2",
        "renderer_version": "three_band_default_v7_standalone_curve_no_energy_floor",
        "files": {
            "transition_render": {"url": "https://jetson/render.wav"},
            "transition_render_meta": {"url": "https://jetson/render.json"},
        },
    }
    value = {
        "transition_id": "transition-1234",
        "trigger": "fast_cut",
        "from_song_id": "a",
        "to_song_id": "b",
        "transition_plan": plan,
        "pair_manifest": manifest,
    }
    value.update(overrides)
    return value


def valid(**overrides):
    req = make_request(**overrides)
    return validate_request(
        transition_id=req["transition_id"],
        trigger=req["trigger"],
        from_song_id=req["from_song_id"],
        to_song_id=req["to_song_id"],
        transition_plan=req["transition_plan"],
        pair_manifest=req["pair_manifest"],
    )


def test_validate_and_build_priority_sync_request():
    request = valid()
    sync = build_priority_sync_request(request)
    assert sync["plan_id"] == "transition-1234"
    assert sync["priority"] is True
    assert sync["wait"] is False
    assert sync["tracks"] == []
    assert len(sync["default_mix_pairs"]) == 1


def test_rejects_pair_song_and_renderer_mismatch():
    for field, value in (
        ("pair_manifest", {"pair_id": "other", "files": {}}),
        ("from_song_id", "wrong"),
    ):
        req = make_request(**{field: value})
        kwargs = dict(
            transition_id=req["transition_id"], trigger=req["trigger"],
            from_song_id=req["from_song_id"], to_song_id=req["to_song_id"],
            transition_plan=req["transition_plan"], pair_manifest=req["pair_manifest"],
        )
        with pytest.raises(OrchestrationValidationError):
            validate_request(**kwargs)
    plan = make_request()["transition_plan"]
    plan["renderer_version"] = "legacy"
    with pytest.raises(OrchestrationValidationError, match="renderer_version_mismatch"):
        validate_request(
            transition_id="transition-1234", trigger="fast_cut", from_song_id="a", to_song_id="b",
            transition_plan=plan, pair_manifest=make_request()["pair_manifest"],
        )


def test_rejects_degraded_or_incomplete_plan():
    req = make_request()
    req["transition_plan"]["degraded"] = True
    with pytest.raises(OrchestrationValidationError, match="degraded_plan_rejected"):
        valid(**req)
    req = make_request()
    req["pair_manifest"]["files"].pop("transition_render_meta")
    with pytest.raises(OrchestrationValidationError, match="incomplete_pair_manifest"):
        valid(**req)


def test_task_state_machine_is_terminal_and_public_safe():
    request = valid()
    task = accept_task(request, now="2026-08-13T00:00:00Z", deadline_epoch_sec=100.0)
    task = transition_task(task, "syncing")
    task = transition_task(task, "cache_ready")
    task = transition_task(task, "prepared")
    task = transition_task(task, "scheduled", result={"action": "default_render_scheduled"})
    assert public_task(task, now_epoch_sec=90.0)["deadline_in_sec"] == 10.0
    assert "request_hash" not in public_task(task)
    with pytest.raises(OrchestrationValidationError, match="invalid_state_transition"):
        transition_task(task, "failed")


def test_duplicate_acceptance_has_stable_hash_and_priority_pair_only():
    first = accept_task(valid(), now="now", deadline_epoch_sec=50.0)
    second = accept_task(valid(), now="later", deadline_epoch_sec=60.0)
    assert first["request_hash"] == second["request_hash"]
    assert build_priority_sync_request(valid())["default_mix_pairs"][0]["pair_id"] == "pair-a-b"
