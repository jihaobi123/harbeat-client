import json
import struct

import pytest

from harbeat_physical_input import encode_audio_trigger, route_logical_key


def test_sfx_keys_trigger_same_sample_and_notify_edge():
    for key in range(1, 6):
        action = route_logical_key(key)
        assert action.audio_trigger_key == key
        assert action.notify_edge is True


def test_key_six_routes_to_vinyl_stop_sample_three():
    action = route_logical_key(6)
    assert action.logical_key == 6
    assert action.audio_trigger_key == 3


def test_zero_routes_to_audio_pause_resume():
    assert route_logical_key(0).audio_trigger_key == 0


def test_navigation_keys_are_event_only():
    for key in (7, 8, 9):
        action = route_logical_key(key)
        assert action.kind == "navigation_event"
        assert action.audio_trigger_key is None
        assert action.notify_edge is True


def test_volume_keys_keep_direction_and_event():
    assert route_logical_key(100).volume_direction == "+"
    assert route_logical_key(101).volume_direction == "-"


def test_unknown_key_is_rejected():
    with pytest.raises(ValueError):
        route_logical_key(42)


def test_audio_trigger_wire_frame_matches_deployed_protocol():
    frame = encode_audio_trigger(3, 1.25)
    size = struct.unpack(">I", frame[:4])[0]
    payload = json.loads(frame[4:].decode("utf-8"))
    assert size == len(frame) - 4
    assert payload == {"cmd": "trigger", "key": 3, "ts": 1.25}
