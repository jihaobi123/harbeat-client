from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.playlists.models import Song, SongTag
from app.modules.profiles.service import get_profile_or_404
from app.modules.recommendations.schemas import RecommendedSongItem


def recommend_songs(
    db: Session,
    user_id: int,
    mode: str,
    current_song_id: Optional[int] = None,
    target_energy: Optional[str] = None,
) -> list[RecommendedSongItem]:
    profile = get_profile_or_404(db, user_id)

    rows = db.query(Song, SongTag).join(SongTag, SongTag.song_id == Song.id).all()
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no songs available")

    ranked: list[tuple[int, Song]] = []
    for song, tags in rows:
        if current_song_id and song.id == current_song_id:
            continue

        score = 0
        if profile.favorite_style and tags.style == profile.favorite_style:
            score += 3
        if target_energy and tags.energy == target_energy:
            score += 3
        elif profile.energy_preference and tags.energy == profile.energy_preference:
            score += 2
        if profile.era_preference and tags.era_tag == profile.era_preference:
            score += 1
        if profile.groove_preference and tags.groove_tag == profile.groove_preference:
            score += 1
        if mode == "cypher" and tags.difficulty_fit in {"intermediate", "advanced"}:
            score += 1

        ranked.append((score, song))

    ranked.sort(key=lambda item: (-item[0], item[1].id))
    return [
        RecommendedSongItem(song_id=song.id, title=song.title, artist=song.artist)
        for _, song in ranked[:10]
    ]
