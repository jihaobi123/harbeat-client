from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.users.models import User
from app.shared.audit import log_action
from app.shared.database import get_db
from app.shared.responses import APIResponse
from app.modules.users.schemas import SuccessData, UserCreateData, UserCreateRequest, UserData, UserListData, UserListQuery, UserRoleUpdateRequest, UserStatusUpdateRequest, UserUpdateRequest
from app.modules.users.service import (
    create_user,
    ensure_admin,
    ensure_can_manage_user,
    get_user_by_username,
    get_user_or_404,
    list_users,
    soft_delete_user,
    update_user,
    update_user_role,
    update_user_status,
)

router = APIRouter()


@router.post("", response_model=APIResponse[UserCreateData])
def create_user_endpoint(payload: UserCreateRequest, db: Session = Depends(get_db)):
    user = create_user(db, payload)
    return APIResponse(data=UserCreateData(user_id=user.id))


@router.get("/by-username/{username}", response_model=APIResponse[UserData])
def get_user_by_username_endpoint(username: str, db: Session = Depends(get_db)):
    user = get_user_by_username(db, username)
    return APIResponse(data=UserData.model_validate(user))


@router.get("/{user_id}", response_model=APIResponse[UserData])
def get_user_endpoint(user_id: int, db: Session = Depends(get_db)):
    user = get_user_or_404(db, user_id)
    return APIResponse(data=UserData.model_validate(user))


@router.get("", response_model=APIResponse[UserListData])
def list_users_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_admin(current_user)
    data = list_users(
        db,
        UserListQuery(page=page, page_size=page_size, keyword=keyword, status=status),
    )
    return APIResponse(data=data)


@router.patch("/{user_id}", response_model=APIResponse[UserData])
def update_user_endpoint(
    user_id: int,
    payload: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = get_user_or_404(db, user_id)
    ensure_can_manage_user(current_user, target_user)
    updated = update_user(db, target_user, payload)
    log_action(db, actor_id=current_user.id, action="update_user", target_id=user_id, detail=str(payload.model_dump(exclude_unset=True)))
    return APIResponse(data=UserData.model_validate(updated))


@router.patch("/{user_id}/status", response_model=APIResponse[UserData])
def update_user_status_endpoint(
    user_id: int,
    payload: UserStatusUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_admin(current_user)
    target_user = get_user_or_404(db, user_id)
    updated = update_user_status(db, target_user, payload.status)
    log_action(db, actor_id=current_user.id, action="update_status", target_id=user_id, detail=f"status={payload.status}")
    return APIResponse(data=UserData.model_validate(updated))


@router.patch("/{user_id}/role", response_model=APIResponse[UserData])
def update_user_role_endpoint(
    user_id: int,
    payload: UserRoleUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ensure_admin(current_user)
    target_user = get_user_or_404(db, user_id)
    updated = update_user_role(db, target_user, payload.role)
    log_action(db, actor_id=current_user.id, action="update_role", target_id=user_id, detail=f"role={payload.role}")
    return APIResponse(data=UserData.model_validate(updated))


@router.delete("/{user_id}", response_model=APIResponse[SuccessData])
def delete_user_endpoint(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_user = get_user_or_404(db, user_id)
    ensure_can_manage_user(current_user, target_user)
    soft_delete_user(db, target_user)
    log_action(db, actor_id=current_user.id, action="delete_user", target_id=user_id)
    return APIResponse(data=SuccessData())
