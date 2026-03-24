from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import Base


class LibrarySong(Base):
    __tablename__ = "library_songs"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[str] = mapped_column(String(255), nullable=False)
    duration: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    format: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_path: Mapped[str] = mapped_column(String(2048), default="", nullable=False)
    platform_id: Mapped[str | None] = mapped_column(String(255))
    platform_url: Mapped[str | None] = mapped_column(String(1024))
    bpm: Mapped[float | None] = mapped_column(Float)
    beat_points: Mapped[list[float]] = mapped_column(JSON, default=list, nullable=False)
    cue_points: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
