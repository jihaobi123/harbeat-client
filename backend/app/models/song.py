from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.config import get_settings
from app.db import Base

settings = get_settings()


class Song(Base):
    __tablename__ = "songs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    artist: Mapped[str] = mapped_column(String(255), nullable=False)
    genre: Mapped[str] = mapped_column(String(100), nullable=False, default="hiphop")
    bpm: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.vector_dim), nullable=False)
