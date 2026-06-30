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


def ellipsize(text, box_w, size):
    """Trim text (+ trailing ellipsis) so it fits box_w at the given size."""
    max_chars = max(box_w // (CHAR_W * size), 1)
    text = text.strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1] + "…"


def wrap_lines(text, box_w, size):
    """Greedily wrap text into lines that each fit box_w at the given size."""
    max_chars = max(box_w // (CHAR_W * size), 1)
    lines, cur = [], ""
    for word in text.split():
        cand = (cur + " " + word).strip()
        if len(cand) <= max_chars:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [text]


def parse_message(message):
    """Return (title, subtitle) — a clean headline + one short line.

    Whatever the Notification event is (tool approval or idle input), it always
    means the same thing to the user: go look at Claude. So we show one clear,
    consistent card instead of guessing a per-case headline.
    """
    return "CLAUDE NEEDS YOU", "Check your terminal"


def build_payload(message, sound=NOTIFY_SOUND):
    title, subtitle = parse_message(message)
    # Big, bold title wrapped to size 3 (drops the old "* claude code" footer
    # so the headline gets the whole screen).
    title_lines = wrap_lines(title, 216, 3)
    y = 8 if len(title_lines) > 1 else 20
    items = []
    for line in title_lines:
        items.append({"type": "text", "text": line, "x": 0, "y": y, "width": 220,
                      "align": "center", "size": 3, "color": ACCENT})
        y += 28
    if subtitle:
        items.append({"type": "text", "text": ellipsize(subtitle, 216, 1),
                      "x": 0, "y": max(y + 6, 70), "width": 220, "align": "center",
                      "size": 1, "color": CREAM})
    return {"play_sound": sound, "items": items[:6]}


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

    # User toggles (default on, preserving prior behaviour)
    if not cfg.get("notify_enabled", True):
        sys.exit(0)
    sound = NOTIFY_SOUND if cfg.get("sounds_enabled", True) else 0

    devices = cfg.get("devices", [])
    if not devices:
        sys.exit(0)

    default_id = cfg.get("default_device_id", devices[0].get("device_id"))
    dev = next((d for d in devices if d["device_id"] == default_id), devices[0])

    payload = build_payload(event.get("message", "Claude needs you"), sound)
    try:
        send_to_lcd(dev["last_known_ip"], dev["device_id"], payload)
        mark_ran()
    except Exception:
        pass


if __name__ == "__main__":
    main()
