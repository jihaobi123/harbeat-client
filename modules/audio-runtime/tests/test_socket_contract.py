from harbeat_audio_runtime import socket_server


class FakeEngine:
    def __init__(self):
        self.calls = []

    def prepare_default_render(self, plan, **kwargs):
        self.calls.append(("prepare", plan, kwargs))
        return {"action": "default_render_prepared", "playback_tier": "default_render_playback"}

    def schedule_default_render(self, plan, **kwargs):
        self.calls.append(("schedule", plan, kwargs))
        return {"action": "default_render_scheduled", "degraded": False}

    def default_render_playback(self, plan, **kwargs):
        self.calls.append(("playback", plan, kwargs))
        return {"action": "default_render_playback", "degraded": False}


def test_default_render_socket_commands_map_without_mutating_plan(monkeypatch):
    fake = FakeEngine()
    monkeypatch.setattr(socket_server, "engine", fake)
    plan = {"pair_id": "pair-a-b", "from_at_sec": 14.5}

    prepared = socket_server._handle_command({
        "cmd": "prepare_default_render",
        "transition_plan": plan,
        "to_song_id": "b",
    })
    scheduled = socket_server._handle_command({
        "cmd": "schedule_default_render",
        "transition_plan": plan,
        "to_song_id": "b",
        "min_lead_sec": 1.75,
    })
    played = socket_server._handle_command({
        "cmd": "default_render_playback",
        "transition_plan": plan,
        "to_song_id": "b",
    })

    assert prepared["action"] == "default_render_prepared"
    assert scheduled["action"] == "default_render_scheduled"
    assert played["action"] == "default_render_playback"
    assert fake.calls[1][2]["min_lead_sec"] == 1.75
    assert all(call[1] is plan for call in fake.calls)
