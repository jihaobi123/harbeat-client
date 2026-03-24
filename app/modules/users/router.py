from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.responses import APIResponse
from app.modules.users.schemas import UserCreateData, UserCreateRequest, UserData
from app.modules.users.service import create_user, get_user_or_404

router = APIRouter()


@router.post("", response_model=APIResponse[UserCreateData])
def create_user_endpoint(payload: UserCreateRequest, db: Session = Depends(get_db)):
    user = create_user(db, payload)
    return APIResponse(data=UserCreateData(user_id=user.id))


@router.get("/{user_id}", response_model=APIResponse[UserData])
def get_user_endpoint(user_id: int, db: Session = Depends(get_db)):
    user = get_user_or_404(db, user_id)
    return APIResponse(data=UserData.model_validate(user))
