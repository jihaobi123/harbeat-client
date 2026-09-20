"""RQ worker entrypoint.

Usage:
    # Terminal 1: analysis worker
    rq worker harbeat:analysis --url redis://localhost:6379/0

    # Terminal 2: stems worker (one at a time for GPU)
    rq worker harbeat:stems --url redis://localhost:6379/0

Or run both in one process (sequential, same concurrency=1 effect):
    rq worker harbeat:analysis harbeat:stems --url redis://localhost:6379/0
"""

if __name__ == "__main__":
    import sys
    print("Usage: rq worker harbeat:analysis harbeat:stems --url <REDIS_URL>")
    sys.exit(1)
