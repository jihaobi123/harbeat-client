from pathlib import Path
import shutil

import pytest


def test_device_grid_normalizes_supported_stereo_48khz(tmp_path, monkeypatch):
    sf = pytest.importorskip('soundfile')
    np = pytest.importorskip('numpy')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('audio tools are unavailable')
    root = Path(__file__).resolve().parents[1] / 'legacy'
    monkeypatch.syspath_prepend(str(root))
    from listen_imports.jetson import normalize_source

    source = tmp_path / 'audio'
    sf.write(source, np.zeros((48000, 2)), 48000, format='WAV')
    assert normalize_source(source, tmp_path) == source

    canonical = normalize_source(source, tmp_path, device_grid=True)
    info = sf.info(canonical)
    assert (info.samplerate, info.frames, info.channels, info.format) == (44100, 44100, 2, 'FLAC')
    assert normalize_source(source, tmp_path, device_grid=True) == canonical
