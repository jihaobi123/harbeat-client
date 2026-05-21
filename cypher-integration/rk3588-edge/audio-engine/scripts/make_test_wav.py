#!/usr/bin/env python3
"""生成测试用 cache/101/original.wav（440Hz 音调，5 秒）。"""

from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100
SONG_ID = 101
DURATION_SEC = 5.0
FREQ = 440.0


def main() -> None:
    out_dir = Path.home() / "cypher" / "cache" / str(SONG_ID)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "original.wav"

    t = np.linspace(0, DURATION_SEC, int(SR * DURATION_SEC), endpoint=False)
    tone = 0.25 * np.sin(2 * np.pi * FREQ * t)
    stereo = np.column_stack([tone, tone]).astype(np.float32)
    sf.write(str(out_path), stereo, SR, subtype="PCM_16")
    print(f"wrote {out_path} ({DURATION_SEC}s @ {FREQ}Hz)")


if __name__ == "__main__":
    main()
