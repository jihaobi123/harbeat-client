from __future__ import annotations

from collections import Counter
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.playlists.models import Playlist, PlaylistSong, Song, SongTag
from app.modules.profiles.schemas import UserProfileData
from app.modules.users.models import UserProfileTag
from app.modules.users.service import get_user_or_404


def _pick_most_common(values: list[Optional[str]], fallback: Optional[str] = None) -> Optional[str]:
    filtered = [value for value in values if value]
    if not filtered:
        return fallback
    return Counter(filtered).most_common(1)[0][0]


def _expand_styles(values: list[Optional[str]]) -> list[str]:
    expanded: list[str] = []
    for value in values:
        if not value:
            continue
        expanded.extend([item.strip() for item in value.split(",") if item.strip()])
    return expanded


def generate_profile(db: Session, user_id: int) -> UserProfileData:
    user = get_user_or_404(db, user_id)

    rows = (
        db.query(SongTag)
        .join(Song, Song.id == SongTag.song_id)
        .join(PlaylistSong, PlaylistSong.song_id == Song.id)
        .join(Playlist, Playlist.id == PlaylistSong.playlist_id)
        .filter(Playlist.user_id == user_id)
        .all()
    )

    avg_bpm = None
    if rows:
        bpm_values = [row.bpm for row in rows if row.bpm is not None]
        if bpm_values:
            avg_bpm = int(sum(bpm_values) / len(bpm_values))

    profile_data = UserProfileData(
        favorite_style=_pick_most_common(_expand_styles([row.style for row in rows]), fallback=user.favorite_style)
        or user.favorite_style,
        avg_bpm_preference=avg_bpm,
        energy_preference=_pick_most_common([row.energy for row in rows]),
        vocal_preference=_pick_most_common([row.vocal_type for row in rows]),
        era_preference=_pick_most_common([row.era_tag for row in rows], fallback=user.favorite_style),
        groove_preference=_pick_most_common([row.groove_tag for row in rows]),
    )

    profile = db.query(UserProfileTag).filter(UserProfileTag.user_id == user_id).first()
    if profile is None:
        profile = UserProfileTag(user_id=user_id, **profile_data.model_dump())
        db.add(profile)
    else:
        for key, value in profile_data.model_dump().items():
            setattr(profile, key, value)

    db.commit()
    return profile_data


def get_profile_or_404(db: Session, user_id: int) -> UserProfileTag:
    get_user_or_404(db, user_id)
    profile = db.query(UserProfileTag).filter(UserProfileTag.user_id == user_id).first()
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    return profile
