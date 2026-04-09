from __future__ import annotations

from datetime import datetime

import jwt
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.users.models import User
from app.shared.redis import blacklist_token, is_token_blacklisted
from app.shared.security import (
    create_access_token as create_access_token_base,
    create_refresh_token as create_refresh_token_base,
    decode_access_token as decode_access_token_base,
    hash_password,
    verify_password,
)


# ── Token helpers ────────────────────────────────────────────────────

def create_token_pair(user: User) -> tuple[str, str]:
    claims = {"username": user.username, "role": user.role}
    access = create_access_token_base(str(user.id), extra_claims=claims)
    refresh = create_refresh_token_base(str(user.id))
    return access, refresh


def create_access_token(user_id: int, username: str) -> str:
    return create_access_token_base(str(user_id), extra_claims={"username": username})


def decode_access_token(token: str) -> dict:
    try:
        return decode_access_token_base(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")


# ── Active-user base query ───────────────────────────────────────────

def _active_q(db: Session):
    return db.query(User).filter(User.is_deleted.is_(False))


# ── Register ─────────────────────────────────────────────────────────

def register_user(
    db: Session,
    username: str,
    password: str,
    dance_style: str,
    level: str,
    favorite_style: str,
    email: str | None = None,
) -> User:
    normalized_username = username.strip()
    normalized_email = email.strip().lower() if email else None

    if _active_q(db).filter(func.lower(User.username) == normalized_username.lower()).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="username already exists")

    if normalized_email:
        if _active_q(db).filter(func.lower(User.email) == normalized_email).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists")

    user = User(
        username=normalized_username,
        email=normalized_email,
        password_hash=hash_password(password),
        dance_style=dance_style,
        level=level,
        favorite_style=favorite_style,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── Login ────────────────────────────────────────────────────────────

def authenticate_user(db: Session, username: str, password: str) -> User:
    normalized = username.strip().lower()
    user = _active_q(db).filter(func.lower(User.username) == normalized).first()
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is not active")

    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


# ── Refresh ──────────────────────────────────────────────────────────

def refresh_access_token(db: Session, refresh_token: str) -> tuple[User, str, str]:
    payload = decode_access_token(refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token type")

    jti = payload.get("jti")
    if jti and is_token_blacklisted(jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token revoked")

    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    user = _active_q(db).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is not active")

    # Rotate: blacklist old refresh token, issue new pair
    exp = payload.get("exp", 0)
    ttl = max(int(exp - datetime.utcnow().timestamp()), 1)
    if jti:
        blacklist_token(jti, ttl)

    access, new_refresh = create_token_pair(user)
    return user, access, new_refresh


# ── Logout ───────────────────────────────────────────────────────────

def logout_token(raw_token: str) -> None:
    payload = decode_access_token(raw_token)
    jti = payload.get("jti")
    if not jti:
        return
    exp = payload.get("exp", 0)
    ttl = max(int(exp - datetime.utcnow().timestamp()), 1)
    blacklist_token(jti, ttl)


# ── Change Password ─────────────────────────────────────────────────

def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not user.password_hash or not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="current password is incorrect")
    user.password_hash = hash_password(new_password)
    db.commit()


# ── Deactivate own account ──────────────────────────────────────────

def deactivate_account(db: Session, user: User) -> None:
    user.status = "disabled"
    db.commit()
