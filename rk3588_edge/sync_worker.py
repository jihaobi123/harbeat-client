"""Sync worker — downloads manifest assets, verifies integrity, converts formats.

Responsibilities:
  1. Fetch manifest JSON from Jetson `/api/manifest/playlist/{id}`
  2. Download original + stems for every track
  3. sha256 integrity check on every file
  4. ffmpeg conversion to 44100 Hz stereo WAV when needed
  5. Report progress and errors to StateManager
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import aiohttp

from .config import DeckSide, PlaybackTier, get_config
from .state_manager import StateManager, get_state_manager

logger = logging.getLogger(__name__)

STEM_NAMES = ("vocals", "drums", "bass", "other")


class SyncWorker:
    """Async manifest download and verification worker."""

    def __init__(self):
        self._config = get_config()
        self._state: StateManager = get_state_manager()

    # ── Public API ────────────────────────────────────────────────────

    async def sync_plan(self, plan_id: str) -> dict[str, Any]:
        """Download and verify all assets for a mix plan.

        Returns: {"ok": bool, "downloaded": int, "errors": list[str]}
        """
        t0 = time.monotonic()
        await self._state.set_plan(plan_id)
        errors: list[str] = []
        downloaded = 0

        try:
            manifest = await self._fetch_manifest(plan_id)
        except Exception as exc:
            errors.append(f"Manifest fetch failed: {exc}")
            await self._state.set_sync_complete(False, errors)
            return {"ok": False, "downloaded": 0, "errors": errors}

        tracks = manifest.get("tracks", [])
        if not tracks:
            errors.append("Manifest contains no tracks")
            await self._state.set_sync_complete(False, errors)
            return {"ok": False, "downloaded": 0, "errors": errors}

        total = 0
        for track in tracks:
            song_id = track.get("songId") or track.get("librarySongId", "unknown")
            files = track.get("files", {})

            # Download original
            orig = files.get("original")
            if orig:
                ok, err = await self._download_file(
                    song_id, "original", orig["url"],
                    orig.get("sha256"), orig.get("size"),
                )
                if ok:
                    downloaded += 1
                else:
                    errors.append(err)
                total += 1

            # Download stems
            stems = files.get("stems", {})
            for stem_name in STEM_NAMES:
                stem_info = stems.get(stem_name)
                if not stem_info:
                    continue
                ok, err = await self._download_file(
                    song_id, f"stems/{stem_name}", stem_info["url"],
                    stem_info.get("sha256"), stem_info.get("size"),
                )
                if ok:
                    downloaded += 1
                else:
                    errors.append(err)
                total += 1

        # Determine tier after sync
        if total > 0 and downloaded == total:
            await self._state.set_sync_complete(True)
            # Check stem availability
            has_all_stems = all(
                self._config.cache_path(str(t.get("songId", "")), "stems", sn, f"{sn}.wav").exists()
                for t in tracks for sn in STEM_NAMES
                if t.get("files", {}).get("stems", {}).get(sn)
            )
            tier = PlaybackTier.stem_aware if has_all_stems else PlaybackTier.non_stem
            await self._state.set_tier(tier)
        else:
            await self._state.set_sync_complete(False, errors)

        elapsed = time.monotonic() - t0
        logger.info(
            "sync complete: plan=%s downloaded=%d/%d errors=%d elapsed=%.1fs",
            plan_id, downloaded, total, len(errors), elapsed,
        )
        return {"ok": len(errors) == 0, "downloaded": downloaded, "total": total,
                "errors": errors, "elapsed_sec": round(elapsed, 1)}

    # ── Internal ──────────────────────────────────────────────────────

    async def _fetch_manifest(self, plan_id: str) -> dict[str, Any]:
        url = f"{self._config.jetson_base_url}/manifest/playlist/{plan_id}"
        logger.info("fetching manifest: %s", url)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"HTTP {resp.status}: {text[:200]}")
                data = await resp.json()
                if not data.get("ok"):
                    raise RuntimeError(f"Manifest API error: {data}")
                manifest = data.get("manifest", data)
                return manifest

    async def _download_file(
        self, song_id: str, subpath: str, url: str,
        expected_sha256: str | None, expected_size: int | None,
    ) -> tuple[bool, str]:
        """Download a single file, verify, and convert if needed.

        Returns (ok, error_message).
        """
        dest_dir = self._config.cache_path(str(song_id), *subpath.split("/")[:-1])
        dest_dir.mkdir(parents=True, exist_ok=True)
        fname = subpath.split("/")[-1]
        if not fname.endswith(".wav"):
            fname = fname.rsplit(".", 1)[0] + ".wav"
        dest = dest_dir / fname

        # Skip if already downloaded and verified
        if dest.exists() and expected_sha256:
            existing_hash = self._sha256_file(str(dest))
            if existing_hash == expected_sha256:
                logger.debug("skip (verified): %s", dest)
                return True, ""

        # Size check
        if expected_size and expected_size > self._config.max_file_size_mb * 1024 * 1024:
            return False, f"{subpath}: size {expected_size} exceeds max {self._config.max_file_size_mb}MB"

        # Download
        tmp = dest.with_suffix(".tmp")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=self._config.download_timeout_sec)) as resp:
                    if resp.status != 200:
                        return False, f"{subpath}: HTTP {resp.status}"
                    content = await resp.read()

            tmp.write_bytes(content)

            # sha256 check
            if expected_sha256:
                actual = self._sha256_file(str(tmp))
                if actual != expected_sha256:
                    tmp.unlink(missing_ok=True)
                    return False, f"{subpath}: sha256 mismatch (expected={expected_sha256[:16]}..., got={actual[:16]}...)"

            # ffmpeg conversion to target format
            ok, err = self._convert_audio(str(tmp), str(dest))
            tmp.unlink(missing_ok=True)
            if not ok:
                return False, f"{subpath}: {err}"

            logger.info("downloaded: %s (%d bytes)", dest, dest.stat().st_size)
            return True, ""

        except asyncio.TimeoutError:
            tmp.unlink(missing_ok=True)
            return False, f"{subpath}: download timeout ({self._config.download_timeout_sec}s)"
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            return False, f"{subpath}: {exc}"

    def _convert_audio(self, src: str, dst: str) -> tuple[bool, str]:
        """Convert audio to 44100 Hz stereo WAV via ffmpeg."""
        ffmpeg = self._config.ffmpeg_bin
        try:
            result = subprocess.run(
                [
                    ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                    "-i", src,
                    "-ar", str(self._config.target_sample_rate),
                    "-ac", str(self._config.target_channels),
                    "-sample_fmt", "s16",
                    dst,
                ],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0 or not os.path.isfile(dst):
                return False, f"ffmpeg failed: {result.stderr.strip()[-200:]}"
            return True, ""
        except FileNotFoundError:
            return False, f"ffmpeg not found at '{ffmpeg}'"
        except subprocess.TimeoutExpired:
            return False, "ffmpeg conversion timeout (60s)"
        except Exception as exc:
            return False, f"ffmpeg error: {exc}"

    @staticmethod
    def _sha256_file(path: str) -> str:
        sha = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()
