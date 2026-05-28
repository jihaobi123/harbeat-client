#!/usr/bin/env python3
"""sync-worker: download Jetson manifest assets into local RK cache."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("sync-worker")

CYPHER_HOME = Path(os.environ.get("CYPHER_HOME", str(Path.home() / "cypher")))
CACHE_DIR = CYPHER_HOME / "cache"
JETSON_BASE_URL = os.environ.get("JETSON_BASE_URL", "http://127.0.0.1:8000")
JWT_TOKEN = os.environ.get("JWT_TOKEN", "")
RK_TOKEN = os.environ.get("HARBEAT_RK_TOKEN") or os.environ.get("RKTOKEN", "")
MAX_CONCURRENCY = int(os.environ.get("SYNC_MAX_CONCURRENCY", "4"))
REQUEST_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)

app = FastAPI(title="Cypher Sync Worker", version="0.1.0")


class SyncState:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.running = False
        self.total = 0
        self.completed = 0
        self.downloaded = 0
        self.current_file: str | None = None
        self.percent = 0.0
        self.errors: list[str] = []
        self.plan_id: str | None = None

    async def reset(self, total: int, plan_id: str | None) -> None:
        async with self.lock:
            self.running = True
            self.total = total
            self.completed = 0
            self.downloaded = 0
            self.current_file = None
            self.percent = 0.0
            self.errors = []
            self.plan_id = plan_id

    async def mark_current(self, name: str) -> None:
        async with self.lock:
            self.current_file = name

    async def mark_done(self) -> None:
        async with self.lock:
            self.completed += 1
            self.downloaded = self.completed
            self.percent = round((self.completed / self.total) * 100, 2) if self.total else 100.0

    async def add_error(self, message: str) -> None:
        async with self.lock:
            self.errors.append(message)

    async def finish(self) -> None:
        async with self.lock:
            self.running = False
            self.current_file = None
            if self.total and not self.errors:
                self.percent = 100.0

    async def snapshot(self) -> dict[str, Any]:
        async with self.lock:
            return {
                "running": self.running,
                "plan_id": self.plan_id,
                "total": self.total,
                "downloaded": self.downloaded,
                "completed": self.completed,
                "current_file": self.current_file,
                "percent": self.percent,
                "errors": list(self.errors),
            }


state = SyncState()
_sync_task: asyncio.Task | None = None


def _manifest_from_body(body: dict[str, Any]) -> dict[str, Any]:
    if "manifest" in body and isinstance(body["manifest"], dict):
        return _manifest_from_body(body["manifest"])
    if "data" in body and isinstance(body["data"], dict):
        return _manifest_from_body(body["data"])
    return body


def _file_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for track in manifest.get("tracks") or []:
        song_id = track.get("song_id") or track.get("library_song_id") or track.get("id")
        if song_id is None:
            continue
        files = track.get("files") or {}
        original = files.get("original")
        if original:
            items.append({"song_id": song_id, "kind": "original", "info": original})
        stems = files.get("stems") or {}
        for stem in ("vocals", "drums", "bass", "other"):
            if stems.get(stem):
                items.append({"song_id": song_id, "kind": stem, "info": stems[stem]})
    return items


def _manifest_asset_report(manifest: dict[str, Any]) -> dict[str, Any]:
    items = _file_items(manifest)
    missing: dict[str, list[str]] = {}
    complete_tracks = 0
    track_count = 0
    for track in manifest.get("tracks") or []:
        song_id = track.get("song_id") or track.get("library_song_id") or track.get("id")
        if song_id is None:
            continue
        track_count += 1
        files = track.get("files") or {}
        stems = files.get("stems") or {}
        absent = []
        if not files.get("original"):
            absent.append("original")
        absent.extend(stem for stem in ("vocals", "drums", "bass", "other") if not stems.get(stem))
        if absent:
            missing[str(song_id)] = absent
        else:
            complete_tracks += 1
    return {
        "track_count": track_count,
        "asset_count": len(items),
        "complete_tracks": complete_tracks,
        "missing": missing,
    }


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if JWT_TOKEN:
        headers["Authorization"] = f"Bearer {JWT_TOKEN}"
    if RK_TOKEN:
        headers["X-RK-Token"] = RK_TOKEN
    return headers


def _final_url(url: str) -> str:
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(JETSON_BASE_URL.rstrip("/") + "/", url.lstrip("/"))


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sidecar(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


def _already_valid(path: Path, expected_sha: str | None, expected_size: int | None) -> bool:
    if not path.is_file():
        return False
    if expected_sha and _sidecar(path).is_file():
        if _sidecar(path).read_text(encoding="utf-8").strip() == expected_sha:
            return True
    if expected_size is not None and path.stat().st_size != expected_size:
        return False
    if expected_sha:
        return _sha256(path) == expected_sha
    return True


def _needs_wav_conversion(info: dict[str, Any]) -> bool:
    fmt = str(info.get("format") or "").lower()
    url = str(info.get("url") or "").lower()
    return fmt not in ("", "wav", "wave") and not url.endswith(".wav")


def _convert_to_wav(src: Path, dst: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        logger.warning("ffmpeg not found; storing validated source bytes as %s", dst)
        src.replace(dst)
        return
    tmp = dst.with_suffix(".wav.tmp")
    subprocess.run(
        [ffmpeg, "-y", "-i", str(src), "-ar", "44100", "-ac", "2", "-f", "wav", str(tmp)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    tmp.replace(dst)
    src.unlink(missing_ok=True)



def _choose_ext(kind: str, info: dict, url: str) -> str:
    """Pick storage extension. Stems always wav; original keeps server format."""
    if kind != "original":
        return "wav"
    fmt = str(info.get("format") or "").lower().lstrip(".")
    if fmt in ("mp3", "wav", "flac", "m4a", "ogg", "opus", "aac"):
        return fmt
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    for ext in ("mp3", "wav", "flac", "m4a", "ogg", "opus", "aac"):
        if path.endswith(f".{ext}"):
            return ext
    return "wav"


def _find_existing_original(out_dir: Path) -> Path | None:
    for ext in ("wav", "mp3", "flac", "m4a", "ogg", "opus", "aac"):
        cand = out_dir / f"original.{ext}"
        if cand.is_file():
            return cand
    return None


async def _download_one(client: httpx.AsyncClient, item: dict[str, Any], sem: asyncio.Semaphore) -> None:
    song_id = str(item["song_id"])
    kind = str(item["kind"])
    info = item["info"]
    expected_sha = info.get("sha256")
    expected_size = int(info["size"]) if info.get("size") is not None else None
    url = _final_url(str(info["url"]))
    out_dir = CACHE_DIR / song_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = _choose_ext(kind, info, url)
    final_path = out_dir / f"{kind}.{ext}"

    # legacy: original.wav may already exist from old runs; treat as valid for original
    if kind == "original":
        existing = _find_existing_original(out_dir)
        if existing and _already_valid(existing, expected_sha, expected_size):
            await state.mark_done()
            return
    if _already_valid(final_path, expected_sha, expected_size):
        await state.mark_done()
        return

    async with sem:
        await state.mark_current(f"{song_id}/{kind}")
        tmp_path = out_dir / f".{kind}.download"
        url_has_token = ("token=" in url)
        req_headers = None if url_has_token else (_headers() or None)
        for attempt in range(1, 4):
            try:
                async with client.stream("GET", url, headers=req_headers) as resp:
                    resp.raise_for_status()
                    with tmp_path.open("wb") as f:
                        async for chunk in resp.aiter_bytes():
                            if chunk:
                                f.write(chunk)
                if expected_size is not None and tmp_path.stat().st_size != expected_size:
                    raise ValueError(f"size mismatch {song_id}/{kind}: got {tmp_path.stat().st_size}, want {expected_size}")
                if expected_sha and _sha256(tmp_path) != expected_sha:
                    raise ValueError(f"sha256 mismatch {song_id}/{kind}")
                # Phase A: store bytes as-is; audio-engine decodes via soundfile/ffmpeg
                tmp_path.replace(final_path)
                if expected_sha:
                    _sidecar(final_path).write_text(expected_sha + "\n", encoding="utf-8")
                await state.mark_done()
                return
            except Exception as exc:
                tmp_path.unlink(missing_ok=True)
                if attempt == 3:
                    message = f"{song_id}/{kind}: {exc}"
                    logger.error(message)
                    await state.add_error(message)
                    return
                await asyncio.sleep([1, 3, 9][attempt - 1])


async def _run_sync(manifest: dict[str, Any]) -> None:
    items = _file_items(manifest)
    await state.reset(len(items), manifest.get("plan_id"))
    if not items:
        await state.finish()
        return
    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        await asyncio.gather(*[_download_one(client, item, sem) for item in items])
    await state.finish()


@app.post("/sync")
async def sync(body: dict[str, Any]) -> dict[str, Any]:
    global _sync_task
    manifest = _manifest_from_body(body)
    if _sync_task and not _sync_task.done():
        return {"ok": False, "error": "sync already running", "status": await state.snapshot()}
    _sync_task = asyncio.create_task(_run_sync(manifest))
    report = _manifest_asset_report(manifest)
    return {"ok": True, "sync_started": True, "total": len(_file_items(manifest)), "manifest": report}


@app.get("/status")
async def status() -> dict[str, Any]:
    return await state.snapshot()
