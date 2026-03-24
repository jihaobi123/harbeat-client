from fastapi import APIRouter

from app.modules.health.router import router as health_router
from app.modules.library.router import router as library_router
from app.modules.playlists.router import router as playlists_router
from app.modules.profiles.router import router as profiles_router
from app.modules.recommendations.router import router as recommendations_router
from app.modules.sessions.router import router as sessions_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(library_router, prefix="/api/library", tags=["library"])
api_router.include_router(users_router, prefix="/api/users", tags=["users"])
api_router.include_router(playlists_router, prefix="/api/playlists", tags=["playlists"])
api_router.include_router(profiles_router, prefix="/api/profiles", tags=["profiles"])
api_router.include_router(
    recommendations_router,
    prefix="/api/recommendations",
    tags=["recommendations"],
)
api_router.include_router(sessions_router, prefix="/api/sessions", tags=["sessions"])

