from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import LoginRequest, RegisterRequest, TokenData, UserMeData
from app.modules.auth.service import authenticate_user, create_access_token, register_user
from app.modules.users.models import User
from app.shared.database import get_db
from app.shared.responses import APIResponse

router = APIRouter()


@router.post("/register", response_model=APIResponse[TokenData])
def register_endpoint(payload: RegisterRequest, db: Session = Depends(get_db)):
    user = register_user(
        db,
        username=payload.username,
        password=payload.password,
        dance_style=payload.dance_style,
        level=payload.level,
        favorite_style=payload.favorite_style,
    )
    token = create_access_token(user.id, user.username)
    return APIResponse(data=TokenData(access_token=token, user_id=user.id, username=user.username))


@router.post("/login", response_model=APIResponse[TokenData])
def login_endpoint(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.username, payload.password)
    token = create_access_token(user.id, user.username)
    return APIResponse(data=TokenData(access_token=token, user_id=user.id, username=user.username))


@router.get("/me", response_model=APIResponse[UserMeData])
def get_me_endpoint(current_user: User = Depends(get_current_user)):
    return APIResponse(data=UserMeData.model_validate(current_user))
