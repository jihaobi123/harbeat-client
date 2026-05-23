"""
轻量 DSP 工具：纯 numpy/Python 实现的双声道 biquad 滤波器（DF-II Transposed）。
为了在 RK3588 上保持依赖最小（不引入 scipy），采用纯 Python 循环 + numpy 数组。
单 callback 内 ~2048 样本 × 双通道 ≈ 4-8 ms，可接受。

系数公式参考 RBJ Audio EQ Cookbook。
"""

from __future__ import annotations

import math

import numpy as np


class Biquad:
    """单段双声道 biquad，DF-II Transposed 形式。

    系数随时变更（每个 callback 重设 cutoff）时，状态保持不变，不产生 click。
    """

    __slots__ = ("_b0", "_b1", "_b2", "_a1", "_a2",
                 "_z1L", "_z2L", "_z1R", "_z2R", "_bypass")

    def __init__(self) -> None:
        # 默认为 bypass：y = x
        self._b0 = 1.0
        self._b1 = 0.0
        self._b2 = 0.0
        self._a1 = 0.0
        self._a2 = 0.0
        self._z1L = 0.0
        self._z2L = 0.0
        self._z1R = 0.0
        self._z2R = 0.0
        self._bypass = True

    def reset(self) -> None:
        self._z1L = 0.0
        self._z2L = 0.0
        self._z1R = 0.0
        self._z2R = 0.0

    def set_bypass(self, on: bool) -> None:
        self._bypass = bool(on)

    # ---------------- 系数设置 (RBJ cookbook) ----------------

    def set_lpf(self, sr: float, fc: float, q: float = 0.707) -> None:
        fc = max(20.0, min(sr * 0.45, float(fc)))
        w0 = 2.0 * math.pi * fc / sr
        cosw = math.cos(w0)
        alpha = math.sin(w0) / (2.0 * q)
        b0 = (1.0 - cosw) * 0.5
        b1 = 1.0 - cosw
        b2 = (1.0 - cosw) * 0.5
        a0 = 1.0 + alpha
        a1 = -2.0 * cosw
        a2 = 1.0 - alpha
        self._set_normalized(b0, b1, b2, a0, a1, a2)

    def set_hpf(self, sr: float, fc: float, q: float = 0.707) -> None:
        fc = max(20.0, min(sr * 0.45, float(fc)))
        w0 = 2.0 * math.pi * fc / sr
        cosw = math.cos(w0)
        alpha = math.sin(w0) / (2.0 * q)
        b0 = (1.0 + cosw) * 0.5
        b1 = -(1.0 + cosw)
        b2 = (1.0 + cosw) * 0.5
        a0 = 1.0 + alpha
        a1 = -2.0 * cosw
        a2 = 1.0 - alpha
        self._set_normalized(b0, b1, b2, a0, a1, a2)

    def set_lowshelf(self, sr: float, fc: float, gain_db: float, q: float = 0.707) -> None:
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * math.pi * float(fc) / sr
        cosw = math.cos(w0)
        sinw = math.sin(w0)
        alpha = sinw / (2.0 * q)
        sqrtA2alpha = 2.0 * math.sqrt(A) * alpha
        b0 = A * ((A + 1.0) - (A - 1.0) * cosw + sqrtA2alpha)
        b1 = 2.0 * A * ((A - 1.0) - (A + 1.0) * cosw)
        b2 = A * ((A + 1.0) - (A - 1.0) * cosw - sqrtA2alpha)
        a0 = (A + 1.0) + (A - 1.0) * cosw + sqrtA2alpha
        a1 = -2.0 * ((A - 1.0) + (A + 1.0) * cosw)
        a2 = (A + 1.0) + (A - 1.0) * cosw - sqrtA2alpha
        self._set_normalized(b0, b1, b2, a0, a1, a2)

    def set_peak(self, sr: float, fc: float, gain_db: float, q: float = 1.0) -> None:
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * math.pi * float(fc) / sr
        cosw = math.cos(w0)
        alpha = math.sin(w0) / (2.0 * q)
        b0 = 1.0 + alpha * A
        b1 = -2.0 * cosw
        b2 = 1.0 - alpha * A
        a0 = 1.0 + alpha / A
        a1 = -2.0 * cosw
        a2 = 1.0 - alpha / A
        self._set_normalized(b0, b1, b2, a0, a1, a2)

    def set_highshelf(self, sr: float, fc: float, gain_db: float, q: float = 0.707) -> None:
        A = 10.0 ** (gain_db / 40.0)
        w0 = 2.0 * math.pi * float(fc) / sr
        cosw = math.cos(w0)
        sinw = math.sin(w0)
        alpha = sinw / (2.0 * q)
        sqrtA2alpha = 2.0 * math.sqrt(A) * alpha
        b0 = A * ((A + 1.0) + (A - 1.0) * cosw + sqrtA2alpha)
        b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cosw)
        b2 = A * ((A + 1.0) + (A - 1.0) * cosw - sqrtA2alpha)
        a0 = (A + 1.0) - (A - 1.0) * cosw + sqrtA2alpha
        a1 = 2.0 * ((A - 1.0) - (A + 1.0) * cosw)
        a2 = (A + 1.0) - (A - 1.0) * cosw - sqrtA2alpha
        self._set_normalized(b0, b1, b2, a0, a1, a2)

    def _set_normalized(self, b0: float, b1: float, b2: float,
                        a0: float, a1: float, a2: float) -> None:
        inv = 1.0 / a0
        self._b0 = b0 * inv
        self._b1 = b1 * inv
        self._b2 = b2 * inv
        self._a1 = a1 * inv
        self._a2 = a2 * inv
        self._bypass = False

    # ---------------- 处理 ----------------

    def process(self, x: np.ndarray) -> np.ndarray:
        """双声道处理。x shape (N, 2)。返回 same-shape float32 数组。"""
        if self._bypass or x.size == 0:
            return x
        b0 = self._b0
        b1 = self._b1
        b2 = self._b2
        a1 = self._a1
        a2 = self._a2
        z1L = self._z1L
        z2L = self._z2L
        z1R = self._z1R
        z2R = self._z2R
        # 拆通道方便索引（避免每 sample 两次 2D 索引）
        xL = x[:, 0]
        xR = x[:, 1]
        N = xL.shape[0]
        out = np.empty_like(x)
        outL = out[:, 0]
        outR = out[:, 1]
        for i in range(N):
            xl = float(xL[i])
            xr = float(xR[i])
            yl = b0 * xl + z1L
            z1L = b1 * xl + z2L - a1 * yl
            z2L = b2 * xl - a2 * yl
            yr = b0 * xr + z1R
            z1R = b1 * xr + z2R - a1 * yr
            z2R = b2 * xr - a2 * yr
            outL[i] = yl
            outR[i] = yr
        self._z1L = z1L
        self._z2L = z2L
        self._z1R = z1R
        self._z2R = z2R
        return out
