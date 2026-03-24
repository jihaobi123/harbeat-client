from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.playlists.models import Playlist, PlaylistSong, Song
from app.modules.playlists.schemas import PlaylistImportRequest
from app.modules.users.service import get_user_or_404


def import_playlist(db: Session, payload: PlaylistImportRequest) -> tuple[Playlist, int]:
    get_user_or_404(db, payload.user_id)

    playlist = Playlist(
        user_id=payload.user_id,
        playlist_name=payload.playlist_name,
        source_type=payload.source_type,
    )
    db.add(playlist)
    db.flush()

    pending_analysis_count = 0

    for index, item in enumerate(payload.songs):
        song = (
            db.query(Song)
            .filter(Song.title == item.title, Song.artist == item.artist)
            .first()
        )
        if not song:
            song = Song(
                title=item.title,
                artist=item.artist,
                audio_url=str(item.audio_url),
                duration=item.duration,
            )
            db.add(song)
            db.flush()

        relation = PlaylistSong(
            playlist_id=playlist.id,
            song_id=song.id,
            order_index=index,
        )
        db.add(relation)

        if song.tags is None:
            pending_analysis_count += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"failed to import playlist: {exc}",
        ) from exc

    db.refresh(playlist)
    return playlist, pending_analysis_count
