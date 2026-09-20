"""Read NAS-published HarBeat preprocess manifests into planning models."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .models import (
    DensityProfile,
    DrumProfile,
    PairAnalysis,
    PhraseMarker,
    SectionMarker,
    TrackProfile,
)


class PreprocessReadError(RuntimeError):
    """Raised when a published preprocess artifact is unsafe or unusable."""


@dataclass(frozen=True)
class ResolvedAsset:
    role: str
    storage_key: str
    path: Path
    sha256: str
    size_bytes: int
    content_type: str
    duration_ms: int
    sample_rate_hz: int
    channels: int


@dataclass(frozen=True)
class TrackPreprocessBundle:
    root: Path
    pointer: Mapping[str, Any]
    manifest: Mapping[str, Any]
    track: TrackProfile
    assets: Mapping[str, ResolvedAsset]
    quality_flags: tuple[str, ...]
    pipeline_git_sha: str | None


@dataclass(frozen=True)
class LibraryIndexItem:
    track_id: str
    analysis_run_id: str
    manifest_storage_key: str
    title: str
    artist: str
    status: str
    style_labels: tuple[str, ...]
    collection_labels: tuple[str, ...]
    source_collection: str
    original_filename: str


@dataclass(frozen=True)
class LibraryIndexBundle:
    root: Path
    path: Path
    payload: Mapping[str, Any]
    items: tuple[LibraryIndexItem, ...]


@dataclass(frozen=True)
class PairScoreBundle:
    root: Path
    path: Path
    payload: Mapping[str, Any]
    pair_analysis: PairAnalysis
    quality_flags: tuple[str, ...]
    proposal_action: str | None


@dataclass(frozen=True)
class PairIndexEntry:
    track_a_id: str
    track_b_id: str
    analysis_run_ids: tuple[str, str]
    cache_key: str
    status: str
    quality_flags: tuple[str, ...] = ()
    drum_overlap_score: float | None = None

    def matches(self, first_track_id: str, second_track_id: str) -> bool:
        return {self.track_a_id, self.track_b_id} == {first_track_id, second_track_id}


def preprocess_root(root: str | os.PathLike[str] | None = None) -> Path:
    """Resolve the NAS preprocess root."""

    value = root or os.getenv("HARBEAT_PREPROCESS_ROOT")
    if not value:
        raise PreprocessReadError("HARBEAT_PREPROCESS_ROOT is not set")
    return Path(value).expanduser().resolve()


def read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PreprocessReadError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PreprocessReadError(f"invalid JSON file: {path}") from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except FileNotFoundError as exc:
        raise PreprocessReadError(f"file not found: {path}") from exc
    return digest.hexdigest()


def resolve_storage_key(root: str | os.PathLike[str], storage_key: str) -> Path:
    """Resolve a storage key below root, rejecting absolute and parent paths."""

    if not isinstance(storage_key, str) or not storage_key:
        raise PreprocessReadError("storage_key must be a non-empty string")
    if "\\" in storage_key:
        raise PreprocessReadError(f"storage_key must use POSIX separators: {storage_key}")

    parsed = PurePosixPath(storage_key)
    if parsed.is_absolute():
        raise PreprocessReadError(f"absolute storage_key is not allowed: {storage_key}")
    if ".." in parsed.parts:
        raise PreprocessReadError(f"parent traversal in storage_key is not allowed: {storage_key}")

    base = Path(root).expanduser().resolve()
    resolved = (base / Path(*parsed.parts)).resolve()
    if not resolved.is_relative_to(base):
        raise PreprocessReadError(f"storage_key escaped preprocess root: {storage_key}")
    return resolved


def _ensure_schema(payload: Mapping[str, Any], expected_name: str, expected_major: str = "1") -> None:
    schema_name = payload.get("schema_name")
    if schema_name != expected_name:
        raise PreprocessReadError(f"unsupported schema_name: {schema_name!r}")
    schema_version = str(payload.get("schema_version") or "")
    major = schema_version.split(".", 1)[0]
    if major != expected_major:
        raise PreprocessReadError(f"unsupported schema_version: {schema_version!r}")


def _asset_items(manifest: Mapping[str, Any]) -> list[tuple[str, Mapping[str, Any]]]:
    assets = manifest.get("assets")
    if not isinstance(assets, Mapping):
        raise PreprocessReadError("manifest.assets is missing")

    items: list[tuple[str, Mapping[str, Any]]] = []
    master = assets.get("master")
    if not isinstance(master, Mapping):
        raise PreprocessReadError("manifest.assets.master is missing")
    items.append(("master", master))

    stems = assets.get("stems")
    if not isinstance(stems, Mapping):
        raise PreprocessReadError("manifest.assets.stems is missing")
    for role in ("vocals", "drums", "bass", "other"):
        asset = stems.get(role)
        if not isinstance(asset, Mapping):
            raise PreprocessReadError(f"manifest.assets.stems.{role} is missing")
        items.append((f"stem:{role}", asset))

    drum_stems = assets.get("drum_stems")
    if isinstance(drum_stems, Mapping):
        for role in ("kick", "snare", "hihat", "tom", "cymbal"):
            asset = drum_stems.get(role)
            if isinstance(asset, Mapping):
                items.append((f"drum:{role}", asset))

    return items


def _resolve_asset(
    root: Path,
    role: str,
    asset: Mapping[str, Any],
    *,
    verify_file: bool,
) -> ResolvedAsset:
    storage_key = str(asset.get("storage_key") or "")
    path = resolve_storage_key(root, storage_key)
    expected_size = int(asset.get("size_bytes") or 0)
    expected_hash = str(asset.get("sha256") or "")

    if verify_file:
        if not path.exists():
            raise PreprocessReadError(f"asset file not found for {role}: {path}")
        actual_size = path.stat().st_size
        if actual_size != expected_size:
            raise PreprocessReadError(
                f"asset size mismatch for {role}: expected {expected_size}, got {actual_size}"
            )
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise PreprocessReadError(
                f"asset sha256 mismatch for {role}: expected {expected_hash}, got {actual_hash}"
            )

    return ResolvedAsset(
        role=role,
        storage_key=storage_key,
        path=path,
        sha256=expected_hash,
        size_bytes=expected_size,
        content_type=str(asset.get("content_type") or ""),
        duration_ms=int(asset.get("duration_ms") or 0),
        sample_rate_hz=int(asset.get("sample_rate_hz") or 0),
        channels=int(asset.get("channels") or 0),
    )


def _hits_from_pattern(pattern: str | None) -> tuple[int, ...]:
    if not isinstance(pattern, str) or len(pattern) != 16:
        return ()
    return tuple(index for index, symbol in enumerate(pattern) if symbol != ".")


def _drum_profile_from_manifest(manifest: Mapping[str, Any]) -> DrumProfile:
    drum_groups = manifest["analysis"]["drum_groups"]
    tags: set[str] = set()

    def group(name: str) -> Mapping[str, Any]:
        value = drum_groups.get(name)
        return value if isinstance(value, Mapping) else {}

    def group_hits(name: str) -> tuple[int, ...]:
        return _hits_from_pattern(group(name).get("pattern_16"))

    for name in ("kick", "snare_clap", "hihat", "bass_808", "percussion"):
        item = group(name)
        if item.get("present"):
            tags.add(name)
        for subtype in item.get("subtypes") or []:
            if isinstance(subtype, str) and subtype.strip():
                tags.add(subtype.strip().lower())

    kick_hits = group_hits("kick")
    snare_hits = group_hits("snare_clap")
    hihat_hits = group_hits("hihat")
    bass_hits = group_hits("bass_808")
    percussion_hits = group_hits("percussion")
    rhythm_hits = tuple(sorted(set(kick_hits + snare_hits + hihat_hits + bass_hits + percussion_hits)))

    return DrumProfile(
        sound_tags=frozenset(tags),
        rhythm_hits=rhythm_hits,
        kick_hits=kick_hits,
        snare_clap_hits=snare_hits,
        hihat_hits=hihat_hits,
        bass_hits=bass_hits,
        percussion_hits=percussion_hits,
    )


def _energy_average(manifest: Mapping[str, Any], start_ms: int, end_ms: int) -> float | None:
    curve = manifest["analysis"]["energy"].get("curve") or []
    weighted = 0.0
    total_ms = 0
    for window in curve:
        if not isinstance(window, Mapping):
            continue
        left = max(start_ms, int(window.get("start_ms") or 0))
        right = min(end_ms, int(window.get("end_ms") or 0))
        overlap = max(0, right - left)
        if overlap <= 0:
            continue
        weighted += overlap * float(window.get("value") or 0.0)
        total_ms += overlap
    if total_ms <= 0:
        return None
    return weighted / total_ms


def _sections_from_manifest(manifest: Mapping[str, Any]) -> tuple[SectionMarker, ...]:
    counts: dict[str, int] = {}
    sections: list[SectionMarker] = []
    for item in manifest["analysis"]["sections"].get("items") or []:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("label") or "unknown")
        counts[label] = counts.get(label, 0) + 1
        start_ms = int(item.get("start_ms") or 0)
        end_ms = int(item.get("end_ms") or 0)
        energy = _energy_average(manifest, start_ms, end_ms)
        density = DensityProfile(
            vocal=energy if energy is not None else 0.0,
            bass=energy if energy is not None else 0.0,
            melody=energy if energy is not None else 0.0,
        )
        sections.append(
            SectionMarker(
                name=label,
                start_time_seconds=start_ms / 1000.0,
                end_time_seconds=end_ms / 1000.0,
                occurrence=counts[label],
                density=density,
            )
        )
    return tuple(sections)


def _section_name_at(sections: tuple[SectionMarker, ...], time_seconds: float) -> str | None:
    for section in sections:
        if section.contains(time_seconds):
            return section.name
    return None


def _risk_from_transition_windows(manifest: Mapping[str, Any], time_ms: int) -> float:
    risk = 0.50
    for window in manifest["analysis"].get("transition_windows") or []:
        if not isinstance(window, Mapping):
            continue
        role = window.get("role")
        if role not in {"out", "both", "avoid"}:
            continue
        start_ms = int(window.get("start_ms") or 0)
        end_ms = int(window.get("end_ms") or 0)
        if not start_ms <= time_ms <= end_ms:
            continue
        confidence = window.get("confidence")
        confidence_value = float(confidence) if isinstance(confidence, (int, float)) else 0.5
        if role == "avoid":
            risk = max(risk, confidence_value)
        else:
            risk = min(risk, 1.0 - confidence_value)
    return max(0.0, min(1.0, risk))


def _phrase_size_for_bar_index(bar_index: int) -> int:
    if bar_index % 16 == 0:
        return 16
    if bar_index % 8 == 0:
        return 8
    if bar_index % 4 == 0:
        return 4
    return 1


def _phrase_markers_from_manifest(
    manifest: Mapping[str, Any],
    sections: tuple[SectionMarker, ...],
) -> tuple[PhraseMarker, ...]:
    beat_grid = manifest["analysis"]["beat_grid"]
    bars_ms = beat_grid.get("bars_ms") or []
    markers: dict[tuple[int, int], PhraseMarker] = {}

    for index, time_ms in enumerate(bars_ms):
        if not isinstance(time_ms, int):
            continue
        time_seconds = time_ms / 1000.0
        phrase_bars = _phrase_size_for_bar_index(index)
        markers[(time_ms, index)] = PhraseMarker(
            time_seconds=time_seconds,
            bar_index=index,
            phrase_bars=phrase_bars,
            section_name=_section_name_at(sections, time_seconds),
            risk_score=_risk_from_transition_windows(manifest, time_ms),
            is_downbeat=True,
        )

    known_times = {time_ms for time_ms, _ in markers}
    for window in manifest["analysis"].get("transition_windows") or []:
        if not isinstance(window, Mapping) or window.get("role") not in {"out", "both"}:
            continue
        start_ms = int(window.get("start_ms") or 0)
        if start_ms in known_times:
            continue
        earlier_bars = [int(value) for value in bars_ms if isinstance(value, int) and value <= start_ms]
        bar_index = len(earlier_bars) - 1 if earlier_bars else 0
        time_seconds = start_ms / 1000.0
        markers[(start_ms, bar_index)] = PhraseMarker(
            time_seconds=time_seconds,
            bar_index=bar_index,
            phrase_bars=_phrase_size_for_bar_index(bar_index),
            section_name=_section_name_at(sections, time_seconds),
            risk_score=_risk_from_transition_windows(manifest, start_ms),
            is_downbeat=True,
        )

    return tuple(marker for _, marker in sorted(markers.items(), key=lambda item: item[0]))


def _stem_quality_from_manifest(manifest: Mapping[str, Any]) -> float:
    quality = manifest.get("quality")
    modules = quality.get("modules") if isinstance(quality, Mapping) else {}
    stem_status = modules.get("stem_separation") if isinstance(modules, Mapping) else None
    if stem_status == "ready":
        return 1.0
    if stem_status == "degraded":
        return 0.5
    return 0.0


def manifest_to_track_profile(
    manifest: Mapping[str, Any],
    *,
    style: str = "same_style",
    title: str | None = None,
    artist: str | None = None,
) -> TrackProfile:
    """Convert a same-style preprocess manifest into TrackProfile."""

    _ensure_schema(manifest, "same_style_track_preprocess")
    analysis = manifest["analysis"]
    sections = _sections_from_manifest(manifest)
    key_info = analysis["key"]
    key = key_info.get("camelot") or key_info.get("name")

    return TrackProfile(
        id=str(manifest["track_id"]),
        title=title or str(manifest["track_id"]),
        artist=artist,
        style=style,
        bpm=float(analysis["tempo"]["bpm"]),
        key=str(key) if key else None,
        duration_seconds=float(manifest["source"]["duration_ms"]) / 1000.0,
        drum_profile=_drum_profile_from_manifest(manifest),
        phrase_markers=_phrase_markers_from_manifest(manifest, sections),
        sections=sections,
        stem_quality=_stem_quality_from_manifest(manifest),
    )


def read_track_preprocess(
    track_id: str,
    *,
    root: str | os.PathLike[str] | None = None,
    style: str = "same_style",
    title: str | None = None,
    artist: str | None = None,
    allow_degraded: bool = False,
    verify_assets: bool = True,
) -> TrackPreprocessBundle:
    """Read and verify one NAS-published track preprocess bundle."""

    base = preprocess_root(root)
    pointer_path = base / "published" / "tracks" / track_id / "latest.json"
    pointer = read_json(pointer_path)
    _ensure_schema(pointer, "same_style_track_pointer")
    if pointer.get("track_id") != track_id:
        raise PreprocessReadError(
            f"latest pointer track_id mismatch: expected {track_id}, got {pointer.get('track_id')}"
        )

    manifest_path = resolve_storage_key(base, str(pointer.get("manifest_storage_key") or ""))
    expected_manifest_hash = str(pointer.get("manifest_sha256") or "")
    actual_manifest_hash = sha256_file(manifest_path)
    if actual_manifest_hash != expected_manifest_hash:
        raise PreprocessReadError(
            f"manifest sha256 mismatch: expected {expected_manifest_hash}, got {actual_manifest_hash}"
        )

    manifest = read_json(manifest_path)
    _ensure_schema(manifest, "same_style_track_preprocess")
    if manifest.get("track_id") != track_id:
        raise PreprocessReadError("manifest track_id does not match latest pointer")
    if manifest.get("analysis_run_id") != pointer.get("analysis_run_id"):
        raise PreprocessReadError("manifest analysis_run_id does not match latest pointer")

    status = manifest.get("status")
    if status == "unavailable":
        raise PreprocessReadError(f"track is unavailable: {track_id}")
    if status == "degraded" and not allow_degraded:
        raise PreprocessReadError(f"track is degraded and allow_degraded=False: {track_id}")
    if status not in {"ready", "degraded"}:
        raise PreprocessReadError(f"unsupported track status: {status!r}")

    success_path = manifest_path.parent / "_SUCCESS.json"
    success = read_json(success_path)
    if success.get("analysis_run_id") != manifest.get("analysis_run_id"):
        raise PreprocessReadError("_SUCCESS analysis_run_id does not match manifest")
    if success.get("manifest_sha256") != expected_manifest_hash:
        raise PreprocessReadError("_SUCCESS manifest_sha256 does not match latest pointer")

    resolved_assets = {
        role: _resolve_asset(base, role, asset, verify_file=verify_assets)
        for role, asset in _asset_items(manifest)
    }
    track = manifest_to_track_profile(manifest, style=style, title=title, artist=artist)
    quality = manifest.get("quality") if isinstance(manifest.get("quality"), Mapping) else {}

    return TrackPreprocessBundle(
        root=base,
        pointer=pointer,
        manifest=manifest,
        track=track,
        assets=resolved_assets,
        quality_flags=tuple(quality.get("quality_flags") or ()),
        pipeline_git_sha=str(manifest.get("pipeline", {}).get("git_sha") or ""),
    )


def read_track_preprocess_from_manifest_key(
    manifest_storage_key: str,
    *,
    root: str | os.PathLike[str] | None = None,
    expected_track_id: str | None = None,
    expected_analysis_run_id: str | None = None,
    style: str = "same_style",
    title: str | None = None,
    artist: str | None = None,
    allow_degraded: bool = False,
    verify_assets: bool = True,
) -> TrackPreprocessBundle:
    """Read a frozen index item by its manifest_storage_key.

    Unlike read_track_preprocess(), this function does not let a future
    latest.json redirect the test to a newer run.
    """

    base = preprocess_root(root)
    manifest_path = resolve_storage_key(base, manifest_storage_key)
    manifest = read_json(manifest_path)
    _ensure_schema(manifest, "same_style_track_preprocess")

    track_id = str(manifest.get("track_id") or "")
    analysis_run_id = str(manifest.get("analysis_run_id") or "")
    if expected_track_id and track_id != expected_track_id:
        raise PreprocessReadError(
            f"manifest track_id mismatch: expected {expected_track_id}, got {track_id}"
        )
    if expected_analysis_run_id and analysis_run_id != expected_analysis_run_id:
        raise PreprocessReadError(
            "manifest analysis_run_id does not match frozen index item"
        )

    status = manifest.get("status")
    if status == "unavailable":
        raise PreprocessReadError(f"track is unavailable: {track_id}")
    if status == "degraded" and not allow_degraded:
        raise PreprocessReadError(f"track is degraded and allow_degraded=False: {track_id}")
    if status not in {"ready", "degraded"}:
        raise PreprocessReadError(f"unsupported track status: {status!r}")

    success_path = manifest_path.parent / "_SUCCESS.json"
    success = read_json(success_path)
    if success.get("analysis_run_id") != analysis_run_id:
        raise PreprocessReadError("_SUCCESS analysis_run_id does not match manifest")
    expected_manifest_hash = str(success.get("manifest_sha256") or "")
    if len(expected_manifest_hash) != 64:
        raise PreprocessReadError("_SUCCESS manifest_sha256 is missing or invalid")
    actual_manifest_hash = sha256_file(manifest_path)
    if actual_manifest_hash != expected_manifest_hash:
        raise PreprocessReadError(
            f"manifest sha256 mismatch: expected {expected_manifest_hash}, got {actual_manifest_hash}"
        )
    pointer = {
        "schema_name": "same_style_track_pointer",
        "schema_version": "1.0.0",
        "track_id": track_id,
        "analysis_run_id": analysis_run_id,
        "manifest_storage_key": manifest_storage_key,
        "manifest_sha256": expected_manifest_hash,
    }

    resolved_assets = {
        role: _resolve_asset(base, role, asset, verify_file=verify_assets)
        for role, asset in _asset_items(manifest)
    }
    source = manifest.get("source") if isinstance(manifest.get("source"), Mapping) else {}
    track = manifest_to_track_profile(
        manifest,
        style=style,
        title=title or source.get("title"),
        artist=artist or source.get("artist"),
    )
    quality = manifest.get("quality") if isinstance(manifest.get("quality"), Mapping) else {}

    return TrackPreprocessBundle(
        root=base,
        pointer=pointer,
        manifest=manifest,
        track=track,
        assets=resolved_assets,
        quality_flags=tuple(quality.get("quality_flags") or ()),
        pipeline_git_sha=str(manifest.get("pipeline", {}).get("git_sha") or ""),
    )


def pair_score_path_for_cache_key(
    cache_key: str,
    *,
    root: str | os.PathLike[str] | None = None,
    score_version: str = "drum_pair_similarity_v2",
) -> Path:
    if len(cache_key) != 64 or any(char not in "0123456789abcdef" for char in cache_key):
        raise PreprocessReadError(f"invalid pair cache_key: {cache_key}")
    base = preprocess_root(root)
    return base / "published" / "pairs" / score_version / cache_key[:2] / f"{cache_key}.json"


def _pair_index_entry_from_payload(payload: Mapping[str, Any], line_number: int) -> PairIndexEntry:
    track_ids = payload.get("track_ids")
    if isinstance(track_ids, list) and len(track_ids) == 2:
        track_a_id = str(track_ids[0])
        track_b_id = str(track_ids[1])
    else:
        track_a_id = str(payload.get("track_a_id") or "")
        track_b_id = str(payload.get("track_b_id") or "")

    if not track_a_id or not track_b_id:
        raise PreprocessReadError(f"pairs.jsonl line {line_number} has no two track IDs")

    cache_key = str(payload.get("cache_key") or "")
    if len(cache_key) != 64 or any(char not in "0123456789abcdef" for char in cache_key):
        raise PreprocessReadError(f"pairs.jsonl line {line_number} has invalid cache_key")

    analysis_run_ids = payload.get("analysis_run_ids")
    if isinstance(analysis_run_ids, list) and len(analysis_run_ids) == 2:
        run_ids = (str(analysis_run_ids[0]), str(analysis_run_ids[1]))
    else:
        run_ids = (
            str(payload.get("analysis_run_id_a") or ""),
            str(payload.get("analysis_run_id_b") or ""),
        )

    drum_overlap = payload.get("drum_overlap_score")
    return PairIndexEntry(
        track_a_id=track_a_id,
        track_b_id=track_b_id,
        analysis_run_ids=run_ids,
        cache_key=cache_key,
        status=str(payload.get("status") or "unavailable"),
        quality_flags=tuple(str(flag) for flag in payload.get("quality_flags") or ()),
        drum_overlap_score=float(drum_overlap) if isinstance(drum_overlap, (int, float)) else None,
    )


def _library_index_item_from_payload(payload: Mapping[str, Any], item_number: int) -> LibraryIndexItem:
    track_id = str(payload.get("track_id") or "")
    analysis_run_id = str(payload.get("analysis_run_id") or "")
    manifest_storage_key = str(payload.get("manifest_storage_key") or "")
    if not track_id:
        raise PreprocessReadError(f"library index item {item_number} has no track_id")
    if not analysis_run_id:
        raise PreprocessReadError(f"library index item {item_number} has no analysis_run_id")
    if not manifest_storage_key:
        raise PreprocessReadError(f"library index item {item_number} has no manifest_storage_key")

    return LibraryIndexItem(
        track_id=track_id,
        analysis_run_id=analysis_run_id,
        manifest_storage_key=manifest_storage_key,
        title=str(payload.get("title") or track_id),
        artist=str(payload.get("artist") or ""),
        status=str(payload.get("status") or "unavailable"),
        style_labels=tuple(str(label) for label in payload.get("style_labels") or ()),
        collection_labels=tuple(str(label) for label in payload.get("collection_labels") or ()),
        source_collection=str(payload.get("source_collection") or ""),
        original_filename=str(payload.get("original_filename") or ""),
    )


def read_library_index(
    *,
    root: str | os.PathLike[str] | None = None,
    index_storage_key: str = "published/indexes/edm_8_handoff_v1.json",
) -> LibraryIndexBundle:
    """Read a frozen same-style library handoff index."""

    base = preprocess_root(root)
    index_path = resolve_storage_key(base, index_storage_key)
    payload = read_json(index_path)
    _ensure_schema(payload, "same_style_library_index")

    items_payload = payload.get("items")
    if not isinstance(items_payload, list):
        raise PreprocessReadError("library index items must be a list")

    items = tuple(
        _library_index_item_from_payload(item, number)
        for number, item in enumerate(items_payload, 1)
        if isinstance(item, Mapping)
    )
    total_tracks = payload.get("total_tracks")
    if isinstance(total_tracks, int) and total_tracks != len(items):
        raise PreprocessReadError(
            f"library index total_tracks mismatch: expected {total_tracks}, got {len(items)}"
        )

    return LibraryIndexBundle(root=base, path=index_path, payload=payload, items=items)


def read_pair_index(
    *,
    root: str | os.PathLike[str] | None = None,
    index_storage_key: str = "published/indexes/pairs.jsonl",
) -> tuple[PairIndexEntry, ...]:
    """Read production pair index entries from published/indexes/pairs.jsonl."""

    base = preprocess_root(root)
    index_path = resolve_storage_key(base, index_storage_key)
    entries: list[PairIndexEntry] = []
    try:
        lines = index_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise PreprocessReadError(f"pair index not found: {index_path}") from exc

    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PreprocessReadError(f"invalid pairs.jsonl line {line_number}") from exc
        if not isinstance(payload, Mapping):
            raise PreprocessReadError(f"pairs.jsonl line {line_number} is not an object")
        entries.append(_pair_index_entry_from_payload(payload, line_number))

    return tuple(entries)


def find_pair_index_entry(
    first_track_id: str,
    second_track_id: str,
    *,
    root: str | os.PathLike[str] | None = None,
    allow_degraded: bool = True,
) -> PairIndexEntry:
    entries = [
        entry
        for entry in read_pair_index(root=root)
        if entry.matches(first_track_id, second_track_id)
    ]
    if not entries:
        raise PreprocessReadError(f"pair index entry not found for {first_track_id} and {second_track_id}")

    ready_entries = [entry for entry in entries if entry.status == "ready"]
    degraded_entries = [entry for entry in entries if entry.status == "degraded"]
    if ready_entries:
        return ready_entries[-1]
    if degraded_entries and allow_degraded:
        return degraded_entries[-1]
    if degraded_entries:
        raise PreprocessReadError(
            f"pair index entry is degraded and allow_degraded=False: {first_track_id}, {second_track_id}"
        )
    raise PreprocessReadError(f"pair index entry is unavailable for {first_track_id} and {second_track_id}")


def pair_score_to_analysis(
    payload: Mapping[str, Any],
    *,
    allow_degraded: bool = False,
    allow_manual_review: bool = False,
) -> PairAnalysis:
    """Convert a pair score payload into PairAnalysis for transition planning."""

    _ensure_schema(payload, "same_style_pair_score")
    status = payload.get("status")
    if status == "unavailable":
        raise PreprocessReadError("pair score is unavailable")
    if status == "degraded" and not allow_degraded:
        raise PreprocessReadError("pair score is degraded and allow_degraded=False")
    if status not in {"ready", "degraded"}:
        raise PreprocessReadError(f"unsupported pair score status: {status!r}")

    route = payload.get("proposal_route") if isinstance(payload.get("proposal_route"), Mapping) else {}
    if route.get("proposal_action") == "manual_review" and not allow_manual_review:
        raise PreprocessReadError("pair score requires manual review")

    scores = payload.get("scores") if isinstance(payload.get("scores"), Mapping) else {}
    drum_overlap = scores.get("drum_overlap_score")
    if not isinstance(drum_overlap, (int, float)):
        raise PreprocessReadError("pair score has no numeric drum_overlap_score")

    return PairAnalysis(drum_overlap=float(drum_overlap))


def read_pair_score_by_cache_key(
    cache_key: str,
    *,
    root: str | os.PathLike[str] | None = None,
    allow_degraded: bool = False,
    allow_manual_review: bool = False,
) -> PairScoreBundle:
    base = preprocess_root(root)
    path = pair_score_path_for_cache_key(cache_key, root=base)
    payload = read_json(path)
    pair_analysis = pair_score_to_analysis(
        payload,
        allow_degraded=allow_degraded,
        allow_manual_review=allow_manual_review,
    )
    route = payload.get("proposal_route") if isinstance(payload.get("proposal_route"), Mapping) else {}
    return PairScoreBundle(
        root=base,
        path=path,
        payload=payload,
        pair_analysis=pair_analysis,
        quality_flags=tuple(payload.get("quality_flags") or ()),
        proposal_action=str(route.get("proposal_action") or ""),
    )


def find_pair_score_via_index(
    first_track_id: str,
    second_track_id: str,
    *,
    root: str | os.PathLike[str] | None = None,
    allow_degraded: bool = True,
    allow_manual_review: bool = False,
) -> PairScoreBundle:
    """Find a pair score through the production pair index."""

    entry = find_pair_index_entry(
        first_track_id,
        second_track_id,
        root=root,
        allow_degraded=allow_degraded,
    )
    bundle = read_pair_score_by_cache_key(
        entry.cache_key,
        root=root,
        allow_degraded=allow_degraded,
        allow_manual_review=allow_manual_review,
    )
    quality_flags = tuple(sorted(set(entry.quality_flags) | set(bundle.quality_flags)))
    return PairScoreBundle(
        root=bundle.root,
        path=bundle.path,
        payload=bundle.payload,
        pair_analysis=bundle.pair_analysis,
        quality_flags=quality_flags,
        proposal_action=bundle.proposal_action,
    )


def find_pair_score_for_tracks(
    first_track_id: str,
    second_track_id: str,
    *,
    root: str | os.PathLike[str] | None = None,
    score_version: str = "drum_pair_similarity_v2",
    allow_degraded: bool = False,
    allow_manual_review: bool = False,
) -> PairScoreBundle:
    """Find a pair score by scanning pair-score files.

    This is convenient for fixtures and small test roots. Production NAS usage
    should pass an explicit cache key or use a dedicated pair index.
    """

    base = preprocess_root(root)
    pair_root = base / "published" / "pairs" / score_version
    expected = {first_track_id, second_track_id}
    matches: list[Path] = []
    for path in sorted(pair_root.glob("*/*.json")):
        try:
            payload = read_json(path)
        except PreprocessReadError:
            continue
        tracks = payload.get("pair", {}).get("tracks") if isinstance(payload.get("pair"), Mapping) else None
        if not isinstance(tracks, list):
            continue
        ids = {str(item.get("track_id")) for item in tracks if isinstance(item, Mapping)}
        if ids == expected:
            matches.append(path)

    if not matches:
        raise PreprocessReadError(f"pair score not found for {first_track_id} and {second_track_id}")

    payload = read_json(matches[-1])
    pair_analysis = pair_score_to_analysis(
        payload,
        allow_degraded=allow_degraded,
        allow_manual_review=allow_manual_review,
    )
    route = payload.get("proposal_route") if isinstance(payload.get("proposal_route"), Mapping) else {}
    return PairScoreBundle(
        root=base,
        path=matches[-1],
        payload=payload,
        pair_analysis=pair_analysis,
        quality_flags=tuple(payload.get("quality_flags") or ()),
        proposal_action=str(route.get("proposal_action") or ""),
    )
