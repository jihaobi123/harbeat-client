import os
from pathlib import Path

CYPHER_HOME = Path(os.environ.get("CYPHER_HOME", str(Path.home() / "cypher")))
CACHE_DIR = CYPHER_HOME / "cache"
AUDIO_SOCKET = "/tmp/cypher-audio.sock"
SAMPLE_RATE = 44100
BLOCK_SIZE = 512
REQUIRE_STEMS_FOR_PLAY = os.environ.get("CYPHER_REQUIRE_STEMS_FOR_PLAY", "0").lower() in (
    "1",
    "true",
    "yes",
)

# sounddevice 设备：索引号(如 6) 或名称子串(如 "hdmi", "USB")
# 默认强制走板载 ES8388 耳机孔（接耳机线到音箱）。
# 要切到 HDMI / USB 声卡时设 CYPHER_AUDIO_DEVICE=hdmi / USB / 数字。
_RAW_AUDIO_DEVICE = os.environ.get("CYPHER_AUDIO_DEVICE") or "es8388"


def resolve_audio_device(raw: str | None) -> int | str | None:
    """解析声卡：支持编号、pulse、es8388 等别名。"""
    if raw is None or raw == "":
        return None
    if raw.isdigit():
        return int(raw)
    import sounddevice as sd

    key = raw.lower()
    aliases = {
        "pulse": "pulse",
        "default": "default",
        "hdmi": "hdmi",
        "es8388": "es8388",
        "headphone": "es8388",
    }
    key = aliases.get(key, key)
    for i, dev in enumerate(sd.query_devices()):
        name = (dev.get("name") or "").lower()
        if key in name and dev.get("max_output_channels", 0) > 0:
            return i
    if key in ("es8388", "headphone"):
        return resolve_audio_device("pulse")
    try:
        d = sd.query_devices(raw)
        if isinstance(d, dict) and d.get("max_output_channels", 0) > 0:
            return d
    except Exception:
        pass
    return raw


AUDIO_DEVICE: int | str | None = resolve_audio_device(_RAW_AUDIO_DEVICE)
