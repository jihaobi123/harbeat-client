import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenData,
    UserMeData,
)
from app.modules.auth.service import (
    authenticate_user,
    change_user_password,
    create_access_token,
    create_refresh_token,
    deactivate_user,
    decode_refresh_token,
    register_user,
)
from app.modules.users.models import User
from app.shared.database import get_db
from app.shared.responses import APIResponse

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/register", response_model=APIResponse[TokenData])
def register_endpoint(payload: RegisterRequest, db: Session = Depends(get_db)):
    logger.warning("[REGISTER] username=%s", payload.username)
    user = register_user(
        db,
        username=payload.username,
        password=payload.password,
        dance_style=payload.dance_style,
        level=payload.level,
        favorite_style=payload.favorite_style,
    )
    access_token = create_access_token(user.id, user.username)
    refresh_token = create_refresh_token(user.id, user.username)
    return APIResponse(
        data=TokenData(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user.id,
            username=user.username,
        )
    )


@router.post("/login", response_model=APIResponse[TokenData])
def login_endpoint(payload: LoginRequest, db: Session = Depends(get_db)):
    logger.warning("[LOGIN] username=%s", payload.username)
    user = authenticate_user(db, payload.username, payload.password)
    access_token = create_access_token(user.id, user.username)
    refresh_token = create_refresh_token(user.id, user.username)
    return APIResponse(
        data=TokenData(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user.id,
            username=user.username,
        )
    )


@router.post("/refresh", response_model=APIResponse[TokenData])
def refresh_token_endpoint(payload: RefreshTokenRequest, db: Session = Depends(get_db)):
    token_data = decode_refresh_token(payload.refresh_token)
    user_id = int(token_data["sub"])
    username = token_data["username"]

    # 验证用户仍然存在且活跃
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.is_active:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found or deactivated")

    access_token = create_access_token(user_id, username)
    refresh_token = create_refresh_token(user_id, username)
    return APIResponse(
        data=TokenData(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user_id,
            username=username,
        )
    )


@router.post("/logout", response_model=APIResponse[dict])
def logout_endpoint(current_user: User = Depends(get_current_user)):
    # JWT 是无状态的，客户端删除 token 即可
    # 这里只是提供一个端点让客户端知道登出成功
    logger.warning("[LOGOUT] user_id=%s", current_user.id)
    return APIResponse(data={"message": "logged out successfully"})


@router.get("/me", response_model=APIResponse[UserMeData])
def get_me_endpoint(current_user: User = Depends(get_current_user)):
    return APIResponse(data=UserMeData.model_validate(current_user))


@router.post("/change-password", response_model=APIResponse[dict])
def change_password_endpoint(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    change_user_password(db, current_user, payload.old_password, payload.new_password)
    logger.warning("[CHANGE_PASSWORD] user_id=%s", current_user.id)
    return APIResponse(data={"message": "password changed successfully"})


@router.post("/deactivate", response_model=APIResponse[dict])
def deactivate_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deactivate_user(db, current_user)
    logger.warning("[DEACTIVATE] user_id=%s", current_user.id)
    return APIResponse(data={"message": "account deactivated successfully"})
