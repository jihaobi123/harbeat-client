from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RegisterRequest(BaseModel):
    username: str
    password: str
    dance_style: str = "hiphop"
    level: str = "beginner"
    favorite_style: str = "hiphop"


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenData(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: int
    username: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class UserMeData(BaseModel):
    id: int
    username: str
    dance_style: str
    level: str
    favorite_style: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
