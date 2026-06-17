#!/usr/bin/env python3
"""Hook: ping the LCD when Claude is waiting on the user.

Fires on Claude Code's `Notification` event — i.e. when Claude needs approval
to run a tool (a yes/no prompt) or the input has been left idle. Uses a
distinct buzzer (triple_ping, #1) so it never sounds like the Task Done cue
(claude_style, #20). Handy when you've wandered off to your phone and forgot
to hit enter.

Rate-limited to once per 8s so a burst of prompts doesn't machine-gun the buzzer.
"""

import json
import os
import re
import sys
import time
import urllib.request

CONFIG_PATH = os.path.expanduser("~/.config/autonomous-lcd.json")
COOLDOWN_PATH = os.path.expanduser("~/.config/autonomous-lcd-notify.last")
COOLDOWN_SECONDS = 8
LCD_PORT = 3000
NOTIFY_SOUND = 1  # triple_ping — deliberately different from Task Done (#20)

ACCENT = "#d4845a"
CREAM = "#e8dcc8"
MUTE = "#9a9488"
CHAR_W = 6  # device font: ~6px per char at size 1, scaling with size


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


PERMISSION_RE = re.compile(r"permission to use (.+?)[.\s]*$", re.IGNORECASE)


def ellipsize(text, box_w, size):
    """Trim text (+ trailing ellipsis) so it fits box_w at the given size."""
    max_chars = max(box_w // (CHAR_W * size), 1)
    text = text.strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1] + "…"


def pretty_tool(name):
    """Shorten tool names for the tiny display.

    MCP tools arrive as 'mcp__<server>__<tool>' which is far too long — keep
    just the tool segment with underscores spaced out (e.g.
    'mcp__claude_ai_Google_Drive__authenticate' -> 'authenticate').
    """
    name = name.strip()
    if name.startswith("mcp__"):
        name = name.split("__")[-1] or name
    return name.replace("_", " ").strip()


def parse_message(message):
    """Return (title, subtitle) — a clean headline + one short line."""
    msg = (message or "").strip()
    low = msg.lower()
    m = PERMISSION_RE.search(msg)
    if m:
        # "Claude needs your permission to use Bash" -> ("Approve?", "Bash")
        return "Approve?", pretty_tool(m.group(1))
    if "permission" in low or "approve" in low or "allow" in low:
        return "Approve?", "needs your ok"
    if "waiting" in low or "idle" in low or "input" in low:
        return "Your turn", "waiting for you"
    return "Heads up", msg


def build_payload(message):
    title, subtitle = parse_message(message)
    items = [
        {"type": "text", "text": title, "x": 0, "y": 26, "width": 220,
         "align": "center", "size": 2, "color": ACCENT},
    ]
    if subtitle:
        # one clean centred line at the smallest size, trimmed before it overflows
        items.append({"type": "text", "text": ellipsize(subtitle, 216, 1),
                      "x": 0, "y": 52, "width": 220, "align": "center",
                      "size": 1, "color": CREAM})
    # keep the footer within the safe band (text below ~y=90 gets clipped)
    items.append({"type": "text", "text": "* claude code", "x": 0, "y": 84,
                  "width": 220, "align": "center", "size": 1, "color": MUTE})
    return {"play_sound": NOTIFY_SOUND, "items": items[:6]}


def main():
    try:
        event = json.load(sys.stdin)
    except Exception:
        event = {}

    if not should_run():
        sys.exit(0)

    if not os.path.exists(CONFIG_PATH):
        sys.exit(0)

    try:
        with open(CONFIG_PATH) as f:
            cfg = json.load(f)
    except Exception:
        sys.exit(0)

    devices = cfg.get("devices", [])
    if not devices:
        sys.exit(0)

    default_id = cfg.get("default_device_id", devices[0].get("device_id"))
    dev = next((d for d in devices if d["device_id"] == default_id), devices[0])

    payload = build_payload(event.get("message", "Claude needs you"))
    try:
        send_to_lcd(dev["last_known_ip"], dev["device_id"], payload)
        mark_ran()
    except Exception:
        pass


if __name__ == "__main__":
    main()
