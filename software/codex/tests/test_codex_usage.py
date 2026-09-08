import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone


SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import codex_usage


class CodexUsageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_sessions = codex_usage.SESSIONS_DIR
        codex_usage.SESSIONS_DIR = self.temp.name

    def tearDown(self):
        codex_usage.SESSIONS_DIR = self.old_sessions
        self.temp.cleanup()

    def write_session(self, events, name="rollout.jsonl"):
        path = os.path.join(self.temp.name, name)
        with open(path, "w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event) + "\n")
        return path

    def test_reads_latest_token_event_and_normalizes_windows(self):
        path = self.write_session(
            [
                {"type": "event_msg", "payload": {"type": "agent_message"}},
                {
                    "timestamp": "2026-07-20T00:00:00Z",
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {"input_tokens": 1000},
                            "last_token_usage": {"total_tokens": 25},
                            "model_context_window": 100,
                        },
                        "rate_limits": {
                            "primary": {
                                "used_percent": 63.6,
                                "window_minutes": 300,
                                "resets_at": 1784516400,
                            },
                            "secondary": {
                                "used_percent": 22,
                                "window_minutes": 10080,
                                "resets_at": 1785121200,
                            },
                            "plan_type": "plus",
                        },
                    },
                },
            ]
        )
        result = codex_usage.read_usage(path)
        self.assertEqual([item["label"] for item in result["limits"]], ["5 hour", "7 day"])
        self.assertEqual(result["limits"][0]["used_percent"], 64)
        self.assertEqual(result["context_percent"], 25)
        self.assertEqual(result["plan_type"], "plus")

    def test_newest_token_event_wins(self):
        path = self.write_session(
            [
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "rate_limits": {
                            "primary": {"used_percent": 10, "window_minutes": 300}
                        },
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "rate_limits": {
                            "primary": {"used_percent": 80, "window_minutes": 300}
                        },
                    },
                },
            ]
        )
        self.assertEqual(codex_usage.read_usage(path)["limits"][0]["used_percent"], 80)

    def test_time_left_handles_epoch_and_expired(self):
        now = datetime(2026, 7, 20, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(codex_usage.time_left(now.timestamp() + 9000, now), "2h 30m")
        self.assertEqual(codex_usage.time_left(now.timestamp() - 1, now), "now")

    def test_missing_usage_returns_none(self):
        path = self.write_session([{"type": "event_msg", "payload": {"type": "task_complete"}}])
        self.assertIsNone(codex_usage.read_usage(path))

    def test_resets_at_epoch_is_used(self):
        now = datetime(2026, 7, 20, 0, 0, tzinfo=timezone.utc)
        path = self.write_session(
            [
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "rate_limits": {
                            "primary": {
                                "used_percent": 80,
                                "window_minutes": 300,
                                "resets_at": now.timestamp() + 9000,
                            }
                        },
                    },
                }
            ],
            name="resets-at.jsonl",
        )
        result = codex_usage.read_usage(path, now=now)
        self.assertEqual(result["limits"][0]["resets_at"], now.timestamp() + 9000)
        card = codex_usage.build_limit_card(result["limits"][0], now=now)
        self.assertIn(
            "Resets in 2h 30m",
            [item.get("text") for item in card["items"]],
        )

    def test_resets_in_seconds_is_converted(self):
        now = datetime(2026, 7, 20, 0, 0, tzinfo=timezone.utc)
        path = self.write_session(
            [
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "token_count",
                        "info": None,
                        "rate_limits": {
                            "primary": {
                                "used_percent": 0.0,
                                "window_minutes": 299,
                                "resets_in_seconds": 9000,
                            },
                            "secondary": {
                                "used_percent": 6.0,
                                "window_minutes": 10079,
                                "resets_in_seconds": 90000,
                            },
                        },
                    },
                }
            ],
            name="resets-in-seconds.jsonl",
        )
        result = codex_usage.read_usage(path, now=now)
        self.assertEqual(result["limits"][0]["resets_at"], now.timestamp() + 9000)
        self.assertEqual(result["limits"][1]["resets_at"], now.timestamp() + 90000)
        card = codex_usage.build_limit_card(result["limits"][0], now=now)
        texts = [item.get("text") for item in card["items"]]
        self.assertIn("Resets in 2h 30m", texts)
        self.assertNotIn("Resets in N/A", texts)

    def test_resets_at_wins_over_resets_in_seconds(self):
        now = datetime(2026, 7, 20, 0, 0, tzinfo=timezone.utc)
        raw = {
            "used_percent": 10,
            "window_minutes": 300,
            "resets_at": now.timestamp() + 3600,
            "resets_in_seconds": 99,
        }
        self.assertEqual(
            codex_usage._window_resets_at(raw, now=now),
            now.timestamp() + 3600,
        )


if __name__ == "__main__":
    unittest.main()
