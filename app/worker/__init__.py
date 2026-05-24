"""RQ async job queue — one worker, one job at a time for GPU/CPU fairness."""

from __future__ import annotations

import redis as redis_lib
from rq import Queue

from app.shared.config import get_settings

_settings = get_settings()
_redis: redis_lib.Redis | None = None
_analysis_queue: Queue | None = None
_stems_queue: Queue | None = None


def _get_redis() -> redis_lib.Redis:
    global _redis
    if _redis is None:
        _redis = redis_lib.Redis.from_url(_settings.redis_url)
    return _redis


def get_analysis_queue() -> Queue:
    """Queue for audio analysis jobs (BPM, key, energy, beats, cues). Concurrency=1."""
    global _analysis_queue
    if _analysis_queue is None:
        _analysis_queue = Queue("harbeat:analysis", connection=_get_redis())
    return _analysis_queue


def get_stems_queue() -> Queue:
    """Queue for stem separation jobs (demucs). Concurrency=1 (GPU-limited)."""
    global _stems_queue
    if _stems_queue is None:
        _stems_queue = Queue("harbeat:stems", connection=_get_redis())
    return _stems_queue


def enqueue_analysis(song_id: str) -> str:
    from app.worker.jobs import job_analyze

    return get_analysis_queue().enqueue(
        job_analyze, song_id,
        job_timeout=600,              # 10 min
        result_ttl=3600,
        failure_ttl=86400,
    ).id


def enqueue_stems(song_id: str) -> str:
    from app.worker.jobs import job_separate_stems

    return get_stems_queue().enqueue(
        job_separate_stems, song_id,
        job_timeout=2700,             # 45 min (demucs is slow)
        result_ttl=3600,
        failure_ttl=86400,
    ).id


def get_job_status(queue_name: str, job_id: str) -> dict | None:
    """Return {status, result, error} for a job, or None if not found."""
    from rq.job import Job

    try:
        job = Job.fetch(job_id, connection=_get_redis())
    except Exception:
        return None
    return {
        "id": job.id,
        "status": job.get_status(),
        "result": job.result,
        "error": str(job.exc_info) if job.exc_info else None,
        "enqueued_at": str(job.enqueued_at) if job.enqueued_at else None,
        "ended_at": str(job.ended_at) if job.ended_at else None,
    }
