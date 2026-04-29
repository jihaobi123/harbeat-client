#!/usr/bin/env python3
"""Patch madmom downbeats.py for numpy >=1.24 compatibility."""
import re

fpath = "/home/mark/venvs/harbeat/lib/python3.10/site-packages/madmom/features/downbeats.py"

with open(fpath, "r") as f:
    content = f.read()

old_line = "        best = np.argmax(np.asarray(results)[:, 1])"
new_line = "        best = max(range(len(results)), key=lambda i: results[i][1])"

if old_line in content:
    content = content.replace(old_line, new_line)
    with open(fpath, "w") as f:
        f.write(content)
    print(f"PATCHED: replaced np.argmax line in {fpath}")
elif new_line in content:
    print("Already patched!")
else:
    print("ERROR: could not find target line")
