import io
import json
import importlib.util
import os
import sys
import tempfile
import time
import unittest
from unittest import mock


PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS = os.path.join(PLUGIN_ROOT, "scripts")
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import insights


def load_script(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(SCRIPTS, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


on_permission_request = load_script("on_permission_request", "on-permission-request.py")
on_stop_done = load_script("on_stop_done", "on-stop-done.py")


class InsightsAndPluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_sessions = insights.SESSIONS_DIR
        insights.SESSIONS_DIR = self.temp.name

    def tearDown(self):
        insights.SESSIONS_DIR = self.old_sessions
        self.temp.cleanup()

    def write_session(self, name="rollout.jsonl", model="gpt-5.6-sol"):
        path = os.path.join(self.temp.name, name)
        events = [
            {
                "timestamp": "2026-07-20T02:00:00Z",
                "type": "session_meta",
                "payload": {"cwd": "/work/autonomous-desk"},
            },
            {
                "timestamp": "2026-07-20T02:00:01Z",
                "type": "turn_context",
                "payload": {"model": model},
            },
            {
                "timestamp": "2026-07-20T02:00:02Z",
                "type": "event_msg",
                "payload": {"type": "user_message", "message": "please run the tests"},
            },
            {
                "type": "response_item",
                "payload": {"type": "custom_tool_call", "name": "exec"},
            },
            {
                "type": "response_item",
                "payload": {"type": "function_call", "name": "apply_patch"},
            },
            {
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 1000,
                            "cached_input_tokens": 750,
                            "output_tokens": 200,
                        }
                    },
                },
            },
        ]
        with open(path, "w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event) + "\n")
        return path

    def test_codex_session_profile(self):
        self.write_session()
        profile = insights.analyze()
        self.assertEqual(profile["activity"]["sessions"], 1)
        self.assertEqual(profile["activity"]["prompts"], 1)
        self.assertEqual(profile["models"]["top"], "GPT 5.6-SOL")
        self.assertEqual(profile["tokens"]["cache_hit_pct"], 75.0)
        self.assertEqual(profile["velocity"]["tool_calls"], 2)
        self.assertEqual(profile["velocity"]["edits"], 1)

    def test_plugin_manifest_and_hooks(self):
        with open(os.path.join(PLUGIN_ROOT, ".codex-plugin", "plugin.json"), encoding="utf-8") as handle:
            manifest = json.load(handle)
        with open(os.path.join(PLUGIN_ROOT, "hooks", "hooks.json"), encoding="utf-8") as handle:
            hooks = json.load(handle)["hooks"]
        self.assertEqual(manifest["name"], os.path.basename(PLUGIN_ROOT))
        self.assertIn("Stop", hooks)
        self.assertIn("PermissionRequest", hooks)
        self.assertNotIn("Notification", hooks)

    def test_permission_tool_name_variants(self):
        self.assertEqual(on_permission_request.event_tool_name({"tool_name": "Bash"}), "Bash")
        self.assertEqual(
            on_permission_request.event_tool_name({"tool": {"name": "apply_patch"}}),
            "apply_patch",
        )

    def test_version_comparison_ignores_build_metadata(self):
        self.assertEqual(on_stop_done._parse_version("1.2.3+codex.local"), (1, 2, 3))

    def test_analyze_skips_sessions_older_than_90_days(self):
        recent = self.write_session(name="recent.jsonl", model="gpt-5.6-sol")
        old = self.write_session(name="old.jsonl", model="gpt-4.1")
        old_mtime = time.time() - (100 * 24 * 3600)
        os.utime(old, (old_mtime, old_mtime))
        os.utime(recent, None)
        profile = insights.analyze()
        self.assertEqual(profile["activity"]["sessions"], 1)
        self.assertEqual(profile["models"]["top_raw"], "gpt-5.6-sol")
        self.assertNotIn(old, list(insights.iter_sessions()))

    def test_analyze_caps_session_file_count(self):
        newer = self.write_session(name="newer.jsonl", model="gpt-5.6-sol")
        older = self.write_session(name="older.jsonl", model="gpt-4.1")
        now = time.time()
        os.utime(older, (now - 10, now - 10))
        os.utime(newer, (now, now))
        original = insights.SESSION_MAX_FILES
        insights.SESSION_MAX_FILES = 1
        try:
            chosen = list(insights.iter_sessions())
            profile = insights.analyze()
        finally:
            insights.SESSION_MAX_FILES = original
        self.assertEqual(chosen, [newer])
        self.assertEqual(profile["activity"]["sessions"], 1)
        self.assertEqual(profile["models"]["top_raw"], "gpt-5.6-sol")

    def test_event_transcript_path_accepts_both_field_names(self):
        claude_or_current = {"transcript_path": "/tmp/session.jsonl"}
        codex_rollout = {"rollout_path": "/tmp/rollout-2026-07-20.jsonl"}
        self.assertEqual(
            on_stop_done.event_transcript_path(claude_or_current),
            "/tmp/session.jsonl",
        )
        self.assertEqual(
            on_stop_done.event_transcript_path(codex_rollout),
            "/tmp/rollout-2026-07-20.jsonl",
        )
        self.assertIsNone(on_stop_done.event_transcript_path({}))

    def test_should_run_honors_done_cooldown_seconds(self):
        old_dir = on_stop_done.device.CONFIG_DIR
        old_path = on_stop_done.device.CONFIG_PATH
        old_cool = on_stop_done.COOLDOWN_PATH
        on_stop_done.device.CONFIG_DIR = self.temp.name
        on_stop_done.device.CONFIG_PATH = os.path.join(
            self.temp.name, "autonomous-lcd.json"
        )
        on_stop_done.COOLDOWN_PATH = os.path.join(self.temp.name, "done.last")
        try:
            now = 1_000_000.0
            on_stop_done.device.save_config({"done_cooldown_seconds": 60})
            on_stop_done.mark_ran(now)
            self.assertFalse(
                on_stop_done.should_run(
                    now=now + 30, cooldown=on_stop_done.cooldown_seconds()
                )
            )
            on_stop_done.device.save_config({"done_cooldown_seconds": 15})
            self.assertTrue(
                on_stop_done.should_run(
                    now=now + 30, cooldown=on_stop_done.cooldown_seconds()
                )
            )
            on_stop_done.device.save_config({"done_cooldown_seconds": 0})
            self.assertTrue(
                on_stop_done.should_run(now=now, cooldown=on_stop_done.cooldown_seconds())
            )
            on_stop_done.device.save_config({"done_cooldown_seconds": "nope"})
            self.assertEqual(on_stop_done.cooldown_seconds(), 60)
        finally:
            on_stop_done.device.CONFIG_DIR = old_dir
            on_stop_done.device.CONFIG_PATH = old_path
            on_stop_done.COOLDOWN_PATH = old_cool

    def test_stop_hook_reads_both_transcript_field_names(self):
        old_dir = on_stop_done.device.CONFIG_DIR
        old_path = on_stop_done.device.CONFIG_PATH
        on_stop_done.device.CONFIG_DIR = self.temp.name
        on_stop_done.device.CONFIG_PATH = os.path.join(self.temp.name, "autonomous-lcd.json")
        on_stop_done.device.save_config(
            {
                "devices": [{"device_id": "lcd-a", "last_known_ip": "10.0.0.55"}],
                "update_check_enabled": False,
                "show_insights": False,
            }
        )
        try:
            for key, path in (
                ("transcript_path", "/tmp/session.jsonl"),
                ("rollout_path", "/tmp/rollout.jsonl"),
            ):
                with mock.patch.object(on_stop_done, "should_run", return_value=True), mock.patch.object(
                    on_stop_done, "mark_ran"
                ), mock.patch.object(
                    on_stop_done.device, "send_with_reconnect", return_value="10.0.0.55"
                ), mock.patch.object(
                    on_stop_done.codex_usage, "read_usage", return_value=None
                ) as reader, mock.patch.object(
                    on_stop_done.sys, "stdin", io.StringIO(json.dumps({key: path}))
                ):
                    on_stop_done.main()
                reader.assert_called_once_with(path)
        finally:
            on_stop_done.device.CONFIG_DIR = old_dir
            on_stop_done.device.CONFIG_PATH = old_path


if __name__ == "__main__":
    unittest.main()
