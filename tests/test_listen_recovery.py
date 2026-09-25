import json
import subprocess
import wave

import pytest

from listen_imports.jetson import normalize_source
from listen_imports.worker import remote_finished


def test_normalization_rebuilds_incomplete_checkpoint(tmp_path):
    import soundfile as sf
    source=tmp_path/'input.wav'
    with wave.open(str(source),'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(8000)
        audio.writeframes(b'\0\0'*8000*21)
    (tmp_path/'normalized.flac').write_bytes(b'incomplete prior attempt')
    target=normalize_source(source,tmp_path)
    assert sf.info(target).channels==2
    assert abs(sf.info(target).duration-21)<.01
    assert json.loads((tmp_path/'normalization.json').read_text())['output_sha256']
    mtime=target.stat().st_mtime_ns
    assert normalize_source(source,tmp_path).stat().st_mtime_ns==mtime


def test_dead_remote_unit_fails_promptly_instead_of_blocking_queue():
    assert remote_finished('active',False) is False
    assert remote_finished('inactive',True) is True
    with pytest.raises(ValueError,match='中断'):
        remote_finished('failed',False)
