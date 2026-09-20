from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database import Base


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    playlist_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    songs: Mapped[list["PlaylistSong"]] = relationship(
        back_populates="playlist",
        cascade="all, delete-orphan",
    )


class Song(Base):
    __tablename__ = "songs"
    __table_args__ = (UniqueConstraint("title", "artist", name="uq_song_title_artist"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[str] = mapped_column(String(255), nullable=False)
    audio_url: Mapped[Optional[str]] = mapped_column(String(1024))
    duration: Mapped[Optional[float]] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    tags: Mapped[Optional["SongTag"]] = relationship(
        back_populates="song",
        cascade="all, delete-orphan",
        uselist=False,
    )
    playlists: Mapped[list["PlaylistSong"]] = relationship(
        back_populates="song",
        cascade="all, delete-orphan",
    )


class PlaylistSong(Base):
    __tablename__ = "playlist_songs"
    __table_args__ = (UniqueConstraint("playlist_id", "song_id", name="uq_playlist_song"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id"), nullable=False, index=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)

    playlist: Mapped["Playlist"] = relationship(back_populates="songs")
    song: Mapped["Song"] = relationship(back_populates="playlists")


class SongTag(Base):
    __tablename__ = "song_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    song_id: Mapped[int] = mapped_column(ForeignKey("songs.id"), nullable=False, unique=True, index=True)
    bpm: Mapped[Optional[int]] = mapped_column(Integer)
    energy: Mapped[Optional[str]] = mapped_column(String(50))
    style: Mapped[Optional[str]] = mapped_column(String(100))
    vocal_type: Mapped[Optional[str]] = mapped_column(String(100))
    era_tag: Mapped[Optional[str]] = mapped_column(String(100))
    groove_tag: Mapped[Optional[str]] = mapped_column(String(100))
    difficulty_fit: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    song: Mapped["Song"] = relationship(back_populates="tags")
