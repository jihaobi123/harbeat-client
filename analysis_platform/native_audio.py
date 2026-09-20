"""Bounded-memory audio decoding for the ARM model backend."""


def load_audio(path, resampler):
    import numpy as np
    import soundfile as sf
    info = sf.info(path)
    if not .5 <= info.duration <= 7200:
        raise ValueError('audio duration must be between 0.5 seconds and 2 hours')
    # Only the mono signal is retained. Reserve headroom for resampling, mel
    # patches and TensorFlow under the service's shared 6 GB memory budget.
    if info.frames * 4 > 1024**3:
        raise ValueError('音频解码超过模型内存预算，请先重采样为 16 kHz 后重试；原始报告仍保留')
    mono = np.empty(info.frames, dtype=np.float32)
    position = 0
    for block in sf.blocks(path, blocksize=65536, dtype='float32', always_2d=True):
        mono[position:position+len(block)] = block.mean(axis=1)
        position += len(block)
    if position != info.frames:
        raise ValueError('decoded frame count differs from audio header')
    if info.samplerate == 16000:
        return mono
    return resampler(inputSampleRate=info.samplerate, outputSampleRate=16000, quality=4)(mono)
