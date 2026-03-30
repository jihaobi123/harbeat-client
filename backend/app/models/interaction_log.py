from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UserInteractionLog(Base):
    __tablename__ = "user_interaction_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    track_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    listen_mode: Mapped[str] = mapped_column(String(50), nullable=False)
    current_dance_style: Mapped[str] = mapped_column(String(100), nullable=False)
    play_duration_sec: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    completion_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    skip_timestamp: Mapped[float | None] = mapped_column(Float, nullable=True)
    drum_boost_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    bpm_adjusted_to: Mapped[float | None] = mapped_column(Float, nullable=True)
    ab_loop_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cue_points_added: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rewind_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
