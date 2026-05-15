"""Music search & download API routes (Kuwo-backed, fangpi-compatible interface)."""
from __future__ import annotations

import os
import re
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.fangpi.service import download_fangpi_song, search_fangpi, smart_search_fangpi
from app.modules.fangpi.playlist_parser import parse_playlist_url
from app.modules.library.background_tasks import copy_analysis_from, run_analysis_and_separation
from app.modules.library.schemas import LibrarySongCreateRequest, LibrarySongData
from app.modules.library.service import create_or_replace_library_song
from app.modules.users.models import User
from app.shared.config import get_settings
from app.shared.database import get_db
from app.shared.responses import APIResponse

router = APIRouter()


class SearchRequest(BaseModel):
    query: str


class DownloadRequest(BaseModel):
    music_id: str
    title: str
    artist: str
    tags: list[str] = []
    energy: list[str] = []
    scenes: list[str] = []
    source: str = "fangpi"  # "fangpi" or "kuwo"


class VibeSearchRequest(BaseModel):
    vibe: str = ""
    tags: list[str] = Field(default_factory=list)
    mode: str = "vibe"  # "style" or "vibe"
    limit: int = Field(default=10, ge=1, le=100)


class ImportSongCandidate(BaseModel):
    title: str
    artist: str = "Unknown Artist"
    music_id: str | None = None
    source: str = "fangpi"
    library_song_id: str | None = None
    song_id: int | None = None
    segment: str = "all"
    tags: list[str] = Field(default_factory=list)


class ImportSongsRequest(BaseModel):
    playlist_id: int | None = None
    playlist_name: str = "Mixtape"
    songs: list[ImportSongCandidate]


class TrackSegmentChoice(BaseModel):
    index: int | None = None
    title: str | None = None
    artist: str | None = None
    segment: str = "all"


class ImportPlaylistRequest(BaseModel):
    url: str
    playlist_id: int | None = None
    playlist_name: str | None = None
    default_segment: str = "all"
    track_segments: list[TrackSegmentChoice] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=300)


class ParsePlaylistRequest(BaseModel):
    url: str


_SEGMENTS = {"all", "intro", "build", "verse", "drop", "bridge", "outro"}


def _normalize_segment(segment: str | None) -> str:
    value = (segment or "all").strip().lower()
    if value == "buildup":
        return "build"
    if value in {"break", "breakdown"}:
        return "bridge"
    return value if value in _SEGMENTS else "all"


def _normalize_token(value: object) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", str(value or "").lower()).strip()


def _split_tokens(*values: object) -> set[str]:
    tokens: set[str] = set()
    for value in values:
        cleaned = _normalize_token(value)
        for token in cleaned.split():
            if len(token) >= 2:
                tokens.add(token)
    return tokens


def _flatten_tags(value: object) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.extend([part.strip() for part in value.split(",") if part.strip()])
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (int, float, str, bool)):
                out.append(f"{key}:{item}")
            elif isinstance(item, list):
                out.extend(_flatten_tags(item))
    elif isinstance(value, list):
        for item in value:
            out.extend(_flatten_tags(item))
    return out


def _library_tags(lib) -> list[str]:
    tags: list[str] = []
    if lib.song and lib.song.tags:
        for attr in ("style", "energy", "vocal_type", "era_tag", "groove_tag", "difficulty_fit"):
            tags.extend(_flatten_tags(getattr(lib.song.tags, attr, None)))
    tags.extend(_flatten_tags(lib.genres))
    tags.extend(_flatten_tags(lib.dance_styles))
    tags.extend(_flatten_tags(lib.dance_style_scores))
    tags.extend(_flatten_tags(lib.music_features))
    return sorted({t for t in tags if t})


def _score_library_song(lib, query_tokens: set[str], tag_tokens: set[str]) -> tuple[float, dict[str, float]]:
    tags = _library_tags(lib)
    haystack_tokens = _split_tokens(lib.title, lib.artist, " ".join(tags))
    title_tokens = _split_tokens(lib.title, lib.artist)

    tag_matches = tag_tokens & haystack_tokens
    query_matches = query_tokens & haystack_tokens
    title_matches = query_tokens & title_tokens

    tag_score = len(tag_matches) * 1.0
    query_score = len(query_matches) * 0.55
    title_score = len(title_matches) * 0.75
    analysis_score = 0.15 if lib.analysis_status in {"completed", "analyzed"} else 0.0
    file_score = 0.2 if lib.source_path and os.path.isfile(lib.source_path) else 0.0
    total = tag_score + query_score + title_score + analysis_score + file_score
    if not query_tokens and not tag_tokens:
        total = file_score + analysis_score
    return total, {
        "tag": round(tag_score, 3),
        "vibe": round(query_score, 3),
        "title": round(title_score, 3),
        "analysis": round(analysis_score, 3),
        "file": round(file_score, 3),
    }


def _candidate_from_library(lib, score: float, tag_scores: dict[str, float], user_id: int) -> dict:
    tags = _library_tags(lib)
    return {
        "id": lib.id,
        "library_song_id": lib.id,
        "song_id": lib.song_id,
        "title": lib.title,
        "artist": lib.artist,
        "duration": lib.duration,
        "bpm": lib.bpm,
        "key": lib.camelot_key or lib.key,
        "genre": tags[0] if tags else None,
        "tags": tags[:12],
        "score": round(float(score), 4),
        "tag_scores": tag_scores,
        "reason": "matched local library tags and metadata",
        "source": "local",
        "in_library": lib.user_id == user_id,
    }


def _segment_tags(tags: list[str], segment: str) -> list[str]:
    segment = _normalize_segment(segment)
    merged = [tag for tag in tags if not tag.startswith("segment:")]
    if segment != "all":
        merged.append(f"segment:{segment}")
    return merged


def _ensure_playlist(db: Session, user_id: int, playlist_id: int | None, playlist_name: str):
    from app.modules.playlists.models import Playlist
    from app.modules.playlists.service import create_empty_playlist

    if playlist_id is not None:
        playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
        if not playlist:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found")
        if playlist.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your playlist")
        return playlist
    return create_empty_playlist(db, user_id, playlist_name or "Mixtape")


def _copy_library_song_to_user(db: Session, source_song, user_id: int):
    from datetime import datetime
    from app.modules.library.models import LibrarySong

    if source_song.user_id == user_id:
        return source_song

    existing = None
    if source_song.song_id:
        existing = (
            db.query(LibrarySong)
            .filter(LibrarySong.user_id == user_id, LibrarySong.song_id == source_song.song_id)
            .first()
        )
    if not existing:
        existing = (
            db.query(LibrarySong)
            .filter(
                LibrarySong.user_id == user_id,
                LibrarySong.title == source_song.title,
                LibrarySong.artist == source_song.artist,
            )
            .first()
        )
    if existing:
        return existing

    copied = LibrarySong(
        id=uuid.uuid4().hex,
        user_id=user_id,
        song_id=source_song.song_id,
        title=source_song.title,
        artist=source_song.artist,
        duration=source_song.duration or 0,
        format=source_song.format or "mp3",
        file_size=source_song.file_size or 0,
        source_type=source_song.source_type or "shared",
        source_path=source_song.source_path or "",
        platform_id=source_song.platform_id,
        platform_url=source_song.platform_url,
        created_at=datetime.utcnow(),
    )
    copy_analysis_from(source_song, copied)
    db.add(copied)
    db.commit()
    db.refresh(copied)
    return copied


async def _download_or_link_song(
    payload: DownloadRequest,
    background_tasks: BackgroundTasks,
    db: Session,
    current_user: User,
):
    from datetime import datetime
    from sqlalchemy import func
    from app.modules.music.schemas import UpsertSongRequest
    from app.modules.music.service import upsert_song_with_tags
    from app.modules.library.models import LibrarySong
    from app.modules.playlists.models import Song

    clean_title = payload.title.strip()
    clean_artist = payload.artist.strip() or "Unknown Artist"
    catalog_song = upsert_song_with_tags(db, UpsertSongRequest(
        title=clean_title,
        artist=clean_artist,
        tags=payload.tags,
        energy=payload.energy,
        scenes=payload.scenes,
    ))

    existing_user = (
        db.query(LibrarySong)
        .filter(
            LibrarySong.user_id == current_user.id,
            func.lower(LibrarySong.title) == clean_title.lower(),
            func.lower(LibrarySong.artist) == clean_artist.lower(),
        )
        .first()
    )
    if existing_user:
        if existing_user.song_id != catalog_song.id:
            existing_user.song_id = catalog_song.id
            db.commit()
            db.refresh(existing_user)
        return existing_user

    existing_any = (
        db.query(LibrarySong)
        .filter(LibrarySong.platform_id == payload.music_id, LibrarySong.source_path.isnot(None))
        .first()
    )
    if not existing_any:
        existing_any = (
            db.query(LibrarySong)
            .filter(
                func.lower(LibrarySong.title) == clean_title.lower(),
                func.lower(LibrarySong.artist) == clean_artist.lower(),
                LibrarySong.source_path.isnot(None),
            )
            .first()
        )
    if existing_any and existing_any.source_path:
        linked = _copy_library_song_to_user(db, existing_any, current_user.id)
        if linked.song_id != catalog_song.id:
            linked.song_id = catalog_song.id
            db.commit()
            db.refresh(linked)
        return linked

    settings = get_settings()
    upload_dir = os.path.abspath(settings.upload_dir)
    shared_dir = os.path.join(upload_dir, "shared")
    os.makedirs(shared_dir, exist_ok=True)

    try:
        result = await download_fangpi_song(
            payload.music_id,
            clean_title,
            clean_artist,
            shared_dir,
            source=payload.source,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"download failed: {e}",
        )

    song_id = uuid.uuid4().hex
    song_payload = LibrarySongCreateRequest(
        id=song_id,
        user_id=current_user.id,
        title=clean_title,
        artist=clean_artist,
        duration=0,
        format="mp3",
        file_size=result["file_size"],
        source_type="fangpi",
        source_path=result["file_path"],
        platform_id=payload.music_id,
        platform_url=f"https://www.fangpi.net/music/{payload.music_id}",
        created_at=datetime.utcnow(),
    )
    song = create_or_replace_library_song(db, song_payload)
    lib_row = db.get(LibrarySong, song.id)
    if lib_row:
        lib_row.song_id = catalog_song.id
        lib_row.analysis_status = "pending"
        db.commit()
        db.refresh(lib_row)
        background_tasks.add_task(run_analysis_and_separation, lib_row.id)
        return lib_row
    return song


@router.post("/search")
async def fangpi_search(payload: SearchRequest):
    """Search songs via music API (Kuwo)."""
    results = await search_fangpi(payload.query)
    return APIResponse(data={"songs": results})


@router.post("/vibe-search")
async def fangpi_vibe_search(
    payload: VibeSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search the server library by dance-style tags or natural-language vibe."""
    from app.modules.library.models import LibrarySong

    query_tokens = _split_tokens(payload.vibe)
    tag_tokens = _split_tokens(" ".join(payload.tags))
    limit = max(1, min(int(payload.limit), 100))

    rows = (
        db.query(LibrarySong)
        .filter(LibrarySong.source_path.isnot(None), LibrarySong.source_path != "")
        .order_by(LibrarySong.user_id == current_user.id, LibrarySong.created_at.desc())
        .all()
    )

    ranked: list[tuple[float, LibrarySong, dict[str, float]]] = []
    seen_keys: set[tuple[str, str]] = set()
    for lib in rows:
        key = (lib.title.strip().lower(), lib.artist.strip().lower())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        score, tag_scores = _score_library_song(lib, query_tokens, tag_tokens)
        if (query_tokens or tag_tokens) and score <= 0:
            continue
        ranked.append((score, lib, tag_scores))

    ranked.sort(key=lambda item: (item[0], item[1].user_id == current_user.id, item[1].created_at), reverse=True)
    local_results = [
        _candidate_from_library(lib, score, tag_scores, current_user.id)
        for score, lib, tag_scores in ranked[:limit]
    ]

    external_results: list[dict] = []
    external_query = payload.vibe.strip() or " ".join(payload.tags).strip()
    if external_query and len(local_results) < min(limit, 5):
        external_results = (await search_fangpi(external_query))[: max(0, limit - len(local_results))]

    return APIResponse(
        data={
            "mode": payload.mode,
            "vibe": payload.vibe,
            "tags": payload.tags,
            "local_results": local_results,
            "external_results": external_results,
        }
    )


@router.post("/download")
async def fangpi_download(
    payload: DownloadRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download a song to the shared server pool and link to user's library."""
    song = await _download_or_link_song(payload, background_tasks, db, current_user)
    return APIResponse(data=LibrarySongData.model_validate(song))

    from datetime import datetime
    from app.modules.music.schemas import UpsertSongRequest
    from app.modules.music.service import upsert_song_with_tags
    from app.modules.library.models import LibrarySong
    from app.modules.playlists.models import Song

    settings = get_settings()
    upload_dir = os.path.abspath(settings.upload_dir)
    shared_dir = os.path.join(upload_dir, "shared")
    os.makedirs(shared_dir, exist_ok=True)

    # --- Cross-user dedup: check if ANY user already downloaded this song ---
    # Strategy: check by platform_id, then by title+artist in Song catalog,
    #           then by title+artist in LibrarySong (case-insensitive).
    existing_lib = (
        db.query(LibrarySong)
        .filter(LibrarySong.platform_id == payload.music_id)
        .first()
    )
    if not existing_lib:
        # Check via the Song catalog table (cross-platform canonical record)
        from sqlalchemy import func
        catalog_match = (
            db.query(Song)
            .filter(
                func.lower(Song.title) == payload.title.lower().strip(),
                func.lower(Song.artist) == payload.artist.lower().strip(),
            )
            .first()
        )
        if catalog_match:
            # Find any LibrarySong linked to this catalog song that has a file
            existing_lib = (
                db.query(LibrarySong)
                .filter(
                    LibrarySong.song_id == catalog_match.id,
                    LibrarySong.source_path.isnot(None),
                )
                .first()
            )
    if not existing_lib:
        # Fallback: case-insensitive title+artist on LibrarySong itself
        from sqlalchemy import func
        existing_lib = (
            db.query(LibrarySong)
            .filter(
                func.lower(LibrarySong.title) == payload.title.lower().strip(),
                func.lower(LibrarySong.artist) == payload.artist.lower().strip(),
                LibrarySong.source_path.isnot(None),
            )
            .first()
        )

    if existing_lib:
        # Song already downloaded — just upsert tags (accumulate) and link to this user
        catalog_song = upsert_song_with_tags(db, UpsertSongRequest(
            title=payload.title,
            artist=payload.artist,
            tags=payload.tags,
            energy=payload.energy,
            scenes=payload.scenes,
        ))

        # Check if this user already has a library entry for this song
        user_lib = (
            db.query(LibrarySong)
            .filter(LibrarySong.user_id == current_user.id, LibrarySong.platform_id == payload.music_id)
            .first()
        )
        if not user_lib:
            from sqlalchemy import func as sa_func
            user_lib = (
                db.query(LibrarySong)
                .filter(
                    LibrarySong.user_id == current_user.id,
                    sa_func.lower(LibrarySong.title) == payload.title.lower().strip(),
                    sa_func.lower(LibrarySong.artist) == payload.artist.lower().strip(),
                )
                .first()
            )
        if not user_lib:
            user_lib = LibrarySong(
                id=uuid.uuid4().hex,
                user_id=current_user.id,
                title=payload.title,
                artist=payload.artist,
                duration=existing_lib.duration or 0,
                format="mp3",
                file_size=existing_lib.file_size or 0,
                source_type="fangpi",
                source_path=existing_lib.source_path,
                platform_id=payload.music_id,
                platform_url=f"https://www.fangpi.net/music/{payload.music_id}",
                song_id=catalog_song.id,
                created_at=datetime.utcnow(),
            )
            # Copy analysis results from existing entry
            copy_analysis_from(existing_lib, user_lib)
            db.add(user_lib)
            db.commit()
            db.refresh(user_lib)
        else:
            if user_lib.song_id != catalog_song.id:
                user_lib.song_id = catalog_song.id
                db.commit()
                db.refresh(user_lib)

        return APIResponse(data=LibrarySongData.model_validate(user_lib))

    # New song — download to shared directory
    try:
        result = await download_fangpi_song(
            payload.music_id, payload.title, payload.artist, shared_dir,
            source=payload.source,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"download failed: {e}",
        )

    song_id = uuid.uuid4().hex
    song_payload = LibrarySongCreateRequest(
        id=song_id,
        user_id=current_user.id,
        title=payload.title,
        artist=payload.artist,
        duration=0,
        format="mp3",
        file_size=result["file_size"],
        source_type="fangpi",
        source_path=result["file_path"],
        platform_id=payload.music_id,
        platform_url=f"https://www.fangpi.net/music/{payload.music_id}",
        created_at=datetime.utcnow(),
    )
    song = create_or_replace_library_song(db, song_payload)

    # Create/update Song + SongTag (accumulate tags) and link
    catalog_song = upsert_song_with_tags(db, UpsertSongRequest(
        title=payload.title,
        artist=payload.artist,
        tags=payload.tags,
        energy=payload.energy,
        scenes=payload.scenes,
    ))

    lib_row = db.get(LibrarySong, song.id)
    if lib_row and lib_row.song_id != catalog_song.id:
        lib_row.song_id = catalog_song.id
        db.commit()

    # Enqueue background analysis + stem separation
    if lib_row:
        lib_row.analysis_status = "pending"
        db.commit()
    background_tasks.add_task(run_analysis_and_separation, song.id)

    return APIResponse(data=LibrarySongData.model_validate(song))


@router.post("/parse-playlist")
async def parse_playlist_endpoint(payload: ParsePlaylistRequest):
    """Parse a NetEase Cloud Music or QQ Music playlist URL."""
    try:
        result = await parse_playlist_url(payload.url)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return APIResponse(data=result)


@router.post("/import-songs")
async def import_songs_endpoint(
    payload: ImportSongsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import selected search results into a playlist and preserve segment choices."""
    from app.modules.library.models import LibrarySong
    from app.modules.playlists.service import add_library_songs_to_playlist

    if not payload.songs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="songs must not be empty")

    playlist = _ensure_playlist(db, current_user.id, payload.playlist_id, payload.playlist_name)
    imported: list[dict] = []
    failed: list[dict] = []

    for index, item in enumerate(payload.songs):
        segment = _normalize_segment(item.segment)
        tags = _segment_tags(item.tags, segment)
        try:
            lib = None
            if item.library_song_id:
                source_lib = db.get(LibrarySong, item.library_song_id)
                if not source_lib:
                    raise ValueError("library song not found")
                lib = _copy_library_song_to_user(db, source_lib, current_user.id)
            elif item.song_id:
                source_lib = (
                    db.query(LibrarySong)
                    .filter(
                        LibrarySong.song_id == item.song_id,
                        LibrarySong.source_path.isnot(None),
                        LibrarySong.source_path != "",
                    )
                    .first()
                )
                if source_lib:
                    lib = _copy_library_song_to_user(db, source_lib, current_user.id)

            if lib is None:
                music_id = item.music_id
                source = item.source
                if not music_id:
                    candidates = await smart_search_fangpi(item.title, item.artist)
                    if not candidates:
                        raise ValueError("no downloadable candidate found")
                    music_id = str(candidates[0]["id"])
                    source = str(candidates[0].get("source") or "fangpi")
                lib = await _download_or_link_song(
                    DownloadRequest(
                        music_id=str(music_id),
                        title=item.title,
                        artist=item.artist,
                        tags=tags,
                        source=source,
                    ),
                    background_tasks,
                    db,
                    current_user,
                )

            add_library_songs_to_playlist(db, playlist.id, current_user.id, [lib.id])
            db.refresh(lib)
            imported.append(
                {
                    "index": index,
                    "library_song_id": lib.id,
                    "song_id": lib.song_id,
                    "title": lib.title,
                    "artist": lib.artist,
                    "segment": segment,
                }
            )
        except Exception as exc:
            failed.append(
                {
                    "index": index,
                    "title": item.title,
                    "artist": item.artist,
                    "segment": segment,
                    "error": str(exc),
                }
            )

    return APIResponse(
        data={
            "playlist_id": playlist.id,
            "playlist_name": playlist.playlist_name,
            "imported": imported,
            "failed": failed,
        }
    )


def _segment_for_track(track: dict, index: int, choices: list[TrackSegmentChoice], default_segment: str) -> str:
    for choice in choices:
        if choice.index is not None and choice.index == index:
            return _normalize_segment(choice.segment)
        title_matches = choice.title and str(choice.title).strip().lower() == str(track.get("title", "")).strip().lower()
        artist_matches = choice.artist and str(choice.artist).strip().lower() == str(track.get("artist", "")).strip().lower()
        if title_matches and (artist_matches or not choice.artist):
            return _normalize_segment(choice.segment)
    return _normalize_segment(default_segment)


@router.post("/import-playlist")
async def import_playlist_endpoint(
    payload: ImportPlaylistRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Parse a playlist URL, search/download each track, add it to a playlist."""
    from app.modules.playlists.service import add_library_songs_to_playlist

    try:
        parsed = await parse_playlist_url(payload.url)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    playlist_name = payload.playlist_name or parsed.get("name") or "Mixtape"
    playlist = _ensure_playlist(db, current_user.id, payload.playlist_id, playlist_name)
    tracks = list(parsed.get("tracks") or [])[: payload.limit]
    imported: list[dict] = []
    failed: list[dict] = []

    for index, track in enumerate(tracks):
        title = str(track.get("title") or "").strip()
        artist = str(track.get("artist") or "Unknown Artist").strip() or "Unknown Artist"
        segment = _segment_for_track(track, index, payload.track_segments, payload.default_segment)
        if not title:
            failed.append({"index": index, "title": title, "artist": artist, "segment": segment, "error": "empty title"})
            continue
        try:
            candidates = await smart_search_fangpi(title, artist)
            if not candidates:
                raise ValueError("no candidate found")
            candidate = candidates[0]
            lib = await _download_or_link_song(
                DownloadRequest(
                    music_id=str(candidate["id"]),
                    title=title,
                    artist=artist,
                    tags=_segment_tags([], segment),
                    source=str(candidate.get("source") or "fangpi"),
                ),
                background_tasks,
                db,
                current_user,
            )
            add_library_songs_to_playlist(db, playlist.id, current_user.id, [lib.id])
            db.refresh(lib)
            imported.append(
                {
                    "index": index,
                    "library_song_id": lib.id,
                    "song_id": lib.song_id,
                    "title": lib.title,
                    "artist": lib.artist,
                    "segment": segment,
                    "source_candidate": candidate,
                }
            )
        except Exception as exc:
            failed.append({"index": index, "title": title, "artist": artist, "segment": segment, "error": str(exc)})

    return APIResponse(
        data={
            "playlist_id": playlist.id,
            "playlist_name": playlist.playlist_name,
            "platform": parsed.get("platform"),
            "source_name": parsed.get("name"),
            "track_count": len(tracks),
            "imported": imported,
            "failed": failed,
        }
    )


class BatchSearchItem(BaseModel):
    title: str
    artist: str


class BatchSearchRequest(BaseModel):
    songs: list[BatchSearchItem]


@router.post("/batch-search")
async def fangpi_batch_search(payload: BatchSearchRequest):
    """Search fangpi for multiple songs. Returns {results: [{title, artist, found: bool, candidates: [...]}]}."""
    results = []
    for item in payload.songs:
        candidates = await smart_search_fangpi(item.title, item.artist)
        results.append({
            "title": item.title,
            "artist": item.artist,
            "found": len(candidates) > 0,
            "candidates": candidates[:5],  # Top 5 per song
        })
    return APIResponse(data={"results": results})
