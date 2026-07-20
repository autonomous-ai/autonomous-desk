#!/usr/bin/env python3
"""Codex PermissionRequest hook: ping the display when approval is needed."""

import json
import os
import sys
import time

import device


COOLDOWN_PATH = os.path.join(device.CONFIG_DIR, "autonomous-lcd-notify.last")
COOLDOWN_SECONDS = 8
NOTIFY_SOUND = 1


def should_run(now=None):
    now = time.time() if now is None else now
    try:
        with open(COOLDOWN_PATH, "r", encoding="utf-8") as handle:
            last = float(handle.read().strip())
        return now - last >= COOLDOWN_SECONDS
    except (OSError, TypeError, ValueError):
        return True


def mark_ran(now=None):
    try:
        os.makedirs(device.CONFIG_DIR, mode=0o700, exist_ok=True)
        with open(COOLDOWN_PATH, "w", encoding="utf-8") as handle:
            handle.write(str(time.time() if now is None else now))
        os.chmod(COOLDOWN_PATH, 0o600)
    except OSError:
        pass


def event_tool_name(event):
    if not isinstance(event, dict):
        return None
    tool = event.get("tool")
    if isinstance(tool, dict):
        nested = tool.get("name")
    else:
        nested = None
    return (
        event.get("tool_name")
        or event.get("toolName")
        or event.get("matcher")
        or nested
    )


def main():
    try:
        event = json.load(sys.stdin)
    except (TypeError, ValueError):
        event = {}

    if not should_run():
        return

    cfg = device.load_config()
    if not cfg.get("notify_enabled", True):
        return
    dev = device.get_device(cfg)
    if not dev:
        return

    sound = NOTIFY_SOUND if cfg.get("sounds_enabled", True) else 0
    payload = device.build_needs_you_payload(event_tool_name(event), sound)
    if device.send_with_reconnect(cfg, dev, payload):
        mark_ran()
        return

    mark_ran()
    if cfg.get("device_warning_enabled", True):
        try:
            import discover

            discover.warn_user(
                "Could not reach {} on your network. Check that the display "
                "is powered on and on the same Wi-Fi, or pair it again.".format(
                    dev.get("label", "your desk display")
                )
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
