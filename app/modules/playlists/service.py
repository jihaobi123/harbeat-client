from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.playlists.models import Playlist, PlaylistSong, Song
from app.modules.playlists.models import SongTag
from app.modules.library.models import LibrarySong
from app.modules.playlists.schemas import (
    PlaylistDetailData,
    PlaylistImportRequest,
    PlaylistListData,
    PlaylistSongData,
    PlaylistSummaryData,
)
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
                audio_url=str(item.audio_url) if item.audio_url else None,
                duration=item.duration,
            )
            db.add(song)
            db.flush()
            if item.bpm is not None or item.tags:
                db.add(
                    SongTag(
                        song_id=song.id,
                        bpm=item.bpm,
                        style=",".join(item.tags) if item.tags else None,
                    )
                )
        elif (item.bpm is not None or item.tags) and song.tags is None:
            db.add(
                SongTag(
                    song_id=song.id,
                    bpm=item.bpm,
                    style=",".join(item.tags) if item.tags else None,
                )
            )
        elif song.tags is not None:
            if item.bpm is not None:
                song.tags.bpm = item.bpm
            if item.tags:
                song.tags.style = ",".join(item.tags)

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


def list_playlists(db: Session, user_id: int) -> PlaylistListData:
    get_user_or_404(db, user_id)
    playlists = (
        db.query(Playlist)
        .filter(Playlist.user_id == user_id)
        .order_by(Playlist.created_at.desc())
        .all()
    )

    # In server-centric model, all songs are available on server
    return PlaylistListData(
        playlists=[
            PlaylistSummaryData(
                id=playlist.id,
                user_id=playlist.user_id,
                playlist_name=playlist.playlist_name,
                source_type=playlist.source_type,
                song_count=len(playlist.songs),
            )
            for playlist in playlists
        ]
    )


def get_playlist_detail(db: Session, playlist_id: int) -> PlaylistDetailData:
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found")

    songs = (
        db.query(PlaylistSong)
        .filter(PlaylistSong.playlist_id == playlist_id)
        .order_by(PlaylistSong.order_index.asc())
        .all()
    )

    # In server-centric model, show all songs (not filtered by local library)
    return PlaylistDetailData(
        id=playlist.id,
        user_id=playlist.user_id,
        playlist_name=playlist.playlist_name,
        source_type=playlist.source_type,
        songs=[
            PlaylistSongData(
                song_id=item.song.id,
                title=item.song.title,
                artist=item.song.artist,
                audio_url=item.song.audio_url,
                duration=item.song.duration,
                bpm=item.song.tags.bpm if item.song.tags else None,
                tags=[part for part in (item.song.tags.style or "").split(",") if part] if item.song.tags else [],
                order_index=item.order_index,
            )
            for item in songs
        ],
    )


def delete_playlist(db: Session, playlist_id: int) -> None:
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found")
    db.delete(playlist)
    db.commit()


def update_playlist_song_tags(db: Session, playlist_id: int, song_id: int, tags: list[str]) -> None:
    relation = (
        db.query(PlaylistSong)
        .filter(PlaylistSong.playlist_id == playlist_id, PlaylistSong.song_id == song_id)
        .first()
    )
    if not relation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist song not found")

    tag = relation.song.tags
    if tag is None:
        tag = SongTag(song_id=song_id)
        db.add(tag)
    tag.style = ",".join(tags) if tags else None
    db.commit()


def create_empty_playlist(db: Session, user_id: int, name: str) -> Playlist:
    """Create an empty playlist."""
    playlist = Playlist(
        user_id=user_id,
        playlist_name=name,
        source_type="manual",
    )
    db.add(playlist)
    db.commit()
    db.refresh(playlist)
    return playlist


def add_library_songs_to_playlist(
    db: Session, playlist_id: int, user_id: int, library_song_ids: list[str]
) -> int:
    """Add library songs to a playlist. Returns the count of newly added songs."""
    playlist = db.query(Playlist).filter(Playlist.id == playlist_id).first()
    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="playlist not found")
    if playlist.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your playlist")

    # Get current max order_index
    max_order = (
        db.query(PlaylistSong.order_index)
        .filter(PlaylistSong.playlist_id == playlist_id)
        .order_by(PlaylistSong.order_index.desc())
        .first()
    )
    next_order = (max_order[0] + 1) if max_order else 0

    added = 0
    for lib_song_id in library_song_ids:
        lib_song = db.get(LibrarySong, lib_song_id)
        if not lib_song or lib_song.user_id != user_id:
            continue

        # Get or create the Song record
        song = (
            db.query(Song)
            .filter(Song.title == lib_song.title, Song.artist == lib_song.artist)
            .first()
        )
        if not song:
            song = Song(
                title=lib_song.title,
                artist=lib_song.artist,
                duration=lib_song.duration,
            )
            db.add(song)
            db.flush()

        # Link library_song → catalog song if not already linked
        if lib_song.song_id != song.id:
            lib_song.song_id = song.id

        # Check for duplicate
        existing = (
            db.query(PlaylistSong)
            .filter(PlaylistSong.playlist_id == playlist_id, PlaylistSong.song_id == song.id)
            .first()
        )
        if existing:
            continue

        db.add(PlaylistSong(
            playlist_id=playlist_id,
            song_id=song.id,
            order_index=next_order,
        ))
        next_order += 1
        added += 1

    db.commit()
    return added
