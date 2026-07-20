import argparse
import json
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import desk_display
import device


class DeviceAndCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_values = (
            device.CONFIG_DIR,
            device.CONFIG_PATH,
            device.PAIRING_PATH,
            desk_display.device.CONFIG_DIR,
            desk_display.device.CONFIG_PATH,
            desk_display.device.PAIRING_PATH,
        )
        config_path = os.path.join(self.temp.name, "autonomous-lcd.json")
        pairing_path = os.path.join(self.temp.name, "pairing.json")
        device.CONFIG_DIR = self.temp.name
        device.CONFIG_PATH = config_path
        device.PAIRING_PATH = pairing_path
        desk_display.device.CONFIG_DIR = self.temp.name
        desk_display.device.CONFIG_PATH = config_path
        desk_display.device.PAIRING_PATH = pairing_path

    def tearDown(self):
        (
            device.CONFIG_DIR,
            device.CONFIG_PATH,
            device.PAIRING_PATH,
            desk_display.device.CONFIG_DIR,
            desk_display.device.CONFIG_PATH,
            desk_display.device.PAIRING_PATH,
        ) = self.old_values
        self.temp.cleanup()

    def test_atomic_config_is_private_and_has_defaults(self):
        device.save_config({"devices": []})
        mode = stat.S_IMODE(os.stat(device.CONFIG_PATH).st_mode)
        self.assertEqual(mode, 0o600)
        self.assertEqual(device.load_config()["usage_threshold"], 80)

    def test_markdown_is_flattened_and_limited(self):
        text = device.strip_markdown("# [Build](https://example.com) `passed` " + "x" * 600)
        self.assertFalse(any(mark in text for mark in ("#", "`", "https://")))
        self.assertLessEqual(len(text), 500)
        self.assertTrue(text.endswith("..."))

    @mock.patch("desk_display.device.try_send", return_value=True)
    def test_pair_complete_updates_existing_device(self, _send):
        device.atomic_write_json(
            device.PAIRING_PATH,
            {
                "created_at": desk_display.time.time(),
                "devices": [{"code": "1234", "device_id": "lcd-a1b2c3", "ip": "10.0.0.8"}],
            },
        )
        device.save_config(
            {
                "devices": [
                    {
                        "device_id": "lcd-a1b2c3",
                        "label": "Old",
                        "last_known_ip": "10.0.0.2",
                    }
                ],
                "default_device_id": "lcd-a1b2c3",
            }
        )
        args = argparse.Namespace(code="1234", label="Studio")
        self.assertEqual(desk_display.pair_complete(args), 0)
        cfg = device.load_config()
        self.assertEqual(len(cfg["devices"]), 1)
        self.assertEqual(cfg["devices"][0]["label"], "Studio")
        self.assertEqual(cfg["devices"][0]["last_known_ip"], "10.0.0.8")

    def test_boolean_configuration(self):
        args = argparse.Namespace(key="sounds_enabled", value="off")
        self.assertEqual(desk_display.configure(args), 0)
        self.assertFalse(device.load_config()["sounds_enabled"])

    def test_layout_validation_clamps_progress_and_text(self):
        payload = desk_display._validate_layout(
            {
                "items": [
                    {"type": "text", "text": "x" * 120},
                    {"type": "progress", "value": 130},
                ]
            }
        )
        self.assertEqual(len(payload["items"][0]["text"]), 95)
        self.assertEqual(payload["items"][1]["value"], 100)
        self.assertEqual(payload["play_sound"], 20)


if __name__ == "__main__":
    unittest.main()
