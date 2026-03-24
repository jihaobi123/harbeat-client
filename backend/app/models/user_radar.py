from sqlalchemy import Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UserRadar(Base):
    __tablename__ = "user_radars"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    style_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
