#!/usr/bin/env python3
"""OTP pairing for the Thinking Desk display.

Mirrors the Codex plugin's `desk_display.py pair-start` / `pair-complete` so
pairing is scripted rather than improvised from SKILL.md — an agent building
the HTTP request by hand tends to miss the required X-Device-ID header and
gets an opaque 403.

The config this writes (~/.config/autonomous-lcd.json) is shared with the
Codex plugin: pairing once is enough for both agents.

    python3 pair.py status          # exit 0 if a display is already paired
    python3 pair.py start           # scan, show a code on each display
    python3 pair.py complete 1234   # match the code, save, confirm
"""

import argparse
import json
import os
import secrets
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discover  # noqa: E402

CONFIG_PATH = os.path.expanduser("~/.config/autonomous-lcd.json")
PAIRING_PATH = os.path.expanduser("~/.config/autonomous-lcd-pairing.json")
PAIRING_TTL = 10 * 60
LCD_PORT = 3000


def load_json(path, default):
    try:
        with open(path) as handle:
            return json.load(handle)
    except Exception:
        return default


def atomic_write_json(path, value, mode=0o600):
    tmp = "{}.tmp.{}".format(path, os.getpid())
    with open(tmp, "w") as handle:
        json.dump(value, handle, indent=2)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def send_to_lcd(ip, device_id, payload):
    request = urllib.request.Request(
        "http://{}:{}/lcd".format(ip, LCD_PORT),
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Device-ID": device_id},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return 200 <= response.status < 300


def try_send(ip, device_id, payload):
    try:
        return send_to_lcd(ip, device_id, payload)
    except Exception:
        return False


def pairing_payload(code):
    return {
        "play_sound": 20,
        "items": [
            {"type": "text", "text": "Pairing", "x": 0, "y": 0, "width": 220,
             "align": "center", "size": 3, "color": "#7eb8da"},
            {"type": "text", "text": code, "x": 0, "y": 35, "width": 220,
             "align": "center", "size": 4, "color": "#e8dcc8"},
            {"type": "text", "text": "Enter this code", "x": 0, "y": 85,
             "width": 220, "align": "center", "size": 2, "color": "#9a9488"},
        ],
    }


def cmd_status(_args):
    cfg = load_json(CONFIG_PATH, {})
    return 0 if cfg.get("devices") else 1


def cmd_start(_args):
    found = discover.cache_check() or discover.parallel_scan()
    if not found:
        print("No displays found. Make sure the display is powered on and "
              "connected to the same Wi-Fi.")
        return 1

    codes = set()
    pending = []
    for item in found:
        code = None
        while code is None or code in codes:
            code = str(secrets.randbelow(9000) + 1000)
        codes.add(code)
        if try_send(item.get("ip"), item.get("device_id"), pairing_payload(code)):
            pending.append({"code": code, "device_id": item.get("device_id"),
                            "ip": item.get("ip")})

    if not pending:
        print("Displays were found but could not be reached. Check the Wi-Fi "
              "connection and try again.")
        return 1

    atomic_write_json(PAIRING_PATH, {"created_at": time.time(), "devices": pending})
    print("Found {} display(s). What 4-digit code do you see on the "
          "display?".format(len(pending)))
    return 0


def cmd_complete(args):
    pending = load_json(PAIRING_PATH, {})
    if not isinstance(pending, dict):
        pending = {}
    if time.time() - pending.get("created_at", 0) > PAIRING_TTL:
        print("That pairing session expired. Start pairing again.")
        return 1

    wanted = str(args.code).strip()
    match = next((item for item in pending.get("devices", [])
                  if str(item.get("code")) == wanted), None)
    if not match:
        print("That code did not match. Check the display and try again.")
        return 1

    cfg = load_json(CONFIG_PATH, {})
    entry = {
        "device_id": match["device_id"],
        "label": args.label,
        "last_known_ip": match["ip"],
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
    }
    devices = cfg.setdefault("devices", [])
    existing = next((d for d in devices if d.get("device_id") == entry["device_id"]), None)
    if existing is None:
        devices.append(entry)
    else:
        existing.update(entry)
    if not cfg.get("default_device_id"):
        cfg["default_device_id"] = entry["device_id"]
    atomic_write_json(CONFIG_PATH, cfg)

    try:
        os.unlink(PAIRING_PATH)
    except OSError:
        pass

    try_send(entry["last_known_ip"], entry["device_id"],
             {"text": "Paired with Claude", "color": "green", "play_sound": 20})
    print("Paired successfully. Your display should show a confirmation.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Pair a Thinking Desk display.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Exit 0 if a display is already paired"
                   ).set_defaults(func=cmd_status)
    sub.add_parser("start", help="Discover displays and show OTP codes"
                   ).set_defaults(func=cmd_start)
    complete = sub.add_parser("complete", help="Complete OTP pairing")
    complete.add_argument("code")
    complete.add_argument("--label", default="My Display")
    complete.set_defaults(func=cmd_complete)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
