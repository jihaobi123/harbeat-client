#!/usr/bin/env python3
"""input-daemon：MYKB E9s 九键 → audio-engine trigger + edge-agent key_event。"""

from __future__ import annotations

import logging
import threading
import time

import httpx
from evdev import InputDevice, ecodes, list_devices

from audio_socket import send_trigger
from config import (
    EDGE_AGENT_URL,
    INPUT_DEVICE_FALLBACKS,
    INPUT_DEVICE_NAME,
    INPUT_DEVICE_PATH,
    RECONNECT_SEC,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("input-daemon")

# 数字行 KEY_1..KEY_0 (codes 2-11) + 小键盘 KEY_KP1..KEY_KP0（九键盒常用）
# 语义（2026-05）：
#   1~5 → audio-engine trigger（DJ 加花音效，对应 sample_key 1-5）
#   6   → audio-engine trigger（key=3 黑胶刹停 — 物理键 6 是 DJ 习惯位）
#   7~9 → 仅作为 key_event 上报 edge-agent（手机 APP 在客户端映射为下一首/能量切歌/风格切歌）
#   0   → audio-engine trigger（key=0 暂停/恢复）
#   100/101 → 旋钮 KEY_VOLUMEUP / KEY_VOLUMEDOWN，本地直接 amixer 调主音量
#            （也上报 edge-agent，方便手机界面同步显示音量）。
SFX_KEYS = {1, 2, 3, 4, 5}
PAUSE_KEY = 0
VINYL_STOP_PHYSICAL_KEY = 6      # 物理键 6（DJ 黑胶刹停）
VINYL_STOP_SAMPLE_KEY = 3        # 实际触发的 audio-engine sample_key
VOL_UP_KEY = 100
VOL_DOWN_KEY = 101
VOL_STEP = "5%"                   # 每次旋钮一格调多少
VOL_CARD = "2"                    # ES8388 codec on RK3588

KEY_MAP = {
    ecodes.KEY_1: 1,
    ecodes.KEY_2: 2,
    ecodes.KEY_3: 3,
    ecodes.KEY_4: 4,
    ecodes.KEY_5: 5,
    ecodes.KEY_6: 6,
    ecodes.KEY_7: 7,
    ecodes.KEY_8: 8,
    ecodes.KEY_9: 9,
    ecodes.KEY_0: 0,
    ecodes.KEY_KP1: 1,
    ecodes.KEY_KP2: 2,
    ecodes.KEY_KP3: 3,
    ecodes.KEY_KP4: 4,
    ecodes.KEY_KP5: 5,
    ecodes.KEY_KP6: 6,
    ecodes.KEY_KP7: 7,
    ecodes.KEY_KP8: 8,
    ecodes.KEY_KP9: 9,
    ecodes.KEY_KP0: 0,
    ecodes.KEY_VOLUMEUP: VOL_UP_KEY,
    ecodes.KEY_VOLUMEDOWN: VOL_DOWN_KEY,
}

KEY_MAP = {
    ecodes.KEY_1: 1,
    ecodes.KEY_2: 2,
    ecodes.KEY_3: 3,
    ecodes.KEY_4: 4,
    ecodes.KEY_5: 5,
    ecodes.KEY_6: 6,
    ecodes.KEY_7: 7,
    ecodes.KEY_8: 8,
    ecodes.KEY_9: 9,
    ecodes.KEY_0: 0,
    ecodes.KEY_KP1: 1,
    ecodes.KEY_KP2: 2,
    ecodes.KEY_KP3: 3,
    ecodes.KEY_KP4: 4,
    ecodes.KEY_KP5: 5,
    ecodes.KEY_KP6: 6,
    ecodes.KEY_KP7: 7,
    ecodes.KEY_KP8: 8,
    ecodes.KEY_KP9: 9,
    ecodes.KEY_KP0: 0,
    ecodes.KEY_VOLUMEUP: VOL_UP_KEY,
    ecodes.KEY_VOLUMEDOWN: VOL_DOWN_KEY,
}


def _try_open(path: str) -> InputDevice | None:
    try:
        dev = InputDevice(path)
        # 试读能力，确认真有按键且权限 OK
        if ecodes.EV_KEY not in dev.capabilities():
            logger.debug("skip %s: no EV_KEY", path)
            return None
        return dev
    except PermissionError:
        logger.error("无权限打开 %s — 请执行: sudo usermod -aG input $USER 后重新登录 SSH", path)
        return None
    except (OSError, FileNotFoundError) as exc:
        logger.debug("cannot open %s: %s", path, exc)
        return None


def find_devices() -> list[InputDevice]:
    """打开所有候选 MYKB 键盘接口（Vial 可能从 event6 或 event10 发键）。"""
    candidates = [INPUT_DEVICE_PATH, *INPUT_DEVICE_FALLBACKS]
    seen: set[str] = set()
    devices: list[InputDevice] = []

    for path in candidates:
        if not path or path in seen:
            continue
        seen.add(path)
        dev = _try_open(path)
        if dev is not None:
            devices.append(dev)

    try:
        for path in list_devices():
            dev = InputDevice(path)
            name = (dev.name or "").lower()
            if INPUT_DEVICE_NAME.lower() not in name:
                continue
            # 跳过纯鼠标 + system control。Consumer Control 节点上有
            # KEY_VOLUMEUP/DOWN，**必须保留**，否则旋钮永远收不到事件。
            if "mouse" in name or "system control" in name:
                continue
            if ecodes.EV_KEY not in dev.capabilities():
                continue
            if dev.path in seen:
                continue
            seen.add(dev.path)
            devices.append(dev)
            logger.info("found by scan: %s (%s)", dev.path, dev.name)
    except PermissionError:
        logger.error("list_devices 无权限 — 请 newgrp input 或重新登录 SSH")

    return devices


def notify_edge_agent(key: int, ts_ms: int) -> None:
    try:
        httpx.post(
            f"{EDGE_AGENT_URL.rstrip('/')}/internal/key_event",
            json={"key": key, "source": "hid", "ts": ts_ms},
            timeout=0.3,
        )
    except Exception as exc:
        logger.debug("edge-agent notify failed: %s", exc)


def adjust_volume(direction: str) -> None:
    """旋钮调主音量。direction = '+' or '-'。

    RK3588 上 ES8388 codec 在 card 2。要点：
      - **PCM** 是 0-192 的真音量 control（有 'volume' capability）。
      - **Headphone / Speaker** 是 pswitch（开关），不是音量；amixer sset 5%- 在
        switch 上等同 toggle，会把整路输出关掉，导致"没声音"。
    所以这里只动 PCM。
    """
    import subprocess
    arg = f"{VOL_STEP}{'+' if direction == '+' else '-'}"
    try:
        r = subprocess.run(
            ["amixer", "-q", "-c", VOL_CARD, "sset", "PCM", arg],
            capture_output=True, timeout=0.5,
        )
        if r.returncode == 0:
            logger.info("volume %s %s on card %s/PCM", direction, VOL_STEP, VOL_CARD)
            return
        logger.warning("amixer PCM stderr: %s", (r.stderr or b"").decode("utf-8", "replace")[:120])
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("amixer PCM failed: %s", exc)


def run_loop(dev: InputDevice) -> None:
    logger.info("listening on %s (%s)", dev.path, dev.name)
    try:
        dev.grab()  # 独占设备，避免事件被桌面/其他进程吃掉
        logger.info("device grabbed (exclusive)")
    except OSError as exc:
        logger.warning("grab failed (try sudo?): %s — still listening", exc)

    for event in dev.read_loop():
        if event.type != ecodes.EV_KEY:
            continue
        if event.value != 1:  # 只处理按下
            continue
        key = KEY_MAP.get(event.code)
        if key is None:
            name = ecodes.KEY.get(event.code, f"code_{event.code}")
            logger.info("unmapped key: %s (code=%s) — 请反馈此键名", name, event.code)
            continue
        ts_ms = int(time.time() * 1000)
        t0 = time.perf_counter()
        if key in SFX_KEYS:
            try:
                send_trigger(key, time.time())
            except OSError as exc:
                logger.warning("audio socket failed: %s", exc)
                continue
            elapsed_ms = (time.perf_counter() - t0) * 1000
            notify_edge_agent(key, ts_ms)
            logger.info("key %s -> SFX trigger (%.1fms)", key, elapsed_ms)
        elif key == VINYL_STOP_PHYSICAL_KEY:
            # 物理 6 → 黑胶刹停（audio-engine sample_key 3）
            try:
                send_trigger(VINYL_STOP_SAMPLE_KEY, time.time())
            except OSError as exc:
                logger.warning("audio socket failed: %s", exc)
                continue
            notify_edge_agent(key, ts_ms)
            logger.info("key 6 -> vinyl_stop (sample_key=%d)", VINYL_STOP_SAMPLE_KEY)
        elif key == PAUSE_KEY:
            try:
                send_trigger(PAUSE_KEY, time.time())
            except OSError as exc:
                logger.warning("audio socket failed: %s", exc)
                continue
            notify_edge_agent(key, ts_ms)
            logger.info("key 0 -> pause/resume")
        elif key in (VOL_UP_KEY, VOL_DOWN_KEY):
            direction = "+" if key == VOL_UP_KEY else "-"
            adjust_volume(direction)
            notify_edge_agent(key, ts_ms)
        else:
            # 7~9：不走 trigger，只上报 edge-agent，交手机处理切歌逻辑
            notify_edge_agent(key, ts_ms)
            logger.info("key %s -> nav (no SFX, forwarded to edge-agent)", key)


def main() -> None:
    logger.info("input-daemon starting (device=%s)", INPUT_DEVICE_PATH)
    while True:
        devices = find_devices()
        if not devices:
            logger.warning(
                "device not found (plug USB 9-key? groups | grep input), retry in %ss",
                RECONNECT_SEC,
            )
            time.sleep(RECONNECT_SEC)
            continue

        logger.info("monitoring %d input device(s)", len(devices))
        threads: list[threading.Thread] = []
        for dev in devices:
            t = threading.Thread(target=run_loop, args=(dev,), daemon=True, name=f"input-{dev.path}")
            t.start()
            threads.append(t)

        try:
            while any(t.is_alive() for t in threads):
                time.sleep(1)
        except KeyboardInterrupt:
            raise
        except Exception:
            pass
        logger.warning("input thread exited, reconnecting in %ss", RECONNECT_SEC)
        time.sleep(RECONNECT_SEC)


if __name__ == "__main__":
    main()
