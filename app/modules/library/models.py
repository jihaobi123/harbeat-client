from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Float, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.database import Base


class LibrarySong(Base):
    __tablename__ = "library_songs"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    song_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("songs.id"), nullable=True, index=True
    )
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
    key: Mapped[str | None] = mapped_column(String(50))
    camelot_key: Mapped[str | None] = mapped_column(String(10))
    energy: Mapped[float | None] = mapped_column(Float)
    music_features: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    dance_styles: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    dance_style_scores: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    dance_style_status: Mapped[str] = mapped_column(String(50), default="none", nullable=False)
    analysis_status: Mapped[str] = mapped_column(String(50), default="none", nullable=False)
    beat_points: Mapped[list[float]] = mapped_column(JSON, default=list, nullable=False)
    bpm_curve: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    tempo_stability: Mapped[float | None] = mapped_column(Float)
    energy_curve: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    transition_windows: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    stem_activity: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    stem_activity_windows: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    stem_quality_score: Mapped[float | None] = mapped_column(Float)
    intro_is_clean: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)
    outro_is_clean: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)
    has_drum_loop: Mapped[bool] = mapped_column(Integer, default=0, nullable=False)
    cue_points: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    downbeats: Mapped[list[float]] = mapped_column(JSON, default=list, nullable=False)
    phrase_map: Mapped[list[dict]] = mapped_column(JSON, default=list, nullable=False)
    key_confidence: Mapped[float | None] = mapped_column(Float)
    stems: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationship to catalog Song (for tags/recommendations)
    song = relationship("Song", foreign_keys=[song_id], lazy="joined")
