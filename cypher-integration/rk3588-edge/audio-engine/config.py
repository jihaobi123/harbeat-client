from __future__ import annotations

import os
from pathlib import Path

CYPHER_HOME = Path(os.environ.get("CYPHER_HOME", str(Path.home() / "cypher")))
CACHE_DIR = CYPHER_HOME / "cache"
AUDIO_SOCKET = "/tmp/cypher-audio.sock"
SAMPLE_RATE = 44100
BLOCK_SIZE = 2048
REQUIRE_STEMS_FOR_PLAY = os.environ.get("CYPHER_REQUIRE_STEMS_FOR_PLAY", "0").lower() in (
    "1",
    "true",
    "yes",
)

# sounddevice 设备：索引号(如 6) 或名称子串(如 "hdmi", "USB")
# 留空则用系统默认（当前板子为 PulseAudio → ES8388 耳机孔）
_RAW_AUDIO_DEVICE = os.environ.get("CYPHER_AUDIO_DEVICE") or None


def resolve_audio_device(raw: str | None) -> int | str | None:
    """解析声卡：支持编号、pulse、es8388 等别名。绝不返回无法匹配的裸字符串。"""
    if raw is None or raw == "":
        return None
    if raw.isdigit():
        return int(raw)
    import sounddevice as sd

    key = raw.lower().strip()
    aliases = {
        "pulse": ("pulse", "default"),
        "default": ("default", "pulse"),
        "hdmi": ("hdmi", "rockchip-hdmi"),
        "es8388": ("es8388", "es8323", "rockchip-es8388"),
        "headphone": ("es8388", "es8323", "rockchip-es8388"),
        "usb": ("usb",),
    }
    search_keys = aliases.get(key, (key,))

    outputs: list[tuple[int, str]] = []
    for i, dev in enumerate(sd.query_devices()):
        if dev.get("max_output_channels", 0) > 0:
            outputs.append((i, (dev.get("name") or "").lower()))

    for sk in search_keys:
        for i, name in outputs:
            if sk in name:
                return i

    # pulse 不可用时回退：default → es8388 硬件 → 第一个输出设备
    if key in ("pulse", "default", "es8388", "headphone"):
        for prefer in ("default", "es8388", "es8323", "sysdefault"):
            for i, name in outputs:
                if prefer in name:
                    return i
        if outputs:
            return outputs[0][0]

    try:
        d = sd.query_devices(raw)
        if isinstance(d, dict) and d.get("max_output_channels", 0) > 0:
            return raw
    except Exception:
        pass
    if outputs:
        return outputs[0][0]
    return None


AUDIO_DEVICE: int | str | None = resolve_audio_device(_RAW_AUDIO_DEVICE)
