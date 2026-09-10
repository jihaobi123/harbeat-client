"""Jetson same-style preprocessing and immutable NAS publication.

This module deliberately has no database dependency.  It converts one audio
file into the public same-style preprocessing contract and publishes only
relative storage keys under one configured NAS root.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any, Callable, Iterator, Mapping
import uuid


SCHEMA_NAME = "same_style_track_preprocess"
SCHEMA_VERSION = "1.1.0"
CONTRACT_VERSION = "same-style-preprocess-v1.1"
PIPELINE_VERSION = "same_style_preprocess_pipeline_v1"
STEM_NAMES = ("vocals", "drums", "bass", "other")
DRUM_STEM_NAMES = ("kick", "snare", "hihat", "tom", "cymbal")
STATUS_VALUES = {"ready", "degraded", "unavailable"}
_TRACK_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class PreprocessError(RuntimeError):
    """Raised when one required preprocessing or publication step fails."""


@dataclass(frozen=True)
class PreprocessConfig:
    root: Path
    git_sha: str
    device: str = "cuda"
    demucs_model: str = "htdemucs"
    require_mdx23c: bool = True
    lock_stale_seconds: int = 6 * 60 * 60

    @classmethod
    def from_values(
        cls,
        *,
        root: str | os.PathLike[str],
        git_sha: str,
        device: str = "cuda",
        demucs_model: str = "htdemucs",
        require_mdx23c: bool = True,
    ) -> "PreprocessConfig":
        return cls(
            root=Path(root).expanduser().resolve(),
            git_sha=str(git_sha).strip(),
            device=str(device).strip() or "cuda",
            demucs_model=str(demucs_model).strip() or "htdemucs",
            require_mdx23c=bool(require_mdx23c),
        )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with temporary.open("wb") as handle:
        handle.write(_json_bytes(payload))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _validate_track_id(track_id: str) -> str:
    value = str(track_id).strip()
    if not _TRACK_ID_PATTERN.fullmatch(value):
        raise ValueError(
            "track_id must start with an alphanumeric character and contain only "
            "letters, numbers, dot, underscore, or dash (maximum 128 characters)"
        )
    return value


def _storage_key(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise PreprocessError(f"asset is outside preprocessing root: {resolved}") from exc
    if relative.is_absolute() or ".." in relative.parts:
        raise PreprocessError(f"unsafe storage key: {relative}")
    return relative.as_posix()


def _seconds_to_ms(value: Any, *, minimum: int = 0) -> int:
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        seconds = 0.0
    return max(minimum, int(round(seconds * 1000.0)))


def _score(value: Any, *, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return round(min(1.0, max(0.0, number)), 4)


def _probe_audio(path: Path) -> dict[str, int]:
    try:
        import soundfile as sf

        info = sf.info(path)
        if info.frames > 0 and info.samplerate > 0:
            return {
                "duration_ms": max(1, int(round(float(info.duration) * 1000.0))),
                "sample_rate_hz": int(info.samplerate),
                "channels": int(info.channels),
            }
    except Exception:
        pass
    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=sample_rate,channels:format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        payload = json.loads(completed.stdout)
        stream = (payload.get("streams") or [{}])[0]
        duration = float((payload.get("format") or {}).get("duration"))
        return {
            "duration_ms": max(1, int(round(duration * 1000.0))),
            "sample_rate_hz": int(stream["sample_rate"]),
            "channels": int(stream["channels"]),
        }
    except Exception as exc:
        raise PreprocessError(f"unable to probe audio asset {path}: {exc}") from exc


def _content_type(path: Path) -> str:
    guessed = mimetypes.guess_type(path.name)[0]
    if guessed:
        return guessed
    return {".wav": "audio/wav", ".flac": "audio/flac", ".mp3": "audio/mpeg"}.get(
        path.suffix.lower(), "application/octet-stream"
    )


def _safe_storage_key(value: str) -> str:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts or not value:
        raise PreprocessError(f"unsafe storage key: {value}")
    return candidate.as_posix()


def _asset(root: Path, path: Path, *, published_storage_key: str | None = None) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise PreprocessError(f"audio asset is missing or empty: {path}")
    return {
        "storage_key": (
            _safe_storage_key(published_storage_key)
            if published_storage_key is not None
            else _storage_key(root, path)
        ),
        "sha256": _sha256(path),
        "size_bytes": int(path.stat().st_size),
        "content_type": _content_type(path),
        **_probe_audio(path),
    }


def _event_time(item: Any) -> float | None:
    value = item.get("time", item.get("start")) if isinstance(item, Mapping) else item
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _deduplicate_events(values: list[Any], *, tolerance: float = 0.03) -> list[Any]:
    ordered = sorted(
        ((timestamp, item) for item in values if (timestamp := _event_time(item)) is not None),
        key=lambda pair: pair[0],
    )
    retained: list[tuple[float, Any]] = []
    for timestamp, item in ordered:
        if not retained or timestamp - retained[-1][0] > tolerance:
            retained.append((timestamp, item))
    return [item for _, item in retained]


def _dominant_pattern(events: list[Any], bars: list[float], symbol: str) -> str | None:
    if len(bars) < 2:
        return None
    counts = [0] * 16
    valid_bars = 0
    event_times = [value for item in events if (value := _event_time(item)) is not None]
    for start, end in zip(bars[:-1], bars[1:]):
        duration = end - start
        if duration <= 0:
            continue
        valid_bars += 1
        occupied = {
            min(15, max(0, int(round((value - start) / duration * 16.0))))
            for value in event_times
            if start <= value < end
        }
        for index in occupied:
            counts[index] += 1
    if not valid_bars:
        return None
    threshold = max(1, int(round(valid_bars * 0.35)))
    return "".join(symbol if value >= threshold else "." for value in counts)


def _subtypes(events: list[Any], fallbacks: list[str]) -> list[str]:
    values = {
        str(item.get("subtype") or item.get("input_subtype") or item.get("input_class")).strip()
        for item in events
        if isinstance(item, Mapping)
        and (item.get("subtype") or item.get("input_subtype") or item.get("input_class"))
    }
    return sorted(values) or fallbacks


def _feature_score(feature: Any) -> float:
    if not isinstance(feature, Mapping):
        return 0.0
    return _score(feature.get("calibrated_score", feature.get("score", 0.0)))


def _build_drum_groups(stem_analysis: Mapping[str, Any], bars: list[float]) -> dict[str, Any]:
    drum = dict(stem_analysis.get("drum_analysis") or {})
    drum_events = dict(drum.get("events") or {})
    modules = dict((stem_analysis.get("feature_analysis") or {}).get("analysis_modules") or {})
    bass_module = dict(modules.get("bass") or {})
    percussion_module = dict(modules.get("percussion") or {})
    bass_events = _deduplicate_events(list(bass_module.get("events") or []))
    percussion_events = _deduplicate_events(
        list(drum_events.get("tom") or [])
        + list(drum_events.get("cymbal") or [])
        + list(percussion_module.get("events") or [])
    )
    grouped = {
        "kick": list(drum_events.get("kick") or []),
        "snare_clap": list(drum_events.get("snare") or []),
        "hihat": list(drum_events.get("hihat") or []),
        "bass_808": bass_events,
        "percussion": percussion_events,
    }
    symbols = {"kick": "K", "snare_clap": "S", "hihat": "H", "bass_808": "B", "percussion": "P"}
    fallbacks = {
        "kick": ["kick"],
        "snare_clap": ["snare_or_clap"],
        "hihat": ["hihat_family"],
        "bass_808": ["bass"],
        "percussion": ["tom_or_cymbal_or_percussion"],
    }
    drum_status = str(drum.get("status") or "unavailable")
    bass_status = str(bass_module.get("status") or "unavailable")
    percussion_status = str(percussion_module.get("status") or "unavailable")
    statuses = {
        "kick": drum_status,
        "snare_clap": drum_status,
        "hihat": drum_status,
        "bass_808": bass_status,
        "percussion": percussion_status,
    }
    low_features = dict(bass_module.get("features") or {})
    if _feature_score(low_features.get("808_timbre_candidate")) >= 0.5:
        fallbacks["bass_808"] = ["bass", "808_timbre_candidate"]
    output: dict[str, Any] = {
        "version": "same_style_drum_groups_v1",
        "status": "ready",
        "quality_flags": sorted(
            set(
                list(drum.get("quality_flags") or [])
                + list(bass_module.get("quality_flags") or [])
                + list(percussion_module.get("quality_flags") or [])
            )
        ),
    }
    for name, events in grouped.items():
        status = statuses[name] if statuses[name] in STATUS_VALUES else "unavailable"
        output[name] = {
            "status": status,
            "present": (len(events) > 0) if status != "unavailable" else None,
            "event_count": len(events) if status != "unavailable" else None,
            "subtypes": _subtypes(events, fallbacks[name]) if events else [],
            "pattern_16": _dominant_pattern(events, bars, symbols[name]),
        }
    group_statuses = [output[name]["status"] for name in grouped]
    if "unavailable" in group_statuses:
        output["status"] = "unavailable"
    elif "degraded" in group_statuses or output["quality_flags"]:
        output["status"] = "degraded"
    return output


def _section_items(core: Mapping[str, Any]) -> tuple[str, bool, list[dict[str, Any]]]:
    analysis = dict(core.get("section_analysis") or {})
    fallback = bool(analysis.get("fallback_used"))
    source = "all_in_one_fallback" if fallback else "songformer"
    items = []
    for value in analysis.get("functional_segments") or []:
        try:
            start = _seconds_to_ms(value["start"])
            end = _seconds_to_ms(value["end"], minimum=1)
            label = str(value["label"]).strip().lower()
        except (KeyError, TypeError, ValueError):
            continue
        if label and end > start:
            confidence = value.get("confidence", value.get("score"))
            items.append(
                {
                    "start_ms": start,
                    "end_ms": end,
                    "label": label,
                    "confidence": None if confidence is None else _score(confidence),
                }
            )
    return source, fallback, items


def _transition_windows(core: Mapping[str, Any]) -> list[dict[str, Any]]:
    output = []
    for value in core.get("transition_windows") or []:
        start = _seconds_to_ms(value.get("start"))
        end = _seconds_to_ms(value.get("end"), minimum=1)
        if end <= start:
            continue
        score_in = _score(value.get("mix_in_score", 0.0))
        score_out = _score(value.get("mix_out_score", 0.0))
        role = "both" if min(score_in, score_out) >= 0.7 else ("in" if score_in >= score_out else "out")
        output.append(
            {"start_ms": start, "end_ms": end, "role": role, "confidence": max(score_in, score_out)}
        )
    return output


def _manifest(
    *,
    config: PreprocessConfig,
    source: Path,
    source_sha256: str,
    track_id: str,
    run_id: str,
    title: str | None,
    artist: str | None,
    master: Path,
    stems: Mapping[str, Path],
    drum_stems: Mapping[str, Path],
    core: Mapping[str, Any],
    stem_analysis: Mapping[str, Any],
) -> dict[str, Any]:
    section_source, fallback_used, sections = _section_items(core)
    beats = [float(value) for value in core.get("beat_points") or []]
    bars = [float(value) for value in core.get("downbeats") or []]
    drum_groups = _build_drum_groups(stem_analysis, bars)
    section_status = "ready" if sections and not fallback_used else ("degraded" if sections else "unavailable")
    core_status = "ready" if core.get("bpm") and beats else "unavailable"
    stem_status = "ready" if all(name in stems for name in STEM_NAMES) else "unavailable"
    mdx_status = "ready" if all(name in drum_stems for name in DRUM_STEM_NAMES) else "unavailable"
    modules = {
        "core": core_status,
        "sections": section_status,
        "stem_separation": stem_status,
        "mdx23c": mdx_status,
        "drum_groups": drum_groups["status"],
    }
    quality_flags = sorted(
        set(
            list(drum_groups.get("quality_flags") or [])
            + (["songformer_fallback_used"] if fallback_used else [])
            + (["sections_unavailable"] if not sections else [])
        )
    )
    if "unavailable" in modules.values():
        status = "unavailable" if core_status == "unavailable" or stem_status == "unavailable" else "degraded"
    elif "degraded" in modules.values() or quality_flags:
        status = "degraded"
    else:
        status = "ready"
    signature = dict(core.get("time_signature") or {})
    energy_curve = [
        {
            "start_ms": _seconds_to_ms(value.get("start")),
            "end_ms": _seconds_to_ms(value.get("end"), minimum=1),
            "value": _score(value.get("relative_energy", value.get("energy", 0.0))),
        }
        for value in core.get("energy_curve") or []
        if _seconds_to_ms(value.get("end"), minimum=1) > _seconds_to_ms(value.get("start"))
    ]
    run_storage_root = f"published/tracks/{track_id}/runs/{run_id}"
    return {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "track_id": track_id,
        "analysis_run_id": run_id,
        "generated_at": _utc_now(),
        "status": status,
        "source": {
            "input_sha256": source_sha256,
            "duration_ms": _probe_audio(master)["duration_ms"],
            "original_filename": source.name,
            "title": title,
            "artist": artist,
        },
        "pipeline": {
            "git_sha": config.git_sha,
            "core": "songformer_sections_v1",
            "sections": "songformer",
            "stem_separation": config.demucs_model,
            "drum_subseparation": "mdx23c_drumsep_6stem" if drum_stems else None,
            "drum_groups": "same_style_drum_groups_v1",
        },
        "assets": {
            "master": _asset(
                config.root,
                master,
                published_storage_key=f"{run_storage_root}/audio/{master.name}",
            ),
            "stems": {
                name: _asset(
                    config.root,
                    Path(stems[name]),
                    published_storage_key=f"{run_storage_root}/audio/stems/{name}.wav",
                )
                for name in STEM_NAMES
            },
            "drum_stems": {
                "status": mdx_status,
                **{
                    name: _asset(
                        config.root,
                        Path(drum_stems[name]),
                        published_storage_key=f"{run_storage_root}/audio/drums/{name}.wav",
                    )
                    if name in drum_stems
                    else None
                    for name in DRUM_STEM_NAMES
                },
            },
        },
        "analysis": {
            "tempo": {
                "bpm": float(core.get("bpm") or 0.0),
                "confidence": _score(core.get("beat_confidence")),
                "stability": None if core.get("tempo_stability") is None else _score(core.get("tempo_stability")),
                "needs_review": bool(core.get("beat_needs_review")),
            },
            "beat_grid": {
                "unit": "ms",
                "beats_ms": [_seconds_to_ms(value) for value in beats],
                "downbeats_ms": [_seconds_to_ms(value) for value in bars],
                "bars_ms": [_seconds_to_ms(value) for value in bars],
                "time_signature": {
                    "numerator": signature.get("numerator"),
                    "denominator": signature.get("denominator"),
                },
                "needs_review": bool(core.get("beat_needs_review") or signature.get("needs_review")),
            },
            "key": {
                "name": core.get("key"),
                "camelot": core.get("camelot_key"),
                "confidence": _score(core.get("key_confidence")),
                "needs_review": bool((core.get("key_profile") or {}).get("needs_review")),
            },
            "sections": {
                "version": "songformer_sections_v1",
                "source": section_source,
                "fallback_used": fallback_used,
                "items": sections,
            },
            "energy": {"overall": _score(core.get("energy")), "curve": energy_curve},
            "drum_groups": drum_groups,
            "transition_windows": _transition_windows(core),
        },
        "quality": {
            "needs_review": status != "ready" or bool(quality_flags),
            "quality_flags": quality_flags,
            "modules": modules,
        },
    }


def _validate_manifest(manifest: Mapping[str, Any], schema_path: Path) -> None:
    try:
        import jsonschema
    except ImportError as exc:
        raise PreprocessError("jsonschema is required by the NAS publisher") from exc
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(manifest)
    except Exception as exc:
        raise PreprocessError(f"manifest schema validation failed: {exc}") from exc


@contextmanager
def _track_lock(root: Path, track_id: str, stale_seconds: int) -> Iterator[None]:
    lock = root / "locks" / f"{track_id}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists() and time.time() - lock.stat().st_mtime > stale_seconds:
        stale = root / "failed" / f"stale-lock-{track_id}-{int(time.time())}.json"
        stale.parent.mkdir(parents=True, exist_ok=True)
        os.replace(lock, stale)
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    except FileExistsError as exc:
        raise PreprocessError(f"track is already being processed: {track_id}") from exc
    try:
        os.write(descriptor, _json_bytes({"track_id": track_id, "pid": os.getpid(), "created_at": _utc_now()}))
        os.close(descriptor)
        yield
    finally:
        active_attempt = staging
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


CoreRunner = Callable[[str], Mapping[str, Any]]
StemAnalyzer = Callable[..., Mapping[str, Any]]
DemucsRunner = Callable[[Path, Path, PreprocessConfig], Mapping[str, Path]]
MdxRunner = Callable[[Path, Path, PreprocessConfig], Mapping[str, Path]]


def _run_demucs(source: Path, work_dir: Path, config: PreprocessConfig) -> Mapping[str, Path]:
    command = [
        sys.executable,
        "-m",
        "demucs",
        "-n",
        config.demucs_model,
        "-d",
        config.device,
        "-o",
        str(work_dir),
        str(source),
    ]
    subprocess.run(command, check=True, timeout=3600)
    output = work_dir / config.demucs_model / source.stem
    result = {name: output / f"{name}.wav" for name in STEM_NAMES}
    missing = [name for name, path in result.items() if not path.is_file()]
    if missing:
        raise PreprocessError(f"Demucs omitted required stems: {missing}")
    return result


def _run_mdx23c(source: Path, output_dir: Path, config: PreprocessConfig) -> Mapping[str, Path]:
    from music_analysis.drum_analysis.mdx23c_separator import MDX23CDrumSeparator

    cache_dir = os.getenv("HARBEAT_MDX23C_CACHE_DIR")
    separator = MDX23CDrumSeparator(device=config.device, cache_dir=cache_dir)
    return separator.separate(source, output_dir)


def run_same_style_preprocess(
    source_path: str | os.PathLike[str],
    track_id: str,
    *,
    config: PreprocessConfig,
    schema_path: str | os.PathLike[str],
    title: str | None = None,
    artist: str | None = None,
    core_runner: CoreRunner | None = None,
    stem_analyzer: StemAnalyzer | None = None,
    demucs_runner: DemucsRunner | None = None,
    mdx_runner: MdxRunner | None = None,
) -> dict[str, Any]:
    """Analyze one song and atomically publish a versioned NAS run."""
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    track_id = _validate_track_id(track_id)
    if len(config.git_sha) < 7:
        raise ValueError("git_sha must contain at least seven characters")
    schema = Path(schema_path).expanduser().resolve()
    source_sha = _sha256(source)
    run_id = f"run-{track_id}-{source_sha[:12]}-{config.git_sha[:7]}"
    run_dir = config.root / "published" / "tracks" / track_id / "runs" / run_id
    manifest_path = run_dir / "manifest.json"
    success_path = run_dir / "_SUCCESS.json"
    latest_path = config.root / "published" / "tracks" / track_id / "latest.json"

    with _track_lock(config.root, track_id, config.lock_stale_seconds):
        if manifest_path.is_file() and success_path.is_file():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            success = json.loads(success_path.read_text(encoding="utf-8"))
            manifest_hash = _sha256(manifest_path)
            if (
                existing.get("source", {}).get("input_sha256") == source_sha
                and success.get("manifest_sha256") == manifest_hash
            ):
                _atomic_json(
                    latest_path,
                    {
                        "schema_name": "same_style_track_pointer",
                        "schema_version": SCHEMA_VERSION,
                        "track_id": track_id,
                        "analysis_run_id": run_id,
                        "manifest_storage_key": _storage_key(config.root, manifest_path),
                        "manifest_sha256": manifest_hash,
                        "published_at": success.get("published_at") or _utc_now(),
                    },
                )
                return existing
            raise PreprocessError(f"published run exists but failed integrity check: {run_dir}")

        attempt_id = uuid.uuid4().hex[:12]
        staging = config.root / "staging" / f"{run_id}.{attempt_id}"
        staging.mkdir(parents=True, exist_ok=False)
        _atomic_json(staging / "_STATE.json", {"status": "running", "step": "copy_master", "updated_at": _utc_now()})
        try:
            audio_dir = staging / "audio"
            stems_dir = audio_dir / "stems"
            drum_dir = audio_dir / "drums"
            work_dir = staging / "_work"
            audio_dir.mkdir(parents=True)
            stems_dir.mkdir(parents=True)
            drum_dir.mkdir(parents=True)
            work_dir.mkdir(parents=True)
            master = audio_dir / f"master{source.suffix.lower() or '.audio'}"
            shutil.copy2(source, master)

            _atomic_json(staging / "_STATE.json", {"status": "running", "step": "core", "updated_at": _utc_now()})
            if core_runner is None:
                from app.modules.library.analysis import analyze_audio_file

                core_runner = analyze_audio_file
            core = dict(core_runner(str(master)))

            _atomic_json(staging / "_STATE.json", {"status": "running", "step": "demucs", "updated_at": _utc_now()})
            separated = dict((demucs_runner or _run_demucs)(master, work_dir / "demucs", config))
            stems: dict[str, Path] = {}
            for name in STEM_NAMES:
                destination = stems_dir / f"{name}.wav"
                shutil.copy2(Path(separated[name]), destination)
                stems[name] = destination

            _atomic_json(staging / "_STATE.json", {"status": "running", "step": "stem_features", "updated_at": _utc_now()})
            if stem_analyzer is None:
                from app.modules.library.stem_analysis import analyze_stem_files

                stem_analyzer = analyze_stem_files
            stem_result = dict(
                stem_analyzer(
                    {name: str(path) for name, path in stems.items()},
                    original_path=str(master),
                    bpm=float(core.get("bpm") or 0.0),
                    beat_points=list(core.get("beat_points") or []),
                    downbeats=list(core.get("downbeats") or []),
                    key_profile=dict(core.get("key_profile") or {}),
                )
            )

            _atomic_json(staging / "_STATE.json", {"status": "running", "step": "mdx23c", "updated_at": _utc_now()})
            drum_stems: dict[str, Path] = {}
            try:
                drum_stems = {
                    name: Path(path)
                    for name, path in dict((mdx_runner or _run_mdx23c)(stems["drums"], drum_dir, config)).items()
                }
            except Exception:
                if config.require_mdx23c:
                    raise

            shutil.rmtree(work_dir, ignore_errors=True)
            (staging / "_STATE.json").unlink(missing_ok=True)

            manifest = _manifest(
                config=config,
                source=source,
                source_sha256=source_sha,
                track_id=track_id,
                run_id=run_id,
                title=title,
                artist=artist,
                master=master,
                stems=stems,
                drum_stems=drum_stems,
                core=core,
                stem_analysis=stem_result,
            )
            manifest_staging = staging / "manifest.json"
            _atomic_json(manifest_staging, manifest)
            _validate_manifest(manifest, schema)

            if run_dir.exists():
                raise PreprocessError(f"incomplete published run requires manual recovery: {run_dir}")
            run_dir.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, run_dir)
            active_attempt = run_dir
            manifest_hash = _sha256(manifest_path)
            published_at = _utc_now()
            asset_count = 1 + len(stems) + len(drum_stems)
            _atomic_json(
                success_path,
                {
                    "analysis_run_id": run_id,
                    "manifest_sha256": manifest_hash,
                    "asset_count": asset_count,
                    "published_at": published_at,
                },
            )
            _atomic_json(
                latest_path,
                {
                    "schema_name": "same_style_track_pointer",
                    "schema_version": SCHEMA_VERSION,
                    "track_id": track_id,
                    "analysis_run_id": run_id,
                    "manifest_storage_key": _storage_key(config.root, manifest_path),
                    "manifest_sha256": manifest_hash,
                    "published_at": published_at,
                },
            )
            index_path = config.root / "published" / "indexes" / "tracks.jsonl"
            index_path.parent.mkdir(parents=True, exist_ok=True)
            with index_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"track_id": track_id, "analysis_run_id": run_id, "status": manifest["status"], "published_at": published_at}, ensure_ascii=False) + "\n")
            return manifest
        except Exception as exc:
            _atomic_json(
                active_attempt / "_FAILED.json",
                {"status": "failed", "error_type": type(exc).__name__, "error": str(exc)[:2000], "updated_at": _utc_now()},
            )
            raise


__all__ = [
    "CONTRACT_VERSION",
    "PIPELINE_VERSION",
    "PreprocessConfig",
    "PreprocessError",
    "SCHEMA_NAME",
    "SCHEMA_VERSION",
    "run_same_style_preprocess",
]
