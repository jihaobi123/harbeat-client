#!/usr/bin/env python3
"""Patch /home/cat/cypher/audio-engine/engine.py to use the new 6-slot DJ FX
sample map (catalog keys air_horn..vinyl_stop) and treat keys 1-6 as one-shots.

Idempotent: running twice leaves the file unchanged after the first run.
"""
from __future__ import annotations
import pathlib
import re
import sys

P = pathlib.Path("/home/cat/cypher/audio-engine/engine.py")
src = P.read_text(encoding="utf-8")

OLD_SAMPLES = re.compile(r"SAMPLE_FILES\s*=\s*\{[^}]*\}\s*\n# 叠到主轨上的增益\s*\nSAMPLE_GAIN\s*=\s*\{[^}]*\}", re.DOTALL)
NEW_BLOCK = (
    "SAMPLE_FILES = {\n"
    "    1: \"air_horn.wav\",            # 喇叭 长鸣\n"
    "    2: \"air_horn_burst.wav\",      # 喇叭 三连\n"
    "    3: \"snare_crack.wav\",         # 嚓声 Snare\n"
    "    4: \"beat_juggle_stutter.wav\", # Beat Juggle\n"
    "    5: \"bass_drop.wav\",           # Bass Drop\n"
    "    6: \"vinyl_stop.wav\",          # 黑胶刹停\n"
    "}\n"
    "# 叠到主轨上的增益\n"
    "SAMPLE_GAIN = {1: 1.4, 2: 1.4, 3: 1.4, 4: 1.2, 5: 1.6, 6: 1.3}"
)
new = OLD_SAMPLES.sub(NEW_BLOCK, src, count=1)
if new == src:
    if "vinyl_stop.wav" in src:
        print("SAMPLE_FILES already updated, skip.")
    else:
        print("ERROR: could not find SAMPLE_FILES block to patch.", file=sys.stderr)
        sys.exit(2)

# Expand one-shot range from (1,2,3) -> (1,2,3,4,5,6); drop the loop branch
# that used keys 4-6. Keep keys 7-9 (stem fx) untouched.
new2 = new.replace(
    "            if key in (1, 2, 3):",
    "            if key in (1, 2, 3, 4, 5, 6):",
    1,
)
new2 = re.sub(
    r"            if key in \(4, 5, 6\):\n"
    r"                if key in self\.loops:\n"
    r"                    del self\.loops\[key\]\n"
    r"                    return \{\"key\": key, \"action\": \"loop_off\"\}\n"
    r"                buf = self\.samples\.get\(key\)\n"
    r"                if buf is None:\n"
    r"                    return \{\"key\": key, \"error\": \"sample_missing\"\}\n"
    r"                self\.loops\[key\] = \[buf, 0\]\n"
    r"                return \{\"key\": key, \"action\": \"loop_on\"\}\n",
    "",
    new2,
    count=1,
)

if new2 == new:
    print("WARN: trigger() one-shot range not patched (already done?).")
P.write_text(new2, encoding="utf-8")
print("OK patched.")
