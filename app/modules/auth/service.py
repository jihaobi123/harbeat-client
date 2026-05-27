from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256

import jwt
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.users.models import User
from app.shared.config import get_settings


def hash_password(password: str) -> str:
    settings = get_settings()
    salted = f"{settings.jwt_secret}:{password}"
    return sha256(salted.encode()).hexdigest()


def verify_password(password: str, hashed: str) -> bool:
    return hash_password(password) == hashed


def create_access_token(user_id: int, username: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
        "type": "access"
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: int, username: str) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(days=30)  # refresh token 30天有效
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
        "type": "refresh"
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


def decode_refresh_token(token: str) -> dict:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")


def register_user(db: Session, username: str, password: str, dance_style: str, level: str, favorite_style: str) -> User:
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

    user = User(
        username=username,
        password_hash=hash_password(password),
        dance_style=dance_style,
        level=level,
        favorite_style=favorite_style,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="account is deactivated")
    if not user.password_hash or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return user


def change_user_password(db: Session, user: User, old_password: str, new_password: str) -> None:
    if not user.password_hash or not verify_password(old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid old password")

    user.password_hash = hash_password(new_password)
    db.commit()


def deactivate_user(db: Session, user: User) -> None:
    user.is_active = False
    db.commit()
