from __future__ import annotations

import dataclasses
import hashlib
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from .config import AdapterConfig, JETSON_SERVICES


def create_jetson_app(config: AdapterConfig) -> FastAPI:
    if config.service not in JETSON_SERVICES:
        raise ValueError(f"not a Jetson service: {config.service}")
    config.prepare_shadow_directories()
    app = FastAPI(title=f"HarBeat clean {config.service}", version="0.3.0")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "service": config.service,
            "profile": config.profile,
            "mode": config.mode,
            "release": "0.3.0",
            "production_ready": False,
        }

    if config.service == "catalog-api":
        _catalog_routes(app, config)
    elif config.service == "analysis-worker":
        _analysis_routes(app, config)
    elif config.service == "planning-api":
        _planning_routes(app, config)
    elif config.service == "render-worker":
        _render_routes(app, config)
    elif config.service == "stem-worker":
        _stem_routes(app, config)
    return app


def _catalog_routes(app: FastAPI, config: AdapterConfig) -> None:
    from harbeat_library_catalog.models import LibrarySong, Playlist
    from harbeat_library_catalog.service import CatalogService

    class RequestRepository:
        def __init__(self, songs: list[dict[str, Any]], playlist: dict[str, Any]) -> None:
            self.songs = [LibrarySong.from_api(row) for row in songs]
            self.playlist = Playlist.from_api(playlist)

        def list_library_songs(self) -> list[Any]:
            return list(self.songs)

        def get_playlist(self, playlist_id: int) -> Any:
            return self.playlist

    @app.post("/catalog/resolve-playlist")
    def resolve_playlist(body: dict[str, Any]) -> dict[str, Any]:
        try:
            repository = RequestRepository(list(body.get("songs") or []), dict(body.get("playlist") or {}))
            result = CatalogService(repository).resolve_playlist(int(body.get("playlist_id") or 0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "complete": result.complete,
            "songs": [dataclasses.asdict(row) for row in result.songs],
            "unresolved_catalog_song_ids": list(result.unresolved_catalog_song_ids),
        }

    @app.get("/catalog/database/playlist/{playlist_id}")
    def resolve_database_playlist(playlist_id: int) -> dict[str, Any]:
        from .postgres import PostgresCatalogRepository, database_url_from_env

        try:
            repository = PostgresCatalogRepository(database_url_from_env(), config.asset_root)
            result = CatalogService(repository).resolve_playlist(playlist_id)
        except (RuntimeError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "complete": result.complete,
            "songs": [dataclasses.asdict(row) for row in result.songs],
            "unresolved_catalog_song_ids": list(result.unresolved_catalog_song_ids),
        }

    @app.get("/catalog/database/song/{song_id}")
    def load_database_song(song_id: str) -> dict[str, Any]:
        from .postgres import PostgresCatalogRepository, database_url_from_env

        try:
            return PostgresCatalogRepository(database_url_from_env(), config.asset_root).load_song(song_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


def _analysis_routes(app: FastAPI, config: AdapterConfig) -> None:
    from harbeat_audio_preprocess.service import PreprocessService

    class RequestRepository:
        def __init__(self, features: dict[str, Any]) -> None:
            self.features = dict(features)

        def load_features(self, song_id: str) -> dict[str, Any]:
            return dict(self.features)

        def save_features(self, song_id: str, features: dict[str, Any]) -> None:
            self.features = dict(features)

    @app.post("/analysis/process")
    def process(body: dict[str, Any]) -> dict[str, Any]:
        repository = RequestRepository(dict(body.get("features") or {}))
        payload = body.get("analysis_payload")
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="analysis_payload is required")
        service = PreprocessService(repository, lambda _song_id: payload)
        try:
            result = service.process(str(body.get("song_id") or ""), force=bool(body.get("force", False)))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "song_id": result.song_id,
            "payload": dict(result.payload),
            "features": repository.features,
            "reused": result.reused,
        }

    @app.post("/analysis/database/process")
    def process_database_song(body: dict[str, Any]) -> dict[str, Any]:
        from harbeat_audio_preprocess.dj_structure_v2 import analyze_song_dj_structure
        from .postgres import (
            PostgresCatalogRepository,
            ShadowAnalysisRepository,
            database_url_from_env,
        )

        song_id = str(body.get("song_id") or "")
        try:
            catalog = PostgresCatalogRepository(database_url_from_env(), config.asset_root)
            repository = ShadowAnalysisRepository(catalog, config.state_root)
            song = _song_namespace(repository.load_song(song_id))
            service = PreprocessService(repository, lambda _song_id: analyze_song_dj_structure(song))
            result = service.process(song_id, force=bool(body.get("force", False)))
        except (RuntimeError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "song_id": result.song_id,
            "payload": dict(result.payload),
            "reused": result.reused,
            "persistence": "shadow_state_only",
        }


def _planning_routes(app: FastAPI, config: AdapterConfig) -> None:
    from harbeat_transition_planner import PlanningMode, PlanningRequest, TransitionPlanningService

    @app.post("/planning/transition")
    def plan(body: dict[str, Any]) -> dict[str, Any]:
        try:
            mode = PlanningMode(str(body.get("mode") or ""))
            previous = _song_namespace(body.get("previous_song"))
            next_song = _song_namespace(body.get("next_song"))
            options = body.get("options") or {}
            if not isinstance(options, dict):
                raise ValueError("options must be an object")
            return TransitionPlanningService().plan(PlanningRequest(mode, previous, next_song, options))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/planning/database/transition")
    def plan_database(body: dict[str, Any]) -> dict[str, Any]:
        from .postgres import PostgresCatalogRepository, database_url_from_env

        try:
            repository = PostgresCatalogRepository(database_url_from_env(), config.asset_root)
            previous = _song_namespace(repository.load_song(str(body.get("from_song_id") or "")))
            next_song = _song_namespace(repository.load_song(str(body.get("to_song_id") or "")))
            mode = PlanningMode(str(body.get("mode") or ""))
            options = body.get("options") or {}
            if not isinstance(options, dict):
                raise ValueError("options must be an object")
            return TransitionPlanningService().plan(PlanningRequest(mode, previous, next_song, options))
        except (RuntimeError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


def _render_routes(app: FastAPI, config: AdapterConfig) -> None:
    def load_database_song(song_id: str) -> dict[str, Any]:
        from .postgres import PostgresCatalogRepository, database_url_from_env

        return PostgresCatalogRepository(database_url_from_env(), config.asset_root).load_song(song_id)

    def render_pair(previous: Any, next_song: Any, plan: dict[str, Any]) -> dict[str, Any]:
        from harbeat_transition_renderer import DefaultRenderError, ensure_reference_render

        os.environ["HARBEAT_DEFAULT_MIX_PAIR_CACHE_DIR"] = str(config.state_root / "pairs")
        try:
            result = ensure_reference_render(previous, next_song, plan)
            return {**result, "pair_manifest": _render_pair_manifest(result)}
        except (DefaultRenderError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/render/transition")
    def render(body: dict[str, Any]) -> dict[str, Any]:
        try:
            previous = _song_namespace(body.get("previous_song"))
            next_song = _song_namespace(body.get("next_song"))
            plan = body.get("plan")
            if not isinstance(plan, dict):
                raise ValueError("plan is required")
            return render_pair(previous, next_song, plan)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/render/database/transition")
    def render_database(body: dict[str, Any]) -> dict[str, Any]:
        from .postgres import PostgresCatalogRepository, database_url_from_env

        plan = body.get("plan")
        if not isinstance(plan, dict):
            raise HTTPException(status_code=422, detail="plan is required")
        try:
            repository = PostgresCatalogRepository(database_url_from_env(), config.asset_root)
            previous = _song_namespace(repository.load_song(str(body.get("from_song_id") or "")))
            next_song = _song_namespace(repository.load_song(str(body.get("to_song_id") or "")))
            return render_pair(previous, next_song, plan)
        except RuntimeError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/render/artifacts/{pair_id}/{name}")
    def render_artifact(pair_id: str, name: str) -> FileResponse:
        if name not in {"transition_render.wav", "transition_render.json"}:
            raise HTTPException(status_code=404, detail="artifact not found")
        path = _contained_artifact(config.state_root / "pairs", pair_id, name)
        return FileResponse(path)

    @app.get("/render/database/song/{song_id}/manifest")
    def target_song_manifest(song_id: str) -> dict[str, Any]:
        try:
            song = load_database_song(song_id)
            source = Path(str(song.get("source_path") or ""))
            return {
                "song_id": song_id,
                "files": {
                    "original": _artifact_spec(
                        song_id,
                        source,
                        f"/render/database/song/{song_id}/original",
                    ),
                },
            }
        except (RuntimeError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/render/database/song/{song_id}/original")
    def target_song_original(song_id: str) -> FileResponse:
        try:
            song = load_database_song(song_id)
            source = Path(str(song.get("source_path") or ""))
            if not source.is_file():
                raise ValueError("song source is missing")
            source.resolve().relative_to(config.asset_root.resolve())
            return FileResponse(source)
        except (RuntimeError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=404, detail="artifact not found") from exc


def _render_pair_manifest(result: dict[str, Any]) -> dict[str, Any]:
    pair_id = str(result.get("pair_id") or "")
    wav = Path(str(result.get("transition_render_path") or ""))
    meta = Path(str(result.get("transition_render_meta_path") or ""))
    if not pair_id or not wav.is_file() or not meta.is_file():
        raise ValueError("renderer returned incomplete artifacts")
    return {
        "pair_id": pair_id,
        "planner_version": result.get("planner_version"),
        "audio_feature_source": result.get("audio_feature_source"),
        "renderer_version": result.get("renderer_version"),
        "required_renderer_version": result.get("required_renderer_version"),
        "render_strategy": result.get("render_strategy"),
        "files": {
            "transition_render": _artifact_spec(pair_id, wav, "transition_render.wav"),
            "transition_render_meta": _artifact_spec(pair_id, meta, "transition_render.json"),
        },
    }


def _artifact_spec(pair_id: str, path: Path, public_name: str) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "url": public_name if public_name.startswith("/") else f"/render/artifacts/{pair_id}/{public_name}",
        "size": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "format": path.suffix.lstrip("."),
    }


def _contained_artifact(root: Path, pair_id: str, name: str) -> Path:
    safe = "".join(ch for ch in pair_id if ch.isalnum() or ch in ("-", "_"))
    if safe != pair_id or not safe:
        raise HTTPException(status_code=404, detail="artifact not found")
    path = (root / safe / name).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="artifact not found")
    return path


def _stem_routes(app: FastAPI, config: AdapterConfig) -> None:
    @app.post("/stems/separate")
    def separate(body: dict[str, Any]) -> dict[str, Any]:
        from harbeat_stem_separation import StemSeparationError, StemSeparator, separation_result
        from harbeat_stem_separation.runner import SubprocessDemucsRunner

        audio_path = _contained_path(config.asset_root, body.get("audio_path"), must_exist=True)
        output_root = _contained_path(config.state_root, body.get("output_root"), must_exist=False)
        model_repo = body.get("model_repo") or config.settings.get("model_repo")
        runner = None
        if model_repo:
            runner = SubprocessDemucsRunner(
                model_repo=_contained_directory(config.asset_root, model_repo),
            )
        separator = StemSeparator(
            model=str(body.get("model") or "htdemucs"),
            timeout_sec=int(body.get("timeout_sec") or 120),
            runner=runner,
        )
        try:
            stems = separator.separate(str(audio_path), str(output_root))
        except StemSeparationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return separation_result("separated", stems)


def _song_namespace(value: Any) -> SimpleNamespace:
    if not isinstance(value, dict):
        raise ValueError("song must be an object")
    row = dict(value)
    if "duration" not in row and "duration_sec" in row:
        row["duration"] = row["duration_sec"]
    return SimpleNamespace(**row)


def _contained_path(root: Path, value: Any, *, must_exist: bool) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise HTTPException(status_code=422, detail="path is required")
    path = Path(raw).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="path is outside configured root") from exc
    if must_exist and not path.is_file():
        raise HTTPException(status_code=422, detail="input file does not exist")
    return path


def _contained_directory(root: Path, value: Any) -> Path:
    path = _contained_path(root, value, must_exist=False)
    if not path.is_dir():
        raise HTTPException(status_code=422, detail="directory does not exist")
    return path
