from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.modules.users.models import User
from app.modules.users.schemas import UserCreateRequest, UserListData, UserListQuery, UserUpdateRequest
from app.shared.security import hash_password

ACTIVE_STATUS = "active"
DISABLED_STATUS = "disabled"
DELETED_STATUS = "deleted"
ADMIN_ROLE = "admin"


def _build_active_user_query(db: Session):
    return db.query(User).filter(User.is_deleted.is_(False))


def create_user(db: Session, payload: UserCreateRequest) -> User:
    existing = _build_active_user_query(db).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="username already exists",
        )

    if payload.email:
        existing_email = _build_active_user_query(db).filter(User.email == payload.email).first()
        if existing_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists")

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password) if payload.password else None,
        dance_style=payload.dance_style,
        level=payload.level,
        favorite_style=payload.favorite_style,
        role="user",
        status=ACTIVE_STATUS,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_or_404(db: Session, user_id: int) -> User:
    user = _build_active_user_query(db).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user


def get_user_by_username(db: Session, username: str) -> User:
    user = _build_active_user_query(db).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user


def get_user_or_401(db: Session, user_id: int) -> User:
    user = _build_active_user_query(db).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    if user.status != ACTIVE_STATUS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is not active")
    return user


def list_users(db: Session, query: UserListQuery) -> UserListData:
    q = _build_active_user_query(db)

    if query.keyword:
        keyword = f"%{query.keyword}%"
        q = q.filter((User.username.ilike(keyword)) | (User.email.ilike(keyword)))

    if query.status:
        q = q.filter(User.status == query.status)

    total = q.count()
    items = (
        q.order_by(User.id.desc())
        .offset((query.page - 1) * query.page_size)
        .limit(query.page_size)
        .all()
    )
    return UserListData(items=items, total=total, page=query.page, page_size=query.page_size)


def update_user(db: Session, target_user: User, payload: UserUpdateRequest) -> User:
    updates = payload.model_dump(exclude_unset=True)
    if "email" in updates and updates["email"]:
        existing_email = (
            _build_active_user_query(db)
            .filter(User.email == updates["email"], User.id != target_user.id)
            .first()
        )
        if existing_email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email already exists")

    for key, value in updates.items():
        setattr(target_user, key, value)

    db.commit()
    db.refresh(target_user)
    return target_user


def update_user_status(db: Session, target_user: User, status_value: str) -> User:
    target_user.status = status_value
    db.commit()
    db.refresh(target_user)
    return target_user


def update_user_role(db: Session, target_user: User, role_value: str) -> User:
    target_user.role = role_value
    db.commit()
    db.refresh(target_user)
    return target_user


def soft_delete_user(db: Session, target_user: User) -> None:
    target_user.is_deleted = True
    target_user.status = DELETED_STATUS
    db.commit()


def ensure_can_manage_user(current_user: User, target_user: User) -> None:
    if current_user.role == ADMIN_ROLE:
        return
    if current_user.id != target_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")


def ensure_admin(current_user: User) -> None:
    if current_user.role != ADMIN_ROLE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin required")
