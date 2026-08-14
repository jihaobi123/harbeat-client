#!/usr/bin/env python3
import json
import socket
import subprocess
import time
from pathlib import Path

import sounddevice


devices = sounddevice.query_devices()
started = time.monotonic_ns()
time.sleep(0.01)
finished = time.monotonic_ns()
ffmpeg = subprocess.run(
    ["ffmpeg", "-version"],
    check=True,
    capture_output=True,
    text=True,
).stdout.splitlines()[0]
socket_candidates = [Path("/tmp/cypher-audio.sock"), Path("/run/cypher/audio.sock")]
aplay = subprocess.run(
    ["aplay", "-l"],
    check=True,
    capture_output=True,
    text=True,
).stdout
normalized_aplay = aplay.casefold()
result = {
    "audio_device_count": len(devices),
    "es8388_card_present": "rockchipes8388" in normalized_aplay
    or "rockchip-es8388" in normalized_aplay
    or "es8323" in normalized_aplay,
    "monotonic_clock_advanced": finished > started,
    "ffmpeg": ffmpeg,
    "legacy_audio_socket_present": any(path.is_socket() for path in socket_candidates),
}
print(json.dumps(result, sort_keys=True))
if (
    result["audio_device_count"] <= 0
    or not result["es8388_card_present"]
    or not result["monotonic_clock_advanced"]
):
    raise SystemExit("RK hardware smoke failed")
