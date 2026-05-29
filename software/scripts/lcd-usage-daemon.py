#!/usr/bin/env python3
"""Fetch Claude Code usage and display on LCD. Runs via launchd every 5 min."""

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

CONFIG_PATH = os.path.expanduser("~/.config/autonomous-lcd.json")
LOG_PREFIX = "lcd-daemon"
LCD_PORT = 3000
SEND_DELAY = 7


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_device(cfg):
    if not cfg.get("devices"):
        return None, None
    dev_id = cfg.get("default_device_id", cfg["devices"][0]["device_id"])
    for d in cfg["devices"]:
        if d["device_id"] == dev_id:
            return d["device_id"], d["last_known_ip"]
    d = cfg["devices"][0]
    return d["device_id"], d["last_known_ip"]


def _find_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _find_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _find_strings(v)


def get_token():
    cred_path = os.path.expanduser("~/.claude/.credentials.json")
    if os.path.exists(cred_path):
        with open(cred_path) as f:
            data = json.load(f)
        for v in _find_strings(data):
            if v.startswith("sk-ant-oat"):
                return v
    try:
        kc = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True,
        )
        if kc.returncode == 0:
            data = json.loads(kc.stdout.strip())
            for v in _find_strings(data):
                if v.startswith("sk-ant-oat"):
                    return v
    except Exception:
        pass
    return None


def fetch_usage(token):
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def time_left(iso_str):
    if not iso_str:
        return "N/A"
    diff = datetime.fromisoformat(iso_str) - datetime.now(timezone.utc)
    total_sec = int(diff.total_seconds())
    if total_sec <= 0:
        return "now"
    h = total_sec // 3600
    m = (total_sec % 3600) // 60
    if h > 24:
        return f"{h // 24}d {h % 24}h"
    return f"{h}h {m}m"


def progress_color(pct):
    if pct >= 80:
        return "#c0392b"
    if pct >= 60:
        return "#d4845a"
    return "#6b8f4e"


def build_section1(pct_5h, reset_5h, sound=0):
    return {
        "play_sound": sound,
        "items": [
            {"type": "text", "text": "Usage", "x": 0, "y": 5, "width": 220, "align": "center", "size": 4, "color": "#d4845a"},
            {"type": "text", "text": f"{pct_5h}%", "x": 18, "y": 38, "width": 100, "size": 4, "color": progress_color(pct_5h)},
            {"type": "text", "text": "Current", "x": 100, "y": 46, "width": 105, "align": "right", "size": 1, "color": "#7eb8da"},
            {"type": "progress", "x": 18, "y": 70, "width": 184, "height": 12, "radius": 6, "value": pct_5h, "color": progress_color(pct_5h), "bg_color": "#3a3a3a"},
            {"type": "text", "text": f"Resets in {reset_5h}", "x": 18, "y": 90, "width": 180, "size": 1, "color": "#e8dcc8"},
        ],
    }


def build_section2(pct_7d, reset_7d, sound=0):
    return {
        "play_sound": sound,
        "items": [
            {"type": "text", "text": f"{pct_7d}%", "x": 18, "y": 10, "width": 100, "size": 4, "color": "#e8dcc8"},
            {"type": "text", "text": "Weekly", "x": 100, "y": 18, "width": 105, "align": "right", "size": 1, "color": "#a09888"},
            {"type": "progress", "x": 18, "y": 45, "width": 184, "height": 12, "radius": 6, "value": pct_7d, "color": progress_color(pct_7d), "bg_color": "#3a3a3a"},
            {"type": "text", "text": f"Resets in {reset_7d}", "x": 18, "y": 63, "width": 180, "size": 1, "color": "#9a9488"},
            {"type": "text", "text": "* Baking...", "x": 0, "y": 87, "width": 220, "align": "center", "size": 2, "color": "#d4845a"},
        ],
    }


def send_to_lcd(ip, device_id, payload):
    req = urllib.request.Request(
        f"http://{ip}:{LCD_PORT}/lcd",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Device-ID": device_id},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status



def main():
    try:
        cfg = load_config()
    except FileNotFoundError:
        log("No config found. Pair a device first.")
        sys.exit(0)

    device_id, ip = get_device(cfg)
    if not device_id or not ip:
        log("No device configured.")
        sys.exit(0)

    token = get_token()
    if not token:
        log("No OAuth token found. Log in to Claude Code first.")
        sys.exit(1)

    try:
        usage = fetch_usage(token)
    except Exception as e:
        log(f"Failed to fetch usage: {e}")
        sys.exit(1)

    pct_5h = int(usage["five_hour"]["utilization"])
    pct_7d = int(usage["seven_day"]["utilization"])
    reset_5h = time_left(usage["five_hour"]["resets_at"])
    reset_7d = time_left(usage["seven_day"]["resets_at"])

    try:
        payload1 = build_section1(pct_5h, reset_5h, sound=20)
        status1 = send_to_lcd(ip, device_id, payload1)
        log(f"Section 1 → HTTP {status1} (5h:{pct_5h}%)")

        time.sleep(SEND_DELAY)

        payload2 = build_section2(pct_7d, reset_7d, sound=20)
        status2 = send_to_lcd(ip, device_id, payload2)
        log(f"Section 2 → HTTP {status2} (7d:{pct_7d}%)")
    except Exception as e:
        log(f"Send failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
