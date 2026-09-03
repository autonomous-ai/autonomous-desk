#!/usr/bin/env python3
"""Shared Thinking Desk display helpers.

The plugin talks only to the display on the local network. Configuration is
stored with mode 0600 and can be redirected in tests with
AUTONOMOUS_LCD_CONFIG_DIR.
"""

import json
import os
import re
import tempfile
import urllib.request
from datetime import datetime, timezone


CONFIG_DIR = os.path.expanduser(
    os.environ.get("AUTONOMOUS_LCD_CONFIG_DIR", "~/.config")
)
CONFIG_PATH = os.path.join(CONFIG_DIR, "autonomous-lcd.json")
PAIRING_PATH = os.path.join(CONFIG_DIR, "autonomous-lcd-pairing.json")
LCD_PORT = 3000

DEFAULTS = {
    "usage_threshold": 80,
    "sounds_enabled": True,
    "task_done_enabled": True,
    "notify_enabled": True,
    "update_check_enabled": True,
    "device_warning_enabled": True,
    "show_insights": True,
}


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return {} if default is None else default


def atomic_write_json(path, value, mode=0o600):
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".autonomous-lcd-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
        os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
        os.chmod(path, mode)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_config():
    cfg = load_json(CONFIG_PATH, {})
    if not isinstance(cfg, dict):
        cfg = {}
    for key, value in DEFAULTS.items():
        cfg.setdefault(key, value)
    cfg.setdefault("devices", [])
    return cfg


def save_config(cfg):
    atomic_write_json(CONFIG_PATH, cfg)


def get_device(cfg, requested=None):
    devices = cfg.get("devices") or []
    if not devices:
        return None
    selected = requested or cfg.get("default_device_id")
    if selected:
        selected_lower = str(selected).lower()
        for dev in devices:
            if str(dev.get("device_id", "")).lower() == selected_lower:
                return dev
            if str(dev.get("label", "")).lower() == selected_lower:
                return dev
    return devices[0]


def send_to_lcd(ip, device_id, payload, timeout=3):
    request = urllib.request.Request(
        "http://{}:{}/lcd".format(ip, LCD_PORT),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Device-ID": device_id},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        response.read()
        return response.status


def try_send(ip, device_id, payload, timeout=3):
    if not ip or not device_id:
        return False
    try:
        send_to_lcd(ip, device_id, payload, timeout=timeout)
        return True
    except Exception:
        return False


def mark_seen(cfg, device_id, ip=None):
    changed = False
    for dev in cfg.get("devices", []):
        if dev.get("device_id") != device_id:
            continue
        if ip and dev.get("last_known_ip") != ip:
            dev["last_known_ip"] = ip
            changed = True
        dev["last_seen_at"] = datetime.now(timezone.utc).isoformat()
        changed = True
        break
    if changed:
        try:
            save_config(cfg)
        except OSError:
            pass


def _adopt_disk_config(cfg):
    """Replace an in-memory config dict with the current on-disk snapshot."""
    if not isinstance(cfg, dict):
        return
    fresh = load_config()
    cfg.clear()
    cfg.update(fresh)


def send_with_reconnect(cfg, dev, payload):
    """Send to the cached IP, rediscovering the device once if needed."""
    device_id = dev.get("device_id")
    ip = dev.get("last_known_ip")
    if try_send(ip, device_id, payload):
        mark_seen(cfg, device_id, ip)
        return ip

    try:
        import discover

        fresh_ip = discover.reconnect(device_id)
    except Exception:
        fresh_ip = None
    if fresh_ip and try_send(fresh_ip, device_id, payload):
        # reconnect() already persisted every discovered device. Reload so
        # mark_seen() cannot write this stale in-memory snapshot back and
        # revert the other devices' IPs.
        _adopt_disk_config(cfg)
        mark_seen(cfg, device_id, fresh_ip)
        return fresh_ip
    return None


def strip_markdown(text, limit=500):
    text = re.sub(r"```.*?```", "", str(text), flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^[#>*+-]+\s*", "", text, flags=re.MULTILINE)
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[: max(0, limit - 3)] + "..."
    return text


def build_text_payload(text, size=2, color="green", sound=20):
    return {
        "text": strip_markdown(text),
        "size": max(1, min(4, int(size))),
        "color": color,
        "play_sound": sound,
    }


def build_task_done_payload(sound=20):
    return {
        "play_sound": sound,
        "items": [
            {
                "type": "text",
                "text": "Codex Done",
                "x": 0,
                "y": 34,
                "width": 220,
                "align": "center",
                "size": 3,
                "color": "#6b8f4e",
            }
        ],
    }


def build_needs_you_payload(tool_name=None, sound=1):
    hint = "Check Codex"
    if tool_name:
        short_name = str(tool_name).split("__")[-1].replace("_", " ")
        hint = short_name[:28]
    return {
        "play_sound": sound,
        "items": [
            {
                "type": "text",
                "text": "CODEX",
                "x": 0,
                "y": 8,
                "width": 220,
                "align": "center",
                "size": 3,
                "color": "#d4845a",
            },
            {
                "type": "text",
                "text": "NEEDS YOU",
                "x": 0,
                "y": 36,
                "width": 220,
                "align": "center",
                "size": 3,
                "color": "#7eb8da",
            },
            {
                "type": "text",
                "text": hint,
                "x": 0,
                "y": 72,
                "width": 220,
                "align": "center",
                "size": 1,
                "color": "#9a9488",
            },
        ],
    }


def warn_hook_user(message):
    """Return a valid, non-blocking Codex hook message on stdout."""
    print(json.dumps({"systemMessage": message}))
