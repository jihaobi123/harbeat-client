from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.assets import router as assets_router


def test_get_asset_serves_file_under_upload_dir(tmp_path, monkeypatch):
    asset = tmp_path / "stems" / "song name" / "drums.wav"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"RIFF")
    monkeypatch.setattr(assets_router, "get_settings", lambda: SimpleNamespace(upload_dir=str(tmp_path)))

    response = assets_router.get_asset("stems/song%20name/drums.wav")

    assert response.path == str(asset)


def test_get_asset_blocks_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(assets_router, "get_settings", lambda: SimpleNamespace(upload_dir=str(tmp_path)))

    with pytest.raises(HTTPException) as exc:
        assets_router.get_asset("../secret.wav")

    assert exc.value.status_code == 404
