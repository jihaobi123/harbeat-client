from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ProfileGenerateRequest(BaseModel):
    user_id: int


class UserProfileData(BaseModel):
    favorite_style: str
    avg_bpm_preference: Optional[int] = None
    energy_preference: Optional[str] = None
    vocal_preference: Optional[str] = None
    groove_preference: Optional[str] = None
