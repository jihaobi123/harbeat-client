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
            if "mouse" in name or "consumer" in name or "system control" in name:
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
        try:
            send_trigger(key, time.time())
        except OSError as exc:
            logger.warning("audio socket failed: %s", exc)
            continue
        elapsed_ms = (time.perf_counter() - t0) * 1000
        notify_edge_agent(key, ts_ms)
        logger.info("key %s -> trigger (%.1fms)", key, elapsed_ms)


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
