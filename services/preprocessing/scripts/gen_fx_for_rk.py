"""Render the 6 DJ FX as 44.1kHz stereo WAVs under /tmp/fx_out/ for RK upload.

Usage on Jetson:
    cd /home/mark/harbeat && python3 scripts/gen_fx_for_rk.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.modules.dj_control.fx_synth import FX_CATALOG, render_to_wav_bytes  # noqa: E402

OUT = "/tmp/fx_out"
os.makedirs(OUT, exist_ok=True)
for key in FX_CATALOG:
    wav = render_to_wav_bytes(key)
    path = os.path.join(OUT, f"{key}.wav")
    with open(path, "wb") as fh:
        fh.write(wav)
    print(f"{key}: {len(wav)} bytes -> {path}")
