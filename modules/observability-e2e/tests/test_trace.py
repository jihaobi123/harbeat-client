from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from harbeat_observability.trace import OperationTrace, TraceEvent


class TraceTests(unittest.TestCase):
    def test_orders_events_and_redacts_secrets(self) -> None:
        trace = OperationTrace("operation-1", "fast_cut")
        trace.append(
            TraceEvent(
                source="rk-edge",
                stage="scheduled",
                timestamp="2026-08-13T06:00:02+00:00",
                details={"authorization": "Bearer secret", "pair_id": "pair-1"},
            )
        )
        trace.append(
            TraceEvent(
                source="mobile",
                stage="clicked",
                timestamp="2026-08-13T06:00:00+00:00",
                details={"message": "Bearer abc.def"},
            )
        )

        report = trace.to_report(passed=True)

        self.assertEqual(report["events"][0]["stage"], "clicked")
        self.assertEqual(report["events"][0]["details"]["message"], "Bearer [REDACTED]")
        self.assertEqual(report["events"][1]["details"]["authorization"], "[REDACTED]")
        self.assertEqual(trace.elapsed_seconds("clicked", "scheduled"), 2.0)


if __name__ == "__main__":
    unittest.main()

