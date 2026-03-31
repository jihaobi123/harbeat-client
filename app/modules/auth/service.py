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
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


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
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> User:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if not user.password_hash or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return user
