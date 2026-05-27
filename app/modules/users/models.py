from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dance_style: Mapped[str] = mapped_column(String(100), nullable=False)
    level: Mapped[str] = mapped_column(String(50), nullable=False)
    favorite_style: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )


class UserProfileTag(Base):
    __tablename__ = "user_profile_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    favorite_style: Mapped[str] = mapped_column(String(100), nullable=False)
    avg_bpm_preference: Mapped[Optional[int]] = mapped_column(Integer)
    energy_preference: Mapped[Optional[str]] = mapped_column(String(100))
    vocal_preference: Mapped[Optional[str]] = mapped_column(String(100))
    era_preference: Mapped[Optional[str]] = mapped_column(String(100))
    groove_preference: Mapped[Optional[str]] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
