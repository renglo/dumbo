"""Tool history keeps one result per call id."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dumbo.lib.class_prototypes import SessionEvent  # noqa: E402
from dumbo.lib.timeline import pair_timeline  # noqa: E402


def _event(kind: str, payload: dict, event_id: str) -> SessionEvent:
    return SessionEvent(
        event_id=event_id,
        session_id="s",
        event_type=kind,
        timestamp=datetime.now(timezone.utc),
        payload=payload,
    )


class TimelineTests(unittest.TestCase):
    def test_the_final_result_replaces_the_running_receipt(self) -> None:
        events = [
            _event("user_message", {"text": "totals for 2026"}, "user"),
            _event("tool_call", {"tool": "revenue", "call_id": "call-1", "arguments": {"year": 2026}}, "call"),
            _event(
                "tool_result",
                {"tool": "revenue", "call_id": "call-1", "success": True, "result": {"status": "running"}},
                "running",
            ),
            _event("assistant_message", {"text": "Checking that now."}, "waiting"),
            _event(
                "tool_result",
                {"tool": "revenue", "call_id": "call-1", "success": True, "result": {"total": 10}},
                "done",
            ),
        ]
        messages = pair_timeline(events)
        tool_messages = [item for item in messages if item.get("role") == "tool"]
        self.assertEqual(len(tool_messages), 1)
        self.assertEqual(tool_messages[0]["tool_call_id"], "call-1")
        self.assertIn("10", tool_messages[0]["content"])
        self.assertNotIn("running", tool_messages[0]["content"])
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["content"], "Checking that now.")
        self.assertEqual(messages[-1]["role"], "tool")


if __name__ == "__main__":
    unittest.main()
