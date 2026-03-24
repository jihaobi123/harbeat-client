import os

from redis.asyncio import Redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

redis_client: Redis | None = None


async def init_redis() -> Redis:
    global redis_client
    redis_client = Redis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    await redis_client.ping()
    return redis_client


def get_redis() -> Redis:
    if redis_client is None:
        raise RuntimeError("Redis client is not initialized. Call init_redis() first.")
    return redis_client


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        await redis_client.aclose()
        redis_client = None


async def check_redis_connection() -> bool:
    if redis_client is None:
        return False
    try:
        await redis_client.ping()
        return True
    except Exception:
        return False
