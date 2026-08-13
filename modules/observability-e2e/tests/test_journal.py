from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from harbeat_observability.journal import endpoint_counts, parse_http_events


class JournalTests(unittest.TestCase):
    def test_parses_and_counts_fastapi_access_lines(self) -> None:
        lines = [
            '2026-08-13T13:34:23+0800 host app[1]: INFO: 1.2.3.4 - "POST /api/dj/transitions/fast-cut HTTP/1.1" 200 OK',
            '2026-08-13T13:34:24+0800 host app[1]: INFO: 1.2.3.4 - "GET /state?full=true HTTP/1.1" 200 OK',
            'not an access line',
        ]

        events = parse_http_events(lines, source="jetson")
        counts = endpoint_counts(events)

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["path"], "/api/dj/transitions/fast-cut")
        self.assertEqual(events[1]["path"], "/state")
        self.assertEqual(sum(item["count"] for item in counts), 2)


if __name__ == "__main__":
    unittest.main()
