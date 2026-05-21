import os
from pathlib import Path

AUDIO_SOCKET = os.environ.get("AUDIO_SOCKET", "/tmp/cypher-audio.sock")
EDGE_AGENT_URL = os.environ.get("EDGE_AGENT_URL", "http://127.0.0.1:9000")
# 优先用 by-id 稳定路径（不随 event 编号变化）
_DEFAULT_BY_ID = "/dev/input/by-id/usb-MYKB_E9s_vial:f64c2b3c-event-kbd"
INPUT_DEVICE_PATH = os.environ.get(
    "INPUT_DEVICE_PATH",
    _DEFAULT_BY_ID if os.path.exists(_DEFAULT_BY_ID) else "/dev/input/event6",
)
INPUT_DEVICE_NAME = os.environ.get("INPUT_DEVICE_NAME", "MYKB E9s")
# 备选 event 节点（Vial 键盘可能出现在 event6 或 event10）
INPUT_DEVICE_FALLBACKS = [
    p.strip()
    for p in os.environ.get(
        "INPUT_DEVICE_FALLBACKS",
        "/dev/input/event6,/dev/input/event10,/dev/input/by-id/usb-MYKB_E9s_vial:f64c2b3c-if02-event-kbd",
    ).split(",")
    if p.strip()
]
RECONNECT_SEC = float(os.environ.get("INPUT_RECONNECT_SEC", "5"))
