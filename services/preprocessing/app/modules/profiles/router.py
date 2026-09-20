from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.shared.database import get_db
from app.shared.responses import APIResponse
from app.modules.profiles.schemas import ProfileGenerateRequest, UserProfileData
from app.modules.profiles.service import generate_profile, get_profile_or_404

router = APIRouter()


@router.post("/generate", response_model=APIResponse[UserProfileData])
def generate_profile_endpoint(payload: ProfileGenerateRequest, db: Session = Depends(get_db)):
    profile = generate_profile(db, payload.user_id)
    return APIResponse(data=profile)


@router.get("/{user_id}", response_model=APIResponse[UserProfileData])
def get_profile_endpoint(user_id: int, db: Session = Depends(get_db)):
    profile = get_profile_or_404(db, user_id)
    return APIResponse(
        data=UserProfileData(
            favorite_style=profile.favorite_style,
            avg_bpm_preference=profile.avg_bpm_preference,
            energy_preference=profile.energy_preference,
            vocal_preference=profile.vocal_preference,
            groove_preference=profile.groove_preference,
        )
    )
