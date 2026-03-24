from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.playlist import router as playlist_router
from app.api.recommend import router as recommend_router
from app.config import get_settings
from app.redis_client import redis_client

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    redis_client.ping()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(recommend_router)
app.include_router(playlist_router)


@app.get("/")
def root():
    return {"message": "Dance AI Recommender API is running"}


@app.get("/health")
def health():
    return {
        "status": "ok",
        "postgres": "connected",
        "redis": "connected",
    }
