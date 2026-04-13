import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    SuccessMsg,
    TokenData,
    UserMeData,
)
from app.modules.auth.service import (
    authenticate_user,
    change_password,
    create_token_pair,
    deactivate_account,
    logout_token,
    refresh_access_token,
    register_user,
)
from app.modules.users.models import User
from app.shared.database import get_db
from app.shared.responses import APIResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/register", response_model=APIResponse[TokenData])
def register_endpoint(payload: RegisterRequest, db: Session = Depends(get_db)):
    logger.info("[REGISTER] username=%s", payload.username)
    user = register_user(
        db,
        username=payload.username,
        password=payload.password,
        dance_style=payload.dance_style,
        level=payload.level,
        favorite_style=payload.favorite_style,
    )
    access, refresh = create_token_pair(user)
    return APIResponse(
        data=TokenData(access_token=access, refresh_token=refresh, user_id=user.id, username=user.username),
    )


@router.post("/login", response_model=APIResponse[TokenData])
def login_endpoint(payload: LoginRequest, db: Session = Depends(get_db)):
    logger.info("[LOGIN] username=%s", payload.username)
    user = authenticate_user(db, payload.username, payload.password)
    access, refresh = create_token_pair(user)
    return APIResponse(
        data=TokenData(access_token=access, refresh_token=refresh, user_id=user.id, username=user.username),
    )


@router.post("/refresh", response_model=APIResponse[TokenData])
def refresh_endpoint(payload: RefreshRequest, db: Session = Depends(get_db)):
    user, access, refresh = refresh_access_token(db, payload.refresh_token)
    return APIResponse(
        data=TokenData(access_token=access, refresh_token=refresh, user_id=user.id, username=user.username),
    )


@router.post("/logout", response_model=APIResponse[SuccessMsg])
def logout_endpoint(request: Request):
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        logout_token(token)
    return APIResponse(data=SuccessMsg(message="logged out"))


@router.post("/change-password", response_model=APIResponse[SuccessMsg])
def change_password_endpoint(
    payload: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    change_password(db, current_user, payload.current_password, payload.new_password)
    return APIResponse(data=SuccessMsg(message="password changed"))


@router.post("/deactivate", response_model=APIResponse[SuccessMsg])
def deactivate_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deactivate_account(db, current_user)
    return APIResponse(data=SuccessMsg(message="account deactivated"))


@router.get("/me", response_model=APIResponse[UserMeData])
def get_me_endpoint(current_user: User = Depends(get_current_user)):
    return APIResponse(data=UserMeData.model_validate(current_user))
