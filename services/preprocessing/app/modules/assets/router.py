from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.shared.config import get_settings

router = APIRouter()


@router.get("/{asset_path:path}")
def get_asset(asset_path: str):
    settings = get_settings()
    root = Path(settings.upload_dir).resolve()
    candidate = (root / unquote(asset_path)).resolve()
    root_prefix = str(root) + os.sep
    if str(candidate) != str(root) and not str(candidate).startswith(root_prefix):
        raise HTTPException(status_code=404, detail="Asset not found")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(str(candidate), filename=candidate.name)
