#!/usr/bin/env python3
"""Hook: ping the LCD when Claude needs you to act.

Fires on Claude Code's `Notification` event, but only for the cases that
actually need a decision — a tool-approval prompt or an MCP form. The plain
"idle, waiting for your next prompt" notice is ignored so the display doesn't
flash a misleading "CLAUDE NEEDS YOU" when nothing is being asked.

Uses a distinct buzzer (triple_ping, #1) so it never sounds like the Task Done
cue (claude_style, #20). Rate-limited to once per 8s.
"""

import json
import os
import sys
import time
import urllib.request

import discover  # same scripts/ dir — reconnect + warn_user helpers

CONFIG_PATH = os.path.expanduser("~/.config/autonomous-lcd.json")
COOLDOWN_PATH = os.path.expanduser("~/.config/autonomous-lcd-notify.last")
COOLDOWN_SECONDS = 8
LCD_PORT = 3000
NOTIFY_SOUND = 1  # triple_ping — deliberately different from Task Done (#20)

ACCENT = "#d4845a"  # orange — "CLAUDE"
BLUE = "#7eb8da"    # sky blue — "NEEDS YOU"
MUTE = "#9a9488"    # muted — hint line

# Notification types that need no action from the user — never light up the
# display for these (idle waiting, auth success, MCP elicitation acks).
SKIP_NOTIFICATION_TYPES = {
    "idle_prompt", "auth_success",
    "elicitation_complete", "elicitation_response",
}


def is_actionable(event):
    """True if this Notification needs the user to do something (approve a tool,
    fill an MCP form). Uses the structured `notification_type` when present and
    falls back to the message text on older Claude Code builds."""
    ntype = (event.get("notification_type") or "").strip()
    if ntype:
        return ntype not in SKIP_NOTIFICATION_TYPES
    low = (event.get("message") or "").lower()
    return not ("waiting for your" in low or "idle" in low)


def should_run():
    try:
        last = float(open(COOLDOWN_PATH).read().strip())
        return (time.time() - last) >= COOLDOWN_SECONDS
    except Exception:
        return True


def mark_ran():
    try:
        with open(COOLDOWN_PATH, "w") as f:
            f.write(str(time.time()))
    except Exception:
        pass


def send_to_lcd(ip, device_id, payload):
    req = urllib.request.Request(
        f"http://{ip}:{LCD_PORT}/lcd",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Device-ID": device_id},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=3)


def try_send(ip, device_id, payload):
    """Send, returning True/False instead of raising — for the reconnect flow."""
    if not ip:
        return False
    try:
        send_to_lcd(ip, device_id, payload)
        return True
    except Exception:
        return False


def build_payload(message, sound=NOTIFY_SOUND):
    """One consistent card for every Notification event: a big two-line
    headline (CLAUDE in orange, NEEDS YOU in blue) over a muted hint. No
    footer — the headline gets the whole screen."""
    return {
        "play_sound": sound,
        "items": [
            {"type": "text", "text": "CLAUDE", "x": 0, "y": 8, "width": 220, "align": "center", "size": 3, "color": ACCENT},
            {"type": "text", "text": "NEEDS YOU", "x": 0, "y": 36, "width": 220, "align": "center", "size": 3, "color": BLUE},
            {"type": "text", "text": "Check your terminal", "x": 0, "y": 72, "width": 220, "align": "center", "size": 1, "color": MUTE},
        ],
    }


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        event = {}

    # Skip idle/background notifications — only ping when action is needed.
    if not is_actionable(event):
        sys.exit(0)

    if not should_run():
        sys.exit(0)

    if not os.path.exists(CONFIG_PATH):
        sys.exit(0)

    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except Exception:
        sys.exit(0)

    # User toggles (default on, preserving prior behaviour)
    if not cfg.get("notify_enabled", True):
        sys.exit(0)
    sound = NOTIFY_SOUND if cfg.get("sounds_enabled", True) else 0

    devices = cfg.get("devices", [])
    if not devices:
        sys.exit(0)

    default_id = cfg.get("default_device_id", devices[0].get("device_id"))
    dev = next((d for d in devices if d["device_id"] == default_id), devices[0])
    device_id = dev["device_id"]

    payload = build_payload(event.get("message", "Claude needs you"), sound)

    # Try the cached IP; if it's stale (DHCP moved the device), rescan the LAN
    # and retry. If it's still unreachable, warn the user in Claude.
    if try_send(dev.get("last_known_ip"), device_id, payload):
        mark_ran()
        return

    new_ip = discover.reconnect(device_id)
    if new_ip and try_send(new_ip, device_id, payload):
        mark_ran()
        return

    if cfg.get("device_warning_enabled", True):
        label = dev.get("label", "your desk display")
        discover.warn_user(
            f"⚠️ Couldn't reach {label} on your network — it may be offline or "
            f"on another Wi-Fi. Re-pair with \"pair my display\" if it moved."
        )


if __name__ == "__main__":
    main()
