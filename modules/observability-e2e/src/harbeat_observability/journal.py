"""Normalize common FastAPI/uvicorn HTTP access events from device journals."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable


HTTP_ACCESS = re.compile(
    r'(?P<timestamp>\d{4}-\d{2}-\d{2}T\S+)?[^\"]*'
    r'\"(?P<method>GET|POST|PUT|PATCH|DELETE) (?P<path>[^ ?\"]+)'
    r'(?:\?[^ \"]*)? HTTP/\d(?:\.\d)?\" (?P<status>\d{3})'
)


def parse_http_events(lines: Iterable[str], *, source: str) -> list[dict]:
    events = []
    for line in lines:
        match = HTTP_ACCESS.search(line)
        if not match:
            continue
        events.append(
            {
                "source": source,
                "timestamp": match.group("timestamp"),
                "method": match.group("method"),
                "path": match.group("path"),
                "status": int(match.group("status")),
            }
        )
    return events


def endpoint_counts(events: Iterable[dict]) -> list[dict]:
    counts = Counter((event["method"], event["path"], event["status"]) for event in events)
    return [
        {"count": count, "method": method, "path": path, "status": status}
        for (method, path, status), count in sorted(
            counts.items(), key=lambda item: (-item[1], item[0])
        )
    ]

