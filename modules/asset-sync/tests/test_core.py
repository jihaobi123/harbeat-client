import hashlib
import json
from pathlib import Path

import pytest

from harbeat_asset_sync.core import AssetSpec, atomic_publish, sidecar_path, validate_cached_asset, verify_download


def test_validates_size_hash_and_bound_sidecar(tmp_path):
    path=tmp_path/'asset.wav'; path.write_bytes(b'abc'); sha=hashlib.sha256(b'abc').hexdigest()
    spec=AssetSpec(sha256=sha,size=3)
    assert validate_cached_asset(path,spec)
    sidecar_path(path).write_text(json.dumps({'sha256':sha,'size':3,'mtime_ns':path.stat().st_mtime_ns}),encoding='utf-8')
    assert validate_cached_asset(path,spec)
    path.write_bytes(b'abcd')
    assert not validate_cached_asset(path,spec)


def test_rejects_invalid_spec_and_download(tmp_path):
    with pytest.raises(ValueError): AssetSpec(sha256='bad')
    path=tmp_path/'part'; path.write_bytes(b'a')
    with pytest.raises(ValueError): verify_download(path,AssetSpec(size=2))


def test_atomic_publish_replaces_destination(tmp_path):
    temporary=tmp_path/'asset.part'; destination=tmp_path/'cache'/'asset.wav'
    temporary.write_bytes(b'new'); destination.parent.mkdir(); destination.write_bytes(b'old')
    assert atomic_publish(temporary,destination)==destination
    assert destination.read_bytes()==b'new'; assert not temporary.exists()
