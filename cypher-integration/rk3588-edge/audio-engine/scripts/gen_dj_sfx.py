#!/usr/bin/env python3
"""生成 5 个常见 DJ 加花音效占位 wav，落到 ~/cypher/samples/。

后续如需更高质量的素材，覆盖同名文件即可。

用法（在 RK3588 上）：
    cd ~/code/harbeat-client/cypher-integration/rk3588-edge/audio-engine
    python3 scripts/gen_dj_sfx.py
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
OUT = Path.home() / "cypher" / "samples"
OUT.mkdir(parents=True, exist_ok=True)


def _save(name: str, mono: np.ndarray) -> None:
    # normalize 至 -1dBFS，避免推到 0dB clip
    peak = float(np.max(np.abs(mono)) or 1.0)
    mono = mono.astype(np.float32) * (0.89 / peak)
    stereo = np.column_stack([mono, mono])
    out_path = OUT / name
    sf.write(str(out_path), stereo, SR, subtype="PCM_16")
    print(f"  + {out_path}  ({len(mono)/SR:.2f}s)")


def scratch(dur: float = 0.6) -> np.ndarray:
    """搓碟：高频白噪在 LFO 调制下做正反向滑音。"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    # 模拟黑胶搓碟：100ms 正向 + 100ms 反向 + 200ms 正向，频率 LFO 强烈
    env = np.exp(-3.5 * t)
    lfo = np.sin(2 * np.pi * 8.0 * t) * 0.6  # 控制速度起伏
    base_freq = 220.0 * (1.0 + lfo)
    phase = np.cumsum(base_freq) / SR * 2 * np.pi
    tone = np.sin(phase) * 0.7
    noise = (np.random.rand(n) * 2 - 1) * 0.5
    sig = (tone + noise) * env
    return sig


def air_horn(dur: float = 0.8) -> np.ndarray:
    """气笛 / Reggae Air Horn：三段 minor 三度堆叠的方波 + 包络。"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    # 包络：快速 attack，平稳 sustain，长尾 release
    env = np.minimum(t / 0.03, 1.0) * np.exp(-2.2 * np.maximum(t - 0.1, 0))
    f1, f2, f3 = 110, 165, 220  # 类似牙买加 horn 的 minor 第三度堆叠
    saw = lambda f: 2 * ((t * f) - np.floor(0.5 + t * f))
    sig = (saw(f1) * 0.5 + saw(f2) * 0.35 + saw(f3) * 0.25) * env
    # 轻微 LPF
    a = 0.18
    y = np.zeros_like(sig)
    prev = 0.0
    for i in range(n):
        prev = prev + a * (sig[i] - prev)
        y[i] = prev
    return y


def spinback(dur: float = 0.6) -> np.ndarray:
    """倒带：高频开始急剧下行至接近零的频率扫."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    # 频率从 1200Hz 指数衰减到 40Hz
    freq = 1200 * np.exp(-5.5 * t) + 40
    phase = np.cumsum(freq) / SR * 2 * np.pi
    tone = np.sin(phase) * 0.6 + np.sign(np.sin(phase * 0.5)) * 0.2
    env = np.exp(-1.8 * t) * np.minimum(t / 0.005, 1.0)
    return tone * env


def siren(dur: float = 0.9) -> np.ndarray:
    """警报：500-1500Hz 的 vibrato 方波。"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 4.0 * t)  # 4Hz 摆动
    freq = 500 + 1000 * lfo
    phase = np.cumsum(freq) / SR * 2 * np.pi
    sq = np.sign(np.sin(phase))
    env = np.minimum(t / 0.02, 1.0) * np.minimum((dur - t) / 0.1, 1.0)
    return sq * env * 0.6


def whoosh(dur: float = 0.5) -> np.ndarray:
    """嗖声 / riser：带通扫频白噪。"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    noise = np.random.randn(n)
    # 简易频谱整形：随时间频率上升 → 用一阶 hp + lp 滤波模拟带通中心移动
    out = np.zeros(n, dtype=np.float32)
    bp_state = np.zeros(2, dtype=np.float32)
    for i in range(n):
        prog = t[i] / dur  # 0..1
        # 带通中心从 200Hz → 6000Hz
        cf = 200 * (1.0 + 29.0 * prog)
        alpha = math.exp(-2 * math.pi * cf / SR)
        x = noise[i]
        # 一阶低通
        bp_state[0] = bp_state[0] * alpha + x * (1 - alpha)
        # 减去低频成分 = 高通
        hp = x - bp_state[1]
        bp_state[1] = bp_state[1] * 0.999 + x * 0.001
        out[i] = (bp_state[0] * 0.5 + hp * 0.5)
    env = np.minimum(t / 0.02, 1.0) ** 2
    return out * env * 0.7


def main() -> None:
    print(f"writing samples to {OUT}")
    _save("scratch.wav",   scratch())
    _save("air_horn.wav",  air_horn())
    _save("spinback.wav",  spinback())
    _save("siren.wav",     siren())
    _save("whoosh.wav",    whoosh())
    print("done. restart audio-engine:")
    print("  sudo systemctl restart cypher-audio-engine.service")


if __name__ == "__main__":
    main()
