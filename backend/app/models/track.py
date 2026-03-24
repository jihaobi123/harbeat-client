from sqlalchemy import Float, Integer, String
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.config import get_settings
from app.db import Base

settings = get_settings()


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    bpm: Mapped[float] = mapped_column(Float, nullable=False)
    camelot_key: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    energy: Mapped[float] = mapped_column(Float, nullable=False)
    genre_tags: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.vector_dim), nullable=False)
