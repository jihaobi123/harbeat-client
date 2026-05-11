from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.dev_mix.router import router as dev_mix_router
from app.modules.fangpi.router import router as fangpi_router
from app.modules.health.router import router as health_router
from app.modules.library.router import router as library_router
from app.modules.music.router import router as music_router
from app.modules.playlists.router import router as playlists_router
from app.modules.profiles.router import router as profiles_router
from app.modules.recommendations.router import router as recommendations_router
from app.modules.sessions.router import router as sessions_router
from app.modules.stream.router import router as stream_router
from app.modules.users.router import router as users_router
from app.modules.voice.router import router as voice_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(dev_mix_router, prefix="/api/dev", tags=["dev-mix"])
api_router.include_router(auth_router, prefix="/api/auth", tags=["auth"])
api_router.include_router(stream_router, prefix="/api/stream", tags=["stream"])
api_router.include_router(library_router, prefix="/api/library", tags=["library"])
api_router.include_router(music_router, prefix="/api/music", tags=["music"])
api_router.include_router(users_router, prefix="/api/users", tags=["users"])
api_router.include_router(playlists_router, prefix="/api/playlists", tags=["playlists"])
api_router.include_router(profiles_router, prefix="/api/profiles", tags=["profiles"])
api_router.include_router(
    recommendations_router,
    prefix="/api/recommendations",
    tags=["recommendations"],
)
api_router.include_router(sessions_router, prefix="/api/sessions", tags=["sessions"])
api_router.include_router(fangpi_router, prefix="/api/fangpi", tags=["fangpi"])
api_router.include_router(voice_router, prefix="/api/voice", tags=["voice"])

