import argparse
import errno
import io
import json
import os
import stat
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock


SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

import desk_display
import device
import discover


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
            discover.CONFIG_PATH,
        )
        config_path = os.path.join(self.temp.name, "autonomous-lcd.json")
        pairing_path = os.path.join(self.temp.name, "pairing.json")
        device.CONFIG_DIR = self.temp.name
        device.CONFIG_PATH = config_path
        device.PAIRING_PATH = pairing_path
        desk_display.device.CONFIG_DIR = self.temp.name
        desk_display.device.CONFIG_PATH = config_path
        desk_display.device.PAIRING_PATH = pairing_path
        discover.CONFIG_PATH = config_path

    def tearDown(self):
        (
            device.CONFIG_DIR,
            device.CONFIG_PATH,
            device.PAIRING_PATH,
            desk_display.device.CONFIG_DIR,
            desk_display.device.CONFIG_PATH,
            desk_display.device.PAIRING_PATH,
            discover.CONFIG_PATH,
        ) = self.old_values
        self.temp.cleanup()

    def test_atomic_config_is_private_and_has_defaults(self):
        device.save_config({"devices": []})
        mode = stat.S_IMODE(os.stat(device.CONFIG_PATH).st_mode)
        self.assertEqual(mode, 0o600)
        loaded = device.load_config()
        self.assertEqual(loaded["usage_threshold"], 80)
        self.assertEqual(loaded["done_cooldown_seconds"], 60)

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

    def test_done_cooldown_seconds_configuration(self):
        args = argparse.Namespace(key="done_cooldown_seconds", value="15")
        self.assertEqual(desk_display.configure(args), 0)
        self.assertEqual(device.load_config()["done_cooldown_seconds"], 15)
        bad = argparse.Namespace(key="done_cooldown_seconds", value="-1")
        self.assertEqual(desk_display.configure(bad), 1)
        self.assertEqual(device.load_config()["done_cooldown_seconds"], 15)

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

    def _two_device_cfg(self, ip_a="10.0.0.55", ip_b="10.0.0.6"):
        cfg = {
            "devices": [
                {"device_id": "lcd-a", "label": "A", "last_known_ip": ip_a},
                {"device_id": "lcd-b", "label": "B", "last_known_ip": ip_b},
            ],
            "default_device_id": "lcd-a",
        }
        device.save_config(cfg)
        return device.load_config()

    def test_send_with_reconnect_does_not_clobber_other_device_ips(self):
        cfg = self._two_device_cfg()
        device_a = cfg["devices"][0]

        def fake_reconnect(device_id):
            on_disk = device.load_config()
            for dev in on_disk["devices"]:
                if dev["device_id"] == "lcd-a":
                    dev["last_known_ip"] = "10.0.0.55"
                elif dev["device_id"] == "lcd-b":
                    dev["last_known_ip"] = "10.0.0.66"
            device.save_config(on_disk)
            self.assertEqual(device_id, "lcd-a")
            return "10.0.0.55"

        with mock.patch.object(device, "try_send", side_effect=[False, True]), mock.patch.object(
            discover, "reconnect", side_effect=fake_reconnect
        ):
            self.assertEqual(
                device.send_with_reconnect(cfg, device_a, {"text": "hi"}),
                "10.0.0.55",
            )

        saved = {dev["device_id"]: dev["last_known_ip"] for dev in device.load_config()["devices"]}
        self.assertEqual(saved["lcd-a"], "10.0.0.55")
        self.assertEqual(saved["lcd-b"], "10.0.0.66")
        self.assertEqual(cfg["devices"][1]["last_known_ip"], "10.0.0.66")

    def test_update_cached_ip_writes_atomically(self):
        self._two_device_cfg()
        with mock.patch.object(device, "atomic_write_json", wraps=device.atomic_write_json) as writer:
            discover._update_cached_ip("lcd-b", "10.0.0.66")
        writer.assert_called_once()
        self.assertEqual(writer.call_args[0][0], device.CONFIG_PATH)
        saved = {dev["device_id"]: dev["last_known_ip"] for dev in device.load_config()["devices"]}
        self.assertEqual(saved["lcd-a"], "10.0.0.55")
        self.assertEqual(saved["lcd-b"], "10.0.0.66")
        mode = stat.S_IMODE(os.stat(device.CONFIG_PATH).st_mode)
        self.assertEqual(mode, 0o600)

    def test_sandbox_network_error_is_distinguished(self):
        wrapped = urllib.error.URLError(OSError(errno.EPERM, "Operation not permitted"))
        self.assertTrue(device.is_sandbox_network_error(wrapped))
        self.assertTrue(
            device.is_sandbox_network_error(OSError(errno.EACCES, "Permission denied"))
        )
        self.assertFalse(device.is_sandbox_network_error(TimeoutError("timed out")))
        self.assertFalse(
            device.is_sandbox_network_error(ConnectionRefusedError("refused"))
        )

    def test_try_send_marks_sandbox_block(self):
        blocked = urllib.error.URLError(OSError(errno.EPERM, "Operation not permitted"))
        with mock.patch.object(device, "send_to_lcd", side_effect=blocked):
            self.assertFalse(device.try_send("10.0.0.55", "lcd-a", {"text": "hi"}))
        self.assertTrue(device.last_send_blocked_by_sandbox())
        with mock.patch.object(device, "send_to_lcd", side_effect=TimeoutError("timed out")):
            self.assertFalse(device.try_send("10.0.0.55", "lcd-a", {"text": "hi"}))
        self.assertFalse(device.last_send_blocked_by_sandbox())

    def test_notify_sandbox_error_is_not_wifi(self):
        device.save_config(
            {
                "devices": [
                    {"device_id": "lcd-a", "label": "Desk", "last_known_ip": "10.0.0.55"}
                ]
            }
        )
        args = argparse.Namespace(
            device=None,
            message="hi",
            size=2,
            color="green",
            sound=20,
            dry_run=False,
        )
        with mock.patch.object(
            desk_display.device, "send_with_reconnect", return_value=None
        ), mock.patch.object(
            desk_display.device, "last_send_blocked_by_sandbox", return_value=True
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(desk_display.notify(args), 1)
        text = out.getvalue()
        self.assertIn("sandbox", text.lower())
        self.assertNotIn(desk_display.WIFI_UNREACHABLE, text)

    def test_notify_wifi_error_when_not_sandbox(self):
        device.save_config(
            {
                "devices": [
                    {"device_id": "lcd-a", "label": "Desk", "last_known_ip": "10.0.0.55"}
                ]
            }
        )
        args = argparse.Namespace(
            device=None,
            message="hi",
            size=2,
            color="green",
            sound=20,
            dry_run=False,
        )
        with mock.patch.object(
            desk_display.device, "send_with_reconnect", return_value=None
        ), mock.patch.object(
            desk_display.device, "last_send_blocked_by_sandbox", return_value=False
        ), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(desk_display.notify(args), 1)
        self.assertIn(desk_display.WIFI_UNREACHABLE, out.getvalue())


if __name__ == "__main__":
    unittest.main()
