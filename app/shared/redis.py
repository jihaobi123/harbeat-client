from __future__ import annotations

import redis

from app.shared.config import get_settings

_pool: redis.ConnectionPool | None = None


def get_redis() -> redis.Redis:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = redis.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    return redis.Redis(connection_pool=_pool)


# ── Token blacklist helpers ──────────────────────────────────────────

_BLACKLIST_PREFIX = "token:blacklist:"


def blacklist_token(jti: str, ttl_seconds: int) -> None:
    r = get_redis()
    r.setex(f"{_BLACKLIST_PREFIX}{jti}", ttl_seconds, "1")


def is_token_blacklisted(jti: str) -> bool:
    r = get_redis()
    return r.exists(f"{_BLACKLIST_PREFIX}{jti}") > 0
