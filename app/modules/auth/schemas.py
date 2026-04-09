from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=8, max_length=64)
    email: EmailStr | None = None
    dance_style: str = "hiphop"
    level: str = "beginner"
    favorite_style: str = "hiphop"


class LoginRequest(BaseModel):
    username: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=64)


class TokenData(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    username: str


class UserMeData(BaseModel):
    id: int
    username: str
    email: str | None
    role: str
    status: str
    dance_style: str
    level: str
    favorite_style: str
    last_login_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SuccessMsg(BaseModel):
    success: bool = True
    message: str = "ok"
