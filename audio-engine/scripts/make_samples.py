#!/usr/bin/env python3
"""生成 9 键 sample（44100 stereo）；2/4/5 加大音量、更易听清。"""

from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
OUT = Path.home() / "cypher" / "samples"


def _normalize(stereo: np.ndarray, peak_target: float = 0.7) -> np.ndarray:
    peak = np.max(np.abs(stereo))
    if peak > 0:
        stereo = stereo * (peak_target / peak)
    return stereo.astype(np.float32)


def sample_ha() -> np.ndarray:
    t = np.linspace(0, 0.12, int(SR * 0.12), endpoint=False)
    w = 0.8 * np.sin(2 * np.pi * 1200 * t) * np.exp(-t * 35)
    s = np.column_stack([w, w])
    return _normalize(s)


def sample_scratch() -> np.ndarray:
    """键 2：白噪声 + 扫频，模拟 scratch。"""
    n = int(SR * 0.28)
    rng = np.random.default_rng(42)
    noise = rng.standard_normal(n).astype(np.float32)
    # 简单高通感
    for i in range(1, n):
        noise[i] = 0.92 * noise[i] + 0.08 * (noise[i] - noise[i - 1])
    t = np.linspace(0, 1, n, endpoint=False)
    env = np.sin(np.pi * t) ** 0.7
    w = 0.95 * noise * env
    s = np.column_stack([w, w])
    return _normalize(s, 0.85)


def sample_horn() -> np.ndarray:
    t = np.linspace(0, 0.4, int(SR * 0.4), endpoint=False)
    w = 0.5 * (np.sin(2 * np.pi * 440 * t) + 0.5 * np.sin(2 * np.pi * 660 * t))
    w *= np.exp(-t * 4)
    s = np.column_stack([w, w])
    return _normalize(s)


def sample_drum_loop() -> np.ndarray:
    """键 4：明显 kick 节奏 loop。"""
    dur = 1.0
    n = int(SR * dur)
    buf = np.zeros(n, dtype=np.float32)
    bpm = 120
    spb = int(SR * 60 / bpm)
    for beat in range(int(dur * bpm / 60) + 1):
        pos = beat * spb
        if pos >= n:
            break
        length = min(800, n - pos)
        t = np.linspace(0, 1, length, endpoint=False)
        kick = 0.95 * np.sin(2 * np.pi * (80 + 200 * (1 - t)) * t) * np.exp(-t * 8)
        buf[pos : pos + length] += kick
    s = np.column_stack([buf, buf])
    return _normalize(s, 0.8)


def sample_bass_loop() -> np.ndarray:
    """键 5：中低频 bass，小音箱也能听见。"""
    dur = 1.0
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    # 98Hz + 二次谐波，小音箱也能听见
    w = 0.7 * np.sin(2 * np.pi * 98 * t) + 0.25 * np.sin(2 * np.pi * 196 * t)
    w *= 0.5 + 0.5 * np.sin(2 * np.pi * 2 * t)  # 振幅调制
    s = np.column_stack([w, w])
    return _normalize(s, 0.85)


def sample_hat_loop() -> np.ndarray:
    dur = 0.5
    n = int(SR * dur)
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n).astype(np.float32)
    for i in range(1, n):
        noise[i] = noise[i] - 0.95 * noise[i - 1]
    t = np.linspace(0, 1, n, endpoint=False)
    w = 0.4 * noise * (0.3 + 0.7 * np.sin(2 * np.pi * 16 * t) ** 2)
    s = np.column_stack([w, w])
    return _normalize(s, 0.65)


BUILDERS = {
    "01_ha.wav": sample_ha,
    "02_scratch.wav": sample_scratch,
    "03_horn.wav": sample_horn,
    "04_drum_loop.wav": sample_drum_loop,
    "05_bass_loop.wav": sample_bass_loop,
    "06_hat_loop.wav": sample_hat_loop,
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, fn in BUILDERS.items():
        path = OUT / name
        sf.write(str(path), fn(), SR, subtype="PCM_16")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
