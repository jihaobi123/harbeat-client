from __future__ import annotations

import random
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Playlist, PlaylistSong, Song, SongTag
from app.modules.recommendations.schemas import (
    AddToLibraryData,
    DiscoverData,
    DiscoverSection,
    DiscoverSongItem,
    RecommendedSongItem,
    VibeSearchData,
    VibeSearchSongItem,
)

# ───────────────── Style → display info mapping ─────────────────
_STYLE_META: dict[str, tuple[str, str]] = {
    "hiphop":    ("🎤", "嘻哈 / Hip-Hop"),
    "hip-hop":   ("🎤", "嘻哈 / Hip-Hop"),
    "breaking":  ("🌀", "Breaking"),
    "popping":   ("🤖", "Popping"),
    "locking":   ("🔒", "Locking"),
    "waacking":  ("💃", "Waacking"),
    "house":     ("🏠", "House"),
    "krump":     ("🔥", "Krump"),
    "jazz":      ("🎷", "Jazz"),
    "funk":      ("🎸", "Funk"),
    "urban":     ("🌆", "Urban Dance"),
    "afro":      ("🌍", "Afro"),
    "dancehall": ("🇯🇲", "Dancehall"),
    "soul":      ("💜", "Soul / R&B"),
    "r&b":       ("💜", "Soul / R&B"),
    "trap":      ("⚡", "Trap"),
    "pop":       ("🎵", "Pop"),
    "latin":     ("💃", "Latin"),
    "reggaeton": ("🔊", "Reggaeton"),
    "电子":      ("🎛️", "电子 / Electronic"),
    "嘻哈":      ("🎤", "嘻哈 / Hip-Hop"),
}

_ENERGY_META: dict[str, tuple[str, str, str]] = {
    "high":   ("🔥", "高能炸场", "适合 Battle / Cypher 的高能量歌曲"),
    "medium": ("🎵", "律动氛围", "适合日常练习和自由舞蹈的中等节奏"),
    "low":    ("🌙", "放松舒缓", "适合拉伸和冷静的低能量音乐"),
}

_GROOVE_META: dict[str, tuple[str, str]] = {
    "cypher":   ("🔄", "Cypher 围圈"),
    "battle":   ("⚔️", "Battle 对战"),
    "showcase": ("🎭", "表演展示"),
    "training": ("📚", "基础训练"),
    "party":    ("🎉", "派对氛围"),
    "warmup":   ("🏃", "热身暖场"),
}

SECTION_SONG_LIMIT = 6


def _user_library_song_ids(db: Session, user_id: int) -> set[int]:
    """Song IDs already in the user's playlists."""
    return set(
        r[0]
        for r in db.query(PlaylistSong.song_id)
        .join(Playlist, Playlist.id == PlaylistSong.playlist_id)
        .filter(Playlist.user_id == user_id)
        .all()
    )


def _to_item(song: Song, tags: Optional[SongTag], in_lib: bool) -> DiscoverSongItem:
    return DiscoverSongItem(
        song_id=song.id,
        title=song.title,
        artist=song.artist,
        style=tags.style if tags else None,
        energy=tags.energy if tags else None,
        in_library=in_lib,
    )


def discover_songs(db: Session, user_id: int) -> DiscoverData:
    """Generate categorised recommendation sections — NetEase Cloud style.

    All songs on the server are considered. Songs the user already owns are
    marked ``in_library=True`` but NOT excluded (they provide familiarity).
    New songs are prioritised within each section.
    """
    rows = db.query(Song, SongTag).outerjoin(SongTag, SongTag.song_id == Song.id).all()
    if not rows:
        return DiscoverData(sections=[])

    user_song_ids = _user_library_song_ids(db, user_id)

    # Build lookup helpers
    all_songs: list[tuple[Song, Optional[SongTag], bool]] = []
    by_style: dict[str, list[tuple[Song, Optional[SongTag], bool]]] = defaultdict(list)
    by_energy: dict[str, list[tuple[Song, Optional[SongTag], bool]]] = defaultdict(list)
    by_groove: dict[str, list[tuple[Song, Optional[SongTag], bool]]] = defaultdict(list)

    for song, tags in rows:
        in_lib = song.id in user_song_ids
        entry = (song, tags, in_lib)
        all_songs.append(entry)

        if tags and tags.style:
            for token in tags.style.split(","):
                key = token.strip().lower()
                if key:
                    by_style[key].append(entry)

        if tags and tags.energy:
            for token in tags.energy.split(","):
                key = token.strip().lower()
                if key:
                    by_energy[key].append(entry)

        if tags and tags.groove_tag:
            for token in tags.groove_tag.split(","):
                key = token.strip().lower()
                if key:
                    by_groove[key].append(entry)

    sections: list[DiscoverSection] = []

    # ── 1. 猜你喜欢 (personalised: new songs first, shuffled) ──
    new_songs = [e for e in all_songs if not e[2]]
    if new_songs:
        random.shuffle(new_songs)
        pick = new_songs[: SECTION_SONG_LIMIT + 4]  # slightly more for variety
        sections.append(
            DiscoverSection(
                key="for_you",
                title="猜你喜欢",
                icon="✨",
                description="为你精选的新歌，点击收入曲库",
                songs=[_to_item(s, t, il) for s, t, il in pick],
            )
        )

    # ── 2. Per-style sections ──
    seen_style_groups: set[str] = set()
    for raw_key, entries in sorted(by_style.items(), key=lambda kv: -len(kv[1])):
        norm = raw_key.lower()
        meta = _STYLE_META.get(norm)
        if not meta:
            icon, display = "🎵", raw_key.capitalize()
        else:
            icon, display = meta

        # Avoid duplicates for aliases (hip-hop / hiphop)
        if display in seen_style_groups:
            continue
        seen_style_groups.add(display)

        # Prioritise new songs
        random.shuffle(entries)
        entries.sort(key=lambda e: (e[2], random.random()))  # not-in-lib first
        picked = entries[:SECTION_SONG_LIMIT]
        if not picked:
            continue

        sections.append(
            DiscoverSection(
                key=f"style_{norm}",
                title=f"{display} 精选",
                icon=icon,
                description=f"适合 {display} 风格的音乐",
                songs=[_to_item(s, t, il) for s, t, il in picked],
            )
        )

    # ── 3. Per-energy sections ──
    for ekey in ("high", "medium", "low"):
        entries = by_energy.get(ekey, [])
        if not entries:
            continue
        meta = _ENERGY_META[ekey]
        random.shuffle(entries)
        entries.sort(key=lambda e: (e[2], random.random()))
        picked = entries[:SECTION_SONG_LIMIT]
        sections.append(
            DiscoverSection(
                key=f"energy_{ekey}",
                title=meta[1],
                icon=meta[0],
                description=meta[2],
                songs=[_to_item(s, t, il) for s, t, il in picked],
            )
        )

    # ── 4. Per-groove / scene sections ──
    for gkey, entries in sorted(by_groove.items(), key=lambda kv: -len(kv[1])):
        meta = _GROOVE_META.get(gkey.lower())
        if not meta:
            icon, display = "🎶", gkey.capitalize()
        else:
            icon, display = meta
        random.shuffle(entries)
        entries.sort(key=lambda e: (e[2], random.random()))
        picked = entries[:SECTION_SONG_LIMIT]
        if not picked:
            continue
        sections.append(
            DiscoverSection(
                key=f"groove_{gkey}",
                title=f"{display} 适用",
                icon=icon,
                description=f"适合 {display} 场景使用的歌曲",
                songs=[_to_item(s, t, il) for s, t, il in picked],
            )
        )

    # ── 5. 最新入库 (recently added) ──
    recent = sorted(all_songs, key=lambda e: e[0].id, reverse=True)[:SECTION_SONG_LIMIT]
    if recent:
        sections.append(
            DiscoverSection(
                key="recent",
                title="最新入库",
                icon="🆕",
                description="最近上传到服务器的新歌",
                songs=[_to_item(s, t, il) for s, t, il in recent],
            )
        )

    # ── 6. 随机发现 ──
    pool = list(all_songs)
    random.shuffle(pool)
    sections.append(
        DiscoverSection(
            key="random",
            title="随机发现",
            icon="🎲",
            description="随机推荐，也许有惊喜",
            songs=[_to_item(s, t, il) for s, t, il in pool[:SECTION_SONG_LIMIT]],
        )
    )

    return DiscoverData(sections=sections)


# ───────────── Add a server song to user's library ─────────────

def add_song_to_library(db: Session, user_id: int, song_id: int) -> AddToLibraryData:
    """Create a LibrarySong entry for an existing Song on the server.

    Reuses the file from any other user's LibrarySong linked to the same Song.
    """
    song = db.query(Song).filter(Song.id == song_id).first()
    if not song:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="歌曲不存在")

    # Check if user already has this song
    existing = (
        db.query(LibrarySong)
        .filter(LibrarySong.user_id == user_id, LibrarySong.song_id == song_id)
        .first()
    )
    if existing:
        return AddToLibraryData(
            library_song_id=existing.id, title=existing.title, artist=existing.artist,
        )

    # Find any other user's LibrarySong with this song's file
    source_lib = (
        db.query(LibrarySong)
        .filter(
            LibrarySong.song_id == song_id,
            LibrarySong.source_path.isnot(None),
            LibrarySong.source_path != "",
        )
        .first()
    )
    if not source_lib:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该歌曲没有可用的音频文件",
        )

    new_lib = LibrarySong(
        id=uuid.uuid4().hex,
        user_id=user_id,
        song_id=song_id,
        title=song.title,
        artist=song.artist,
        duration=source_lib.duration or 0,
        format=source_lib.format or "mp3",
        file_size=source_lib.file_size or 0,
        source_type=source_lib.source_type or "server",
        source_path=source_lib.source_path,
        platform_id=source_lib.platform_id,
        platform_url=source_lib.platform_url,
        created_at=datetime.utcnow(),
    )

    # Copy analysis results
    from app.modules.library.background_tasks import copy_analysis_from
    copy_analysis_from(source_lib, new_lib)

    db.add(new_lib)
    db.commit()
    db.refresh(new_lib)

    return AddToLibraryData(
        library_song_id=new_lib.id, title=new_lib.title, artist=new_lib.artist,
    )


# ───────────── Legacy: used by practice session ─────────────

def _score_song(
    tags: Optional[SongTag],
    profile,
    mode: str,
    target_energy: Optional[str],
) -> int:
    score = 0
    if tags and tags.style:
        style_tokens = {t.strip() for t in tags.style.split(",") if t.strip()}
        if profile.favorite_style and profile.favorite_style in style_tokens:
            score += 3
    else:
        score += 1
    if tags and tags.energy:
        energy_tokens = {e.strip() for e in tags.energy.split(",") if e.strip()}
        if target_energy and target_energy in energy_tokens:
            score += 3
        elif profile.energy_preference and profile.energy_preference in energy_tokens:
            score += 2
    else:
        score += 1
    if tags and tags.groove_tag:
        groove_tokens = {g.strip() for g in tags.groove_tag.split(",") if g.strip()}
        if profile.groove_preference and profile.groove_preference in groove_tokens:
            score += 1
    else:
        score += 1
    if mode == "cypher" and tags and tags.difficulty_fit in {"intermediate", "advanced"}:
        score += 1
    return score


def recommend_songs(
    db: Session,
    user_id: int,
    mode: str,
    current_song_id: Optional[int] = None,
    target_energy: Optional[str] = None,
    source: str = "library",
) -> list[RecommendedSongItem]:
    from app.modules.profiles.service import get_profile_or_404

    profile = get_profile_or_404(db, user_id)
    rows = (
        db.query(Song, SongTag)
        .join(PlaylistSong, PlaylistSong.song_id == Song.id)
        .join(Playlist, Playlist.id == PlaylistSong.playlist_id)
        .outerjoin(SongTag, SongTag.song_id == Song.id)
        .filter(Playlist.user_id == user_id)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no songs in your playlists")

    seen: set[int] = set()
    ranked: list[tuple[int, Song]] = []
    for song, tags in rows:
        if song.id in seen:
            continue
        seen.add(song.id)
        if current_song_id and song.id == current_song_id:
            continue
        score = _score_song(tags, profile, mode, target_energy)
        ranked.append((score, song))

    random.shuffle(ranked)
    ranked.sort(key=lambda item: -item[0])
    return [
        RecommendedSongItem(song_id=song.id, title=song.title, artist=song.artist, in_library=True)
        for _, song in ranked[:10]
    ]


# ───────────── Vibe search (CLAP + Spotify hybrid) ─────────────

import logging as _logging

_vibe_logger = _logging.getLogger(__name__)


def vibe_search(
    db: Session,
    query: str,
    user_id: Optional[int] = None,
    top_k: int = 10,
) -> VibeSearchData:
    """Search songs by natural-language vibe description.

    Pipeline:
    1. interpret_vibe  → genres + vibe_description + Spotify search_query
    2. CLAP text→audio → search local library via ChromaDB
    3. Spotify search  → candidate tracks from Spotify catalog
    4. Merge & sort by real similarity
    """
    from app.modules.recommendations.vibe_service import interpret_vibe
    from app.modules.recommendations.spotify_service import search_tracks

    vibe = interpret_vibe(query)
    spotify_query = vibe.get("search_query", "")
    vibe_desc = vibe["vibe_description"]
    genres = vibe.get("genres", [])

    songs: list[VibeSearchSongItem] = []

    # ── Step 1: CLAP cross-modal search in local library ──
    try:
        from app.modules.recommendations.vector_store import search_songs as clap_search
        local_results = clap_search(vibe_desc, top_k=top_k)
        _vibe_logger.info("[vibe] CLAP returned %d local results", len(local_results))

        for row in local_results:
            # cosine distance → match percentage (0=perfect, 2=worst for cosine)
            distance = row.get("distance", 1.0)
            match_pct = round(max(0, (1.0 - distance)) * 100, 1)
            song_id_str = row.get("song_id")
            song_id = int(song_id_str) if song_id_str else None

            # Check if song is in user's library
            in_lib = False
            if song_id and user_id:
                lib_song = (
                    db.query(LibrarySong)
                    .filter(LibrarySong.song_id == song_id, LibrarySong.user_id == user_id)
                    .first()
                )
                in_lib = lib_song is not None

            songs.append(VibeSearchSongItem(
                song_id=song_id,
                title=row.get("title", "Unknown"),
                artist=row.get("artist", "Unknown"),
                style=row.get("style"),
                energy=row.get("energy"),
                source="local",
                in_library=in_lib,
                match_percentage=match_pct,
            ))
    except Exception:
        _vibe_logger.warning("[vibe] CLAP local search failed, skipping", exc_info=True)

    # ── Step 2: Spotify search ──
    spotify_songs: list[VibeSearchSongItem] = []
    if spotify_query:
        try:
            spotify_tracks = search_tracks(spotify_query, limit=min(top_k, 10))
            _vibe_logger.info("[vibe] Spotify returned %d results", len(spotify_tracks))

            for i, track in enumerate(spotify_tracks):
                # Position-based score (Spotify relevance) scaled to [0, 80]
                # Local CLAP results can score up to 100, Spotify max 80
                match_pct = round((1.0 - i / max(len(spotify_tracks), 1)) * 80, 1)
                spotify_songs.append(VibeSearchSongItem(
                    title=track["title"],
                    artist=track["artist"],
                    spotify_id=track.get("spotify_id"),
                    preview_url=track.get("preview_url"),
                    album_art=track.get("album_art"),
                    spotify_url=track.get("spotify_url"),
                    source="spotify",
                    in_library=False,
                    match_percentage=match_pct,
                ))
        except Exception:
            _vibe_logger.warning("[vibe] Spotify search failed, skipping", exc_info=True)

    # ── Step 3: Merge & sort ──
    # Deduplicate: if a Spotify track matches a local song by title+artist, keep local
    local_keys = {(s.title.lower(), s.artist.lower()) for s in songs}
    for sp_song in spotify_songs:
        key = (sp_song.title.lower(), sp_song.artist.lower())
        if key not in local_keys:
            songs.append(sp_song)

    # Sort by match_percentage descending
    songs.sort(key=lambda s: s.match_percentage, reverse=True)
    songs = songs[:top_k]

    return VibeSearchData(
        query=query,
        vibe_description=vibe_desc,
        search_query=spotify_query,
        genres=genres,
        songs=songs,
    )


# ───────────── Import from vibe / playlist pipelines ─────────────


def import_from_vibe(
    db: Session,
    user_id: int,
    vibe_description: str,
    top_k: int = 5,
    auto_import: bool = True,
) -> dict:
    """Full pipeline: vibe → Spotify search → CLAP rerank → download → index.

    Returns ImportFromVibeData-compatible dict.
    """
    from app.modules.recommendations.vibe_service import interpret_vibe
    from app.modules.recommendations.spotify_service import search_tracks
    from app.modules.recommendations.rerank_service import rerank_tracks
    from app.modules.recommendations.ingest_service import ingest_spotify_tracks

    vibe = interpret_vibe(vibe_description)
    spotify_query = vibe["search_query"]
    vibe_desc = vibe["vibe_description"]
    genres = vibe.get("genres", [])

    # Step 1: Spotify search
    spotify_raw = search_tracks(spotify_query, limit=min(top_k * 3, 10))
    spotify_candidates: list[dict] = []
    for item in spotify_raw:
        spotify_candidates.append(VibeSearchSongItem(
            title=item["title"],
            artist=item["artist"],
            spotify_id=item.get("spotify_id"),
            preview_url=item.get("preview_url"),
            album_art=item.get("album_art"),
            spotify_url=item.get("spotify_url"),
            source="spotify",
            in_library=False,
            match_percentage=0.0,
        ))

    # Step 2: CLAP rerank
    if spotify_raw:
        reranked = rerank_tracks(vibe_desc, spotify_raw)
    else:
        reranked = []
    top_tracks = reranked[:top_k]

    # Build enriched song items for reranked results
    reranked_items: list[dict] = []
    for t in top_tracks:
        t_info = t.get("track") or t
        reranked_items.append({
            "title": str(t_info.get("name") or t.get("title") or ""),
            "artist": (
                ", ".join(a.get("name", "") for a in (t_info.get("artists") or []))
                or str(t.get("artist") or "")
            ),
            "spotify_id": str(t_info.get("id") or t.get("spotify_id") or ""),
            "semantic_score": t.get("semantic_score", 0),
        })

    # Step 3: Download + index
    ingested: list[dict] = []
    if auto_import and top_tracks:
        ingested = ingest_spotify_tracks(top_tracks)

    success_count = sum(1 for r in ingested if r.get("success"))
    return {
        "vibe_description": vibe_desc,
        "search_query": spotify_query,
        "genres": genres,
        "spotify_candidates": spotify_candidates,
        "reranked_candidates": reranked_items,
        "ingested_tracks": ingested,
        "pipeline_summary": (
            f"Spotify returned {len(spotify_raw)} tracks, "
            f"CLAP reranked to {len(reranked_items)}, "
            f"ingested {success_count}/{len(ingested)} successfully."
        ),
    }


def import_playlist_spotify(
    db: Session,
    user_id: int,
    playlist_url: str,
    auto_import: bool = True,
) -> dict:
    """Import a Spotify playlist: fetch tracks → download → index.

    Returns ImportPlaylistData-compatible dict.
    """
    from app.modules.recommendations.spotify_service import fetch_playlist_tracks
    from app.modules.recommendations.ingest_service import ingest_spotify_tracks

    tracks = fetch_playlist_tracks(playlist_url)
    if not tracks:
        return {
            "playlist_name": "",
            "track_count": 0,
            "ingested_tracks": [],
            "pipeline_summary": "No tracks found in playlist.",
        }

    ingested: list[dict] = []
    if auto_import:
        ingested = ingest_spotify_tracks(tracks)

    success_count = sum(1 for r in ingested if r.get("success"))
    return {
        "playlist_name": f"Spotify playlist ({len(tracks)} tracks)",
        "track_count": len(tracks),
        "ingested_tracks": ingested,
        "pipeline_summary": (
            f"Fetched {len(tracks)} tracks, "
            f"ingested {success_count}/{len(ingested)} successfully."
        ),
    }
