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
        self.assertEqual(report["schema_version"], 2)
        self.assertEqual(report["result"]["metrics"]["click_to_scheduled_sec"], 2.0)

    def test_rejects_unknown_source_or_stage(self) -> None:
        with self.assertRaises(ValueError):
            TraceEvent(source="unknown",stage="clicked",timestamp="2026-08-13T06:00:00+00:00")
        with self.assertRaises(ValueError):
            TraceEvent(source="mobile",stage="unknown",timestamp="2026-08-13T06:00:00+00:00")

    def test_computes_standard_manual_transition_metrics(self) -> None:
        trace=OperationTrace("operation-2","fast_cut")
        for source,stage,second in (("mobile","clicked",0),("jetson","planned",3),("jetson","rendered",8),("rk-sync","sync_started",8),("rk-sync","cache_ready",10),("rk-edge","scheduled",11),("rk-audio","transition_started",14),("rk-audio","resumed",20)):
            trace.append(TraceEvent(source,stage,f"2026-08-13T06:00:{second:02d}+00:00"))
        metrics=trace.standard_metrics()
        self.assertEqual(metrics["click_to_scheduled_sec"],11.0)
        self.assertEqual(metrics["click_to_transition_sec"],14.0)
        self.assertEqual(metrics["sync_sec"],2.0)


if __name__ == "__main__":
    unittest.main()

