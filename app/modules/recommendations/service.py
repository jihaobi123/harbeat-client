from __future__ import annotations

import random
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.library.models import LibrarySong
from app.modules.playlists.models import Playlist, PlaylistSong, Song, SongTag
from app.modules.profiles.service import get_profile_or_404
from app.modules.recommendations.schemas import RecommendedSongItem


def _score_song(
    tags: Optional[SongTag],
    profile,
    mode: str,
    target_energy: Optional[str],
) -> int:
    """Score a song against the user profile.

    If a song has NO tags for a given dimension, it is treated as matching
    any value (wildcard) and receives the corresponding base score.
    """
    score = 0

    # --- style ---
    if tags and tags.style:
        style_tokens = {t.strip() for t in tags.style.split(",") if t.strip()}
        if profile.favorite_style and profile.favorite_style in style_tokens:
            score += 3
    else:
        # No style tag → wildcard, give partial credit
        score += 1

    # --- energy ---
    if tags and tags.energy:
        energy_tokens = {e.strip() for e in tags.energy.split(",") if e.strip()}
        if target_energy and target_energy in energy_tokens:
            score += 3
        elif profile.energy_preference and profile.energy_preference in energy_tokens:
            score += 2
    else:
        # No energy tag → wildcard
        score += 1

    # --- groove / scenes ---
    if tags and tags.groove_tag:
        groove_tokens = {g.strip() for g in tags.groove_tag.split(",") if g.strip()}
        if profile.groove_preference and profile.groove_preference in groove_tokens:
            score += 1
    else:
        score += 1

    # --- mode bonus ---
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
    """Recommend songs.

    source="library"  — from user's own playlists (with their tags)
    source="server"   — from ALL songs on the server, scored by aggregated tags from all users
    """
    profile = get_profile_or_404(db, user_id)

    if source == "library":
        return _recommend_from_library(db, user_id, profile, mode, current_song_id, target_energy)
    else:
        return _recommend_from_server(db, user_id, profile, mode, current_song_id, target_energy)


def _recommend_from_library(
    db: Session,
    user_id: int,
    profile,
    mode: str,
    current_song_id: Optional[int],
    target_energy: Optional[str],
) -> list[RecommendedSongItem]:
    """Recommend from songs in the user's playlists (with tags)."""
    rows = (
        db.query(Song, SongTag)
        .join(PlaylistSong, PlaylistSong.song_id == Song.id)
        .join(Playlist, Playlist.id == PlaylistSong.playlist_id)
        .outerjoin(SongTag, SongTag.song_id == Song.id)
        .filter(Playlist.user_id == user_id)
        .all()
    )

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no songs in your playlists",
        )

    # Deduplicate by song id
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

    # Add randomness for songs with same score
    random.shuffle(ranked)
    ranked.sort(key=lambda item: -item[0])
    return [
        RecommendedSongItem(
            song_id=song.id, title=song.title, artist=song.artist, in_library=True,
        )
        for _, song in ranked[:10]
    ]


def _recommend_from_server(
    db: Session,
    user_id: int,
    profile,
    mode: str,
    current_song_id: Optional[int],
    target_energy: Optional[str],
) -> list[RecommendedSongItem]:
    """Recommend from the server-wide song pool using aggregated tags from all users."""
    rows = db.query(Song, SongTag).outerjoin(SongTag, SongTag.song_id == Song.id).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no songs available")

    # Build set of song_ids in user's library
    lib_song_ids = set(
        r[0] for r in db.query(LibrarySong.song_id)
        .filter(LibrarySong.user_id == user_id, LibrarySong.song_id.isnot(None))
        .all()
    )

    ranked: list[tuple[int, Song, bool]] = []
    for song, tags in rows:
        if current_song_id and song.id == current_song_id:
            continue
        score = _score_song(tags, profile, mode, target_energy)
        ranked.append((score, song, song.id in lib_song_ids))

    # Add randomness for songs with same score
    random.shuffle(ranked)
    ranked.sort(key=lambda item: -item[0])
    return [
        RecommendedSongItem(
            song_id=song.id, title=song.title, artist=song.artist, in_library=in_lib,
        )
        for _, song, in_lib in ranked[:10]
    ]
