from fastapi import APIRouter

from app.shared.responses import APIResponse

router = APIRouter()


@router.get("/health", response_model=APIResponse[dict[str, str]])
def health_check():
    return APIResponse(data={"status": "ok"})
