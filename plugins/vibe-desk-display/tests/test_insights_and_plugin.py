import json
import importlib.util
import os
import sys
import tempfile
import unittest


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

    def write_session(self):
        path = os.path.join(self.temp.name, "rollout.jsonl")
        events = [
            {
                "timestamp": "2026-07-20T02:00:00Z",
                "type": "session_meta",
                "payload": {"cwd": "/work/autonomous-desk"},
            },
            {
                "timestamp": "2026-07-20T02:00:01Z",
                "type": "turn_context",
                "payload": {"model": "gpt-5.6-sol"},
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


if __name__ == "__main__":
    unittest.main()
