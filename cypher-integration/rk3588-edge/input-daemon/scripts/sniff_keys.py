#!/usr/bin/env python3
"""调试：按下九键时打印原始键码（运行 30 秒后自动退出）。"""

import sys
import time
from evdev import InputDevice, ecodes

DEV = sys.argv[1] if len(sys.argv) > 1 else "/dev/input/by-id/usb-MYKB_E9s_vial:f64c2b3c-event-kbd"

dev = InputDevice(DEV)
print(f"Sniffing {dev.path} ({dev.name}) — 请按九键，Ctrl+C 结束\n")
dev.grab()
end = time.time() + 30
for event in dev.read_loop():
    if event.type == ecodes.EV_KEY:
        name = ecodes.KEY.get(event.code, event.code)
        print(f"KEY code={event.code} name={name} value={event.value}")
    if time.time() > end:
        break
