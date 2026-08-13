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
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

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
REQUEST_TIMEOUT = httpx.Timeout(connect=10.0, read=180.0, write=60.0, pool=10.0)
CURL_MAX_TIME_SEC = int(os.environ.get("SYNC_CURL_MAX_TIME_SEC", "240"))
VERIFY_FULL_CACHE = os.environ.get("SYNC_VERIFY_FULL", "0") == "1"

app = FastAPI(title="Cypher Sync Worker", version="0.1.0")


class SyncState:
    def __init__(self) -> None:
        self.lock: asyncio.Lock | None = None
        self.running = False
        self.total = 0
        self.completed = 0
        self.downloaded = 0
        self.current_file: str | None = None
        self.percent = 0.0
        self.errors: list[str] = []
        self.plan_id: str | None = None
        self.file_timings: dict[str, dict[str, Any]] = {}

    async def reset(self, total: int, plan_id: str | None) -> None:
        async with self._lock():
            self.running = True
            self.total = total
            self.completed = 0
            self.downloaded = 0
            self.current_file = None
            self.percent = 0.0
            self.errors = []
            self.plan_id = plan_id
            self.file_timings = {}

    async def mark_current(self, name: str) -> None:
        async with self._lock():
            self.current_file = name

    async def mark_done(self) -> None:
        async with self._lock():
            self.completed += 1
            self.downloaded = self.completed
            self.percent = round((self.completed / self.total) * 100, 2) if self.total else 100.0

    async def add_error(self, message: str) -> None:
        async with self._lock():
            self.errors.append(message)

    async def update_file_timing(self, name: str, **changes: Any) -> None:
        async with self._lock():
            current = dict(self.file_timings.get(name) or {})
            current.update(changes)
            self.file_timings[name] = current

    async def finish(self) -> None:
        async with self._lock():
            self.running = False
            self.current_file = None
            if not self.errors and (self.total == 0 or self.completed >= self.total):
                self.percent = 100.0

    async def snapshot(self) -> dict[str, Any]:
        async with self._lock():
            return {
                "running": self.running,
                "plan_id": self.plan_id,
                "total": self.total,
                "downloaded": self.downloaded,
                "completed": self.completed,
                "current_file": self.current_file,
                "percent": self.percent,
                "errors": list(self.errors),
                "file_timings": {
                    key: dict(value) for key, value in self.file_timings.items()
                },
            }

    def _lock(self) -> asyncio.Lock:
        if self.lock is None:
            self.lock = asyncio.Lock()
        return self.lock


state = SyncState()
_sync_task: asyncio.Task | None = None
_download_locks: dict[str, asyncio.Lock] = {}


def _manifest_from_body(body: dict[str, Any]) -> dict[str, Any]:
    if "manifest" in body and isinstance(body["manifest"], dict):
        return _manifest_from_body(body["manifest"])
    if "data" in body and isinstance(body["data"], dict):
        return _manifest_from_body(body["data"])
    return body


def _file_items(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    tracks = manifest.get("tracks")
    if not isinstance(tracks, list):
        # Accept a single-song manifest directly as a convenience. The mobile
        # app normally wraps this in {"tracks": [...]}, but manual tests and
        # relay tools often post the song manifest itself.
        if isinstance(manifest.get("files"), dict):
            tracks = [manifest]
        else:
            tracks = []
    for track in tracks:
        song_id = (
            track.get("song_id")
            or track.get("library_song_id")
            or track.get("songId")
            or track.get("librarySongId")
            or track.get("id")
        )
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
    for pair in manifest.get("default_mix_pairs") or manifest.get("pairs") or []:
        if not isinstance(pair, dict):
            continue
        pair_id = pair.get("pair_id") or pair.get("id")
        if not pair_id:
            continue
        files = pair.get("files") or {}
        render = files.get("transition_render") or pair.get("transition_render")
        if render:
            items.append({"pair_id": pair_id, "kind": "transition_render", "info": render, "pair_meta": pair})
        meta = files.get("transition_render_meta") or pair.get("transition_render_meta")
        if meta:
            items.append({"pair_id": pair_id, "kind": "transition_render_meta", "info": meta, "pair_meta": pair})
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
    stat = path.stat()
    if VERIFY_FULL_CACHE and expected_sha:
        return _sha256(path) == expected_sha
    if expected_sha and _sidecar(path).is_file():
        raw = _sidecar(path).read_text(encoding="utf-8").strip()
        try:
            meta = json.loads(raw)
        except json.JSONDecodeError:
            meta = {"sha256": raw}
        if meta.get("converted_from_sha256") == expected_sha:
            source_size = meta.get("converted_from_size")
            if expected_size is not None and source_size is not None and int(source_size) != expected_size:
                return False
            sidecar_size = meta.get("size")
            sidecar_mtime = meta.get("mtime_ns")
            if sidecar_size is not None and int(sidecar_size) != stat.st_size:
                return False
            if sidecar_mtime is not None and int(sidecar_mtime) != stat.st_mtime_ns:
                return False
            return True
        if meta.get("sha256") == expected_sha:
            sidecar_size = meta.get("size")
            sidecar_mtime = meta.get("mtime_ns")
            if sidecar_size is not None and int(sidecar_size) != stat.st_size:
                return False
            if sidecar_mtime is not None and int(sidecar_mtime) != stat.st_mtime_ns:
                return False
            return True
    if _sidecar(path).is_file():
        try:
            meta = json.loads(_sidecar(path).read_text(encoding="utf-8").strip())
        except (json.JSONDecodeError, OSError):
            meta = {}
        source_size = meta.get("converted_from_size")
        if expected_size is not None and source_size is not None:
            if int(source_size) != expected_size:
                return False
            sidecar_size = meta.get("size")
            sidecar_mtime = meta.get("mtime_ns")
            if sidecar_size is not None and int(sidecar_size) != stat.st_size:
                return False
            if sidecar_mtime is not None and int(sidecar_mtime) != stat.st_mtime_ns:
                return False
            return True
    if expected_size is not None and stat.st_size != expected_size:
        return False
    if expected_sha:
        return _sha256(path) == expected_sha
    return True


def _pair_meta_matches_manifest(out_dir: Path, pair_meta: dict[str, Any] | None) -> bool:
    if not pair_meta:
        return True
    meta_path = out_dir / "transition_render_meta.json"
    if not meta_path.is_file():
        return False
    try:
        local = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    checks = {
        "planner_version": pair_meta.get("planner_version"),
        "audio_feature_source": pair_meta.get("audio_feature_source"),
        "render_strategy": pair_meta.get("render_strategy"),
    }
    expected_renderer = pair_meta.get("renderer_version") or pair_meta.get("required_renderer_version")
    if expected_renderer:
        checks["renderer_version"] = expected_renderer
    for key, expected in checks.items():
        if expected is None or expected == "":
            continue
        actual = local.get(key)
        if actual != expected:
            return False
    return True


def _invalidate_stale_pair_caches(items: list[dict[str, Any]]) -> None:
    """Remove an incompatible pair cache once, before parallel downloads."""
    checked: set[str] = set()
    for item in items:
        pair_id = item.get("pair_id")
        if not pair_id or str(pair_id) in checked:
            continue
        checked.add(str(pair_id))
        pair_meta = item.get("pair_meta") if isinstance(item.get("pair_meta"), dict) else None
        out_dir = _safe_pair_dir(str(pair_id))
        if _pair_meta_matches_manifest(out_dir, pair_meta):
            continue
        for stale in out_dir.glob("transition_render*"):
            try:
                stale.unlink()
            except OSError:
                pass


def _needs_wav_conversion(info: dict[str, Any]) -> bool:
    fmt = str(info.get("format") or "").lower()
    url = str(info.get("url") or "").lower()
    return fmt not in ("", "wav", "wave") and not url.endswith(".wav")


def _convert_to_wav(src: Path, dst: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found; cannot convert original audio to wav")
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
    """Pick storage extension.

    Keep the server format for both originals and stems. Jetson usually serves
    mp3, and audio-engine can locate/decode mp3 directly; forcing stems to wav
    here can create mp3 bytes with a .wav suffix and break stem-aware playback.
    """
    fmt = str(info.get("format") or "").lower().lstrip(".")
    if fmt in ("mp3", "wav", "flac", "m4a", "ogg", "opus", "aac"):
        return fmt
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    for ext in ("mp3", "wav", "flac", "m4a", "ogg", "opus", "aac"):
        if path.endswith(f".{ext}"):
            return ext
    return "wav"


_AUDIO_EXTS = ("wav", "mp3", "flac", "m4a", "ogg", "opus", "aac")


def _find_existing_original(out_dir: Path) -> Path | None:
    for ext in _AUDIO_EXTS:
        cand = out_dir / f"original.{ext}"
        if cand.is_file():
            return cand
    return None


def _find_existing_asset(out_dir: Path, kind: str, required_format: str | None = None) -> Path | None:
    if kind == "original":
        fmt = (required_format or "").lower().lstrip(".")
        if fmt in _AUDIO_EXTS:
            cand = out_dir / f"original.{fmt}"
            return cand if cand.is_file() else None
        return _find_existing_original(out_dir)
    if kind not in ("vocals", "drums", "bass", "other"):
        return None
    fmt = (required_format or "").lower().lstrip(".")
    exts = (fmt,) if fmt in _AUDIO_EXTS else _AUDIO_EXTS
    for ext in exts:
        cand = out_dir / f"{kind}.{ext}"
        if cand.is_file():
            return cand
    return None


def _safe_song_dir(song_id: str) -> Path:
    if not song_id.strip():
        raise ValueError("empty song_id")
    cache_root = CACHE_DIR.resolve()
    target = (CACHE_DIR / song_id).resolve()
    if target == cache_root or cache_root not in target.parents:
        raise ValueError(f"invalid song_id path: {song_id}")
    return target


def _safe_pair_dir(pair_id: str) -> Path:
    if not pair_id.strip():
        raise ValueError("empty pair_id")
    cache_root = CACHE_DIR.resolve()
    target = (CACHE_DIR / "default-mix" / "pairs" / pair_id).resolve()
    if cache_root not in target.parents:
        raise ValueError(f"invalid pair_id path: {pair_id}")
    return target


def _download_lock(path: Path) -> asyncio.Lock:
    key = str(path.resolve())
    lock = _download_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _download_locks[key] = lock
    return lock


def _curl_command(url: str, path: Path, headers: dict[str, str] | None) -> list[str]:
    curl = shutil.which("curl")
    if not curl:
        raise RuntimeError("curl not found")
    cmd = [
        curl,
        "-L",
        "--fail",
        "--connect-timeout",
        "10",
        "--max-time",
        str(CURL_MAX_TIME_SEC),
        "--speed-time",
        "45",
        "--speed-limit",
        "1",
        "-o",
        str(path),
    ]
    for key, value in (headers or {}).items():
        cmd.extend(["-H", f"{key}: {value}"])
    cmd.append(url)
    return cmd


async def _download_with_curl_async(
    url: str,
    path: Path,
    headers: dict[str, str] | None,
) -> None:
    proc = await asyncio.create_subprocess_exec(
        *_curl_command(url, path, headers),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _stdout, stderr = await proc.communicate()
    except asyncio.CancelledError:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        raise
    if proc.returncode != 0:
        message = stderr.decode(errors="replace").strip()
        raise RuntimeError(f"curl failed rc={proc.returncode}: {message}")


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _write_sidecar_atomic(path: Path, payload: dict[str, Any]) -> None:
    sidecar = _sidecar(path)
    tmp = sidecar.with_name(f".{sidecar.name}.{uuid.uuid4().hex}.part")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
        _fsync_file(tmp)
        os.replace(tmp, sidecar)
    finally:
        tmp.unlink(missing_ok=True)


def _pair_cache_ready(pair_id: str) -> tuple[bool, str | None]:
    out_dir = _safe_pair_dir(pair_id)
    render = out_dir / "transition_render.wav"
    meta = out_dir / "transition_render_meta.json"
    if not render.is_file():
        return False, "render_missing"
    try:
        if render.stat().st_size <= 44:
            return False, "render_empty"
    except OSError:
        return False, "render_unreadable"
    if not meta.is_file():
        return False, "meta_missing"
    try:
        if meta.stat().st_size <= 2:
            return False, "meta_empty"
        payload = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, "meta_invalid"
    if not isinstance(payload, dict):
        return False, "meta_invalid"
    meta_pair_id = payload.get("pair_id")
    if meta_pair_id not in (None, "") and str(meta_pair_id) != pair_id:
        return False, "meta_pair_mismatch"
    return True, None


async def _download_with_httpx(
    client: httpx.AsyncClient,
    url: str,
    path: Path,
    headers: dict[str, str] | None,
) -> dict[str, Any]:
    started = time.monotonic()
    first_byte_sec: float | None = None
    downloaded = 0
    async with client.stream("GET", url, headers=headers) as resp:
        resp.raise_for_status()
        with path.open("wb") as f:
            async for chunk in resp.aiter_bytes():
                if chunk:
                    if first_byte_sec is None:
                        first_byte_sec = time.monotonic() - started
                    f.write(chunk)
                    downloaded += len(chunk)
    return {
        "first_byte_sec": round(first_byte_sec, 4) if first_byte_sec is not None else None,
        "bytes": downloaded,
    }


async def _download_one(client: httpx.AsyncClient, item: dict[str, Any], sem: asyncio.Semaphore) -> None:
    song_id = str(item.get("song_id") or item.get("pair_id") or "")
    kind = str(item["kind"])
    info = item["info"]
    expected_sha = info.get("sha256")
    expected_size = int(info["size"]) if info.get("size") is not None else None
    url = _final_url(str(info["url"]))
    out_dir = _safe_pair_dir(str(item["pair_id"])) if "pair_id" in item else _safe_song_dir(song_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = _choose_ext(kind, info, url)
    if kind == "transition_render_meta":
        ext = "json"
    final_path = out_dir / f"{kind}.{ext}"
    timing_name = f"{song_id}/{kind}"
    timing_started = time.monotonic()
    await state.update_file_timing(
        timing_name,
        kind=kind,
        url_host=urlparse(url).hostname or "",
        expected_bytes=expected_size,
        started_at=datetime.now(timezone.utc).isoformat(),
        attempts=0,
        cached=False,
        complete=False,
        error=None,
    )

    # legacy: original.wav may already exist from old runs; treat as valid for original
    if kind == "original":
        existing = _find_existing_asset(out_dir, "original", ext)
        if existing and _already_valid(existing, expected_sha, expected_size):
            await state.update_file_timing(
                timing_name,
                bytes=existing.stat().st_size,
                download_sec=0.0,
                verify_sec=0.0,
                transport="cache",
                cached=True,
                complete=True,
            )
            await state.mark_done()
            return
    if _already_valid(final_path, expected_sha, expected_size):
        await state.update_file_timing(
            timing_name,
            bytes=final_path.stat().st_size,
            download_sec=0.0,
            verify_sec=0.0,
            transport="cache",
            cached=True,
            complete=True,
        )
        await state.mark_done()
        return

    async with sem, _download_lock(final_path):
        if _already_valid(final_path, expected_sha, expected_size):
            await state.update_file_timing(
                timing_name,
                bytes=final_path.stat().st_size,
                download_sec=0.0,
                verify_sec=0.0,
                transport="cache",
                cached=True,
                complete=True,
            )
            await state.mark_done()
            return
        await state.mark_current(timing_name)
        tmp_path = out_dir / f".{kind}.{uuid.uuid4().hex}.part"
        url_has_token = "token=" in url
        req_headers = None if url_has_token else (_headers() or None)
        try:
            for attempt in range(1, 4):
                await state.update_file_timing(timing_name, attempts=attempt)
                try:
                    attempt_started = time.monotonic()
                    transport = "httpx"
                    transfer: dict[str, Any] | None = None
                    try:
                        transfer = await _download_with_httpx(client, url, tmp_path, req_headers)
                    except asyncio.CancelledError:
                        raise
                    except Exception as httpx_exc:
                        logger.warning("%s/%s httpx download failed, fallback to curl: %r", song_id, kind, httpx_exc)
                        transport = "curl"
                        await _download_with_curl_async(url, tmp_path, req_headers)
                    download_sec = time.monotonic() - attempt_started
                    verify_started = time.monotonic()
                    if expected_size is not None and tmp_path.stat().st_size != expected_size:
                        raise ValueError(f"size mismatch {song_id}/{kind}: got {tmp_path.stat().st_size}, want {expected_size}")
                    if expected_sha and _sha256(tmp_path) != expected_sha:
                        raise ValueError(f"sha256 mismatch {song_id}/{kind}")
                    head = b""
                    try:
                        with tmp_path.open("rb") as fh:
                            head = fh.read(3)
                    except OSError:
                        pass
                    is_mp3 = head[:3] == b"ID3" or (
                        len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0
                    )
                    source_size = tmp_path.stat().st_size
                    verify_sec = time.monotonic() - verify_started
                    published_path = final_path.with_suffix(".mp3") if final_path.suffix.lower() == ".wav" and is_mp3 else final_path
                    _fsync_file(tmp_path)
                    os.replace(tmp_path, published_path)
                    if expected_sha:
                        stat = published_path.stat()
                        _write_sidecar_atomic(
                            published_path,
                            {
                                "size": stat.st_size,
                                "mtime_ns": stat.st_mtime_ns,
                                "source_size": source_size,
                                "sha256": expected_sha,
                            },
                        )
                    await state.update_file_timing(
                        timing_name,
                        bytes=source_size,
                        first_byte_sec=(transfer or {}).get("first_byte_sec"),
                        download_sec=round(download_sec, 4),
                        verify_sec=round(verify_sec, 4),
                        total_sec=round(time.monotonic() - timing_started, 4),
                        transport=transport,
                        complete=True,
                        error=None,
                    )
                    await state.mark_done()
                    return
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    tmp_path.unlink(missing_ok=True)
                    if attempt == 3:
                        message = f"{song_id}/{kind}: {exc!r}"
                        logger.error(message)
                        await state.update_file_timing(
                            timing_name,
                            bytes=tmp_path.stat().st_size if tmp_path.exists() else 0,
                            total_sec=round(time.monotonic() - timing_started, 4),
                            complete=False,
                            error=repr(exc),
                        )
                        await state.add_error(message)
                        return
                    await asyncio.sleep([1, 3, 9][attempt - 1])
        finally:
            tmp_path.unlink(missing_ok=True)


async def _run_sync(
    manifest: dict[str, Any],
    *,
    items: list[dict[str, Any]] | None = None,
    state_initialized: bool = False,
) -> None:
    items = items if items is not None else _file_items(manifest)
    if not state_initialized:
        await state.reset(len(items), manifest.get("plan_id"))
    try:
        if not items:
            return
        _invalidate_stale_pair_caches(items)
        sem = asyncio.Semaphore(MAX_CONCURRENCY)
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            await asyncio.gather(*[_download_one(client, item, sem) for item in items])
    finally:
        # A manual fast cut can cancel a rolling preparation. Do not leave the
        # single-worker state marked as running after that cancellation.
        await state.finish()


@app.post("/sync")
async def sync(body: dict[str, Any]) -> dict[str, Any]:
    global _sync_task
    manifest = _manifest_from_body(body)
    priority = bool(body.get("priority"))
    if _sync_task and not _sync_task.done():
        if not priority:
            return {"ok": False, "error": "sync already running", "status": await state.snapshot()}
        # Replace a rolling transfer and publish the manual plan atomically.
        # A later ordinary /sync can only observe this new task as busy.
        task = _sync_task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        _sync_task = None
    items = _file_items(manifest)
    # Publish this plan before returning so an immediate /status request
    # cannot observe the previous completed sync.
    await state.reset(len(items), manifest.get("plan_id"))
    _sync_task = asyncio.create_task(
        _run_sync(manifest, items=items, state_initialized=True)
    )
    wait_for_completion = bool(body.get("wait"))
    if wait_for_completion:
        await _sync_task
    report = _manifest_asset_report(manifest)
    return {
        "ok": True,
        "sync_started": True,
        "sync_completed": wait_for_completion,
        "plan_id": manifest.get("plan_id"),
        "total": len(items),
        "manifest": report,
        "status": await state.snapshot(),
    }


@app.post("/sync/cancel")
async def cancel_sync() -> dict[str, Any]:
    """Cancel the current low-priority transfer for a manual fast cut."""
    global _sync_task
    task = _sync_task
    if task is None or task.done():
        return {"ok": True, "cancelled": False, "status": await state.snapshot()}
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    return {"ok": True, "cancelled": True, "status": await state.snapshot()}


@app.get("/status")
async def status() -> dict[str, Any]:
    return await state.snapshot()


@app.get("/cache/check")
async def cache_check(
    song_id: str | None = None,
    kind: str = "original",
    format: str | None = None,
    pair_id: str | None = None,
) -> dict[str, Any]:
    if pair_id:
        exists, reason = _pair_cache_ready(pair_id)
        render = _safe_pair_dir(pair_id) / "transition_render.wav"
        return {
            "ok": True,
            "exists": exists,
            "pair_id": pair_id,
            "kind": "default_mix_pair",
            "path": str(render) if exists else None,
            "reason": reason,
        }
    if not song_id:
        raise ValueError("song_id or pair_id is required")
    out_dir = _safe_song_dir(song_id)
    normalized_kind = (kind or "original").lower().lstrip(".")
    requested_format = (format or "").lower().lstrip(".")
    if not out_dir.is_dir():
        return {"ok": True, "exists": False, "kind": normalized_kind, "format": requested_format or None}
    found = _find_existing_asset(out_dir, normalized_kind, requested_format)
    if not found:
        return {"ok": True, "exists": False, "kind": normalized_kind, "format": requested_format or None}
    try:
        size = found.stat().st_size
    except OSError:
        size = 0
    return {
        "ok": True,
        "exists": True,
        "kind": normalized_kind,
        "format": requested_format or None,
        "path": str(found),
        "size": size,
        "ext": found.suffix.lstrip("."),
    }


@app.delete("/cache/song/{song_id}")
async def delete_song_cache(song_id: str) -> dict[str, Any]:
    out_dir = _safe_song_dir(song_id)
    if not out_dir.exists():
        return {"ok": True, "deleted": False, "song_id": song_id}
    if not out_dir.is_dir():
        raise ValueError(f"cache path is not a directory: {out_dir}")
    shutil.rmtree(out_dir)
    return {"ok": True, "deleted": True, "song_id": song_id}
