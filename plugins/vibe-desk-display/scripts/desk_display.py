#!/usr/bin/env python3
"""User-facing CLI for pairing and controlling the Thinking Desk display."""

import argparse
import json
import os
import secrets
import sys
import time
from datetime import datetime, timezone

import codex_usage
import device
import discover


PAIRING_TTL = 10 * 60
DISPLAY_DELAY = float(os.environ.get("AUTONOMOUS_LCD_SECTION_DELAY", "5"))
BOOL_KEYS = {
    "sounds_enabled",
    "task_done_enabled",
    "notify_enabled",
    "update_check_enabled",
    "device_warning_enabled",
    "show_insights",
}


def _pairing_payload(code):
    return {
        "play_sound": 20,
        "items": [
            {
                "type": "text",
                "text": "Pairing",
                "x": 0,
                "y": 0,
                "width": 220,
                "align": "center",
                "size": 3,
                "color": "#7eb8da",
            },
            {
                "type": "text",
                "text": code,
                "x": 0,
                "y": 35,
                "width": 220,
                "align": "center",
                "size": 4,
                "color": "#e8dcc8",
            },
            {
                "type": "text",
                "text": "Enter this code",
                "x": 0,
                "y": 85,
                "width": 220,
                "align": "center",
                "size": 2,
                "color": "#9a9488",
            },
        ],
    }


def pair_start(_args):
    found = discover.cache_check()
    if not found:
        found = discover.parallel_scan()
    if not found:
        print(
            "No displays found. Make sure the display is powered on and "
            "connected to the same Wi-Fi."
        )
        return 1

    codes = set()
    pending = []
    for found_device in found:
        code = None
        while code is None or code in codes:
            code = str(secrets.randbelow(9000) + 1000)
        codes.add(code)
        if device.try_send(
            found_device.get("ip"),
            found_device.get("device_id"),
            _pairing_payload(code),
        ):
            pending.append(
                {
                    "code": code,
                    "device_id": found_device.get("device_id"),
                    "ip": found_device.get("ip"),
                }
            )

    if not pending:
        print(
            "Displays were found but could not be reached. Check the Wi-Fi "
            "connection and try again."
        )
        return 1

    device.atomic_write_json(
        device.PAIRING_PATH,
        {"created_at": time.time(), "devices": pending},
    )
    print(
        "Found {} display(s). What 4-digit code do you see on the display?".format(
            len(pending)
        )
    )
    return 0


def pair_complete(args):
    pending = device.load_json(device.PAIRING_PATH, {})
    if not isinstance(pending, dict):
        pending = {}
    if time.time() - pending.get("created_at", 0) > PAIRING_TTL:
        print("That pairing session expired. Start pairing again.")
        return 1
    match = next(
        (
            item
            for item in pending.get("devices", [])
            if str(item.get("code")) == str(args.code).strip()
        ),
        None,
    )
    if not match:
        print("That code did not match. Check the display and try again.")
        return 1

    cfg = device.load_config()
    now = datetime.now(timezone.utc).isoformat()
    entry = {
        "device_id": match["device_id"],
        "label": args.label,
        "last_known_ip": match["ip"],
        "last_seen_at": now,
    }
    existing = next(
        (
            item
            for item in cfg.get("devices", [])
            if item.get("device_id") == entry["device_id"]
        ),
        None,
    )
    if existing is None:
        cfg.setdefault("devices", []).append(entry)
    else:
        existing.update(entry)
    if not cfg.get("default_device_id"):
        cfg["default_device_id"] = entry["device_id"]
    device.save_config(cfg)
    try:
        os.unlink(device.PAIRING_PATH)
    except OSError:
        pass

    confirmation = device.build_text_payload(
        "Paired with Codex", size=2, color="green", sound=20
    )
    device.try_send(entry["last_known_ip"], entry["device_id"], confirmation)
    print("Paired successfully. Your display should show a confirmation.")
    return 0


def unpair(args):
    cfg = device.load_config()
    selected = device.get_device(cfg, args.device)
    if not selected:
        print("No paired display was found.")
        return 1
    selected_id = selected.get("device_id")
    cfg["devices"] = [
        item for item in cfg.get("devices", []) if item.get("device_id") != selected_id
    ]
    if cfg.get("default_device_id") == selected_id:
        cfg["default_device_id"] = (
            cfg["devices"][0].get("device_id") if cfg["devices"] else None
        )
    device.save_config(cfg)
    print("Display unpaired.")
    return 0


def notify(args):
    cfg = device.load_config()
    selected = device.get_device(cfg, args.device)
    if not selected:
        print("No display is paired. Pair a display first.")
        return 1
    sound = args.sound if cfg.get("sounds_enabled", True) else 0
    payload = device.build_text_payload(args.message, args.size, args.color, sound)
    if args.dry_run:
        print(json.dumps({"target": selected.get("last_known_ip"), "payload": payload}, indent=2))
        return 0
    if not device.send_with_reconnect(cfg, selected, payload):
        print("The display could not be reached. Check its Wi-Fi connection.")
        return 1
    print("Notification sent.")
    return 0


def _validate_layout(payload):
    if not isinstance(payload, dict):
        raise ValueError("Layout must be a JSON object.")
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("Layout must contain a non-empty items array.")
    if len(items) > 6:
        raise ValueError("Layout supports at most 6 items.")
    allowed_types = {"text", "rect", "line", "progress"}
    cleaned = dict(payload)
    cleaned_items = []
    for item in items:
        if not isinstance(item, dict) or item.get("type") not in allowed_types:
            raise ValueError("Layout contains an unsupported item type.")
        item = dict(item)
        if "text" in item:
            item["text"] = str(item["text"])[:95]
        if item.get("type") == "progress":
            item["value"] = max(0, min(100, int(item.get("value", 0))))
        cleaned_items.append(item)
    cleaned["items"] = cleaned_items
    cleaned.setdefault("play_sound", 20)
    return cleaned


def send_layout(args):
    try:
        with open(args.file, "r", encoding="utf-8") as handle:
            payload = _validate_layout(json.load(handle))
    except (OSError, ValueError, TypeError) as error:
        print("Invalid layout: {}".format(error))
        return 1
    cfg = device.load_config()
    selected = device.get_device(cfg, args.device)
    if not selected:
        print("No display is paired. Pair a display first.")
        return 1
    if not cfg.get("sounds_enabled", True):
        payload["play_sound"] = 0
    if args.dry_run:
        print(json.dumps({"target": selected.get("last_known_ip"), "payload": payload}, indent=2))
        return 0
    if not device.send_with_reconnect(cfg, selected, payload):
        print("The display could not be reached. Check its Wi-Fi connection.")
        return 1
    print("Layout sent.")
    return 0


def usage(args):
    result = codex_usage.read_usage(args.transcript)
    if args.json:
        print(json.dumps(codex_usage.public_summary(result), indent=2))
        return 0 if result else 1
    if not result or not result.get("limits"):
        print(
            "Codex usage data is not available yet. Complete a Codex turn, "
            "then try again."
        )
        return 1
    if not args.display:
        for limit_data in result["limits"]:
            print(
                "{}: {}% used, resets in {}".format(
                    limit_data["label"],
                    limit_data["used_percent"],
                    codex_usage.time_left(limit_data.get("resets_at")),
                )
            )
        if result.get("context_percent") is not None:
            print("Current context: {}%".format(result["context_percent"]))
        return 0

    cfg = device.load_config()
    selected = device.get_device(cfg, args.device)
    if not selected:
        print("No display is paired. Pair a display first.")
        return 1
    sound = 20 if cfg.get("sounds_enabled", True) else 0
    for index, limit_data in enumerate(result["limits"][:2]):
        if index and DISPLAY_DELAY:
            time.sleep(DISPLAY_DELAY)
        card_sound = sound if index == 0 else 0
        if not device.send_with_reconnect(
            cfg, selected, codex_usage.build_limit_card(limit_data, card_sound)
        ):
            print("The display could not be reached. Check its Wi-Fi connection.")
            return 1
    if cfg.get("show_insights", True):
        try:
            import insights

            if DISPLAY_DELAY:
                time.sleep(DISPLAY_DELAY)
            insights.rotate_one(cfg, selected)
        except Exception:
            pass
    print("Codex usage sent to the display.")
    return 0


def configure(args):
    cfg = device.load_config()
    if args.key == "usage_threshold":
        try:
            value = int(args.value)
        except ValueError:
            print("usage_threshold must be a number from 0 to 100.")
            return 1
        if value < 0 or value > 100:
            print("usage_threshold must be a number from 0 to 100.")
            return 1
    elif args.key in BOOL_KEYS:
        low = args.value.lower()
        if low not in {"true", "false", "on", "off", "yes", "no", "1", "0"}:
            print("{} must be true or false.".format(args.key))
            return 1
        value = low in {"true", "on", "yes", "1"}
    else:
        print("Unsupported setting: {}".format(args.key))
        return 1
    cfg[args.key] = value
    device.save_config(cfg)
    print("{} updated.".format(args.key))
    return 0


def status(_args):
    cfg = device.load_config()
    selected = device.get_device(cfg)
    if not selected:
        print("No display is paired.")
        return 1
    print("Paired display: {}".format(selected.get("label", "My Display")))
    print("Sounds: {}".format("on" if cfg.get("sounds_enabled", True) else "off"))
    print("Usage threshold: {}%".format(cfg.get("usage_threshold", 80)))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("pair-start", help="Discover displays and show OTP codes")
    start.set_defaults(func=pair_start)

    complete = subparsers.add_parser("pair-complete", help="Complete OTP pairing")
    complete.add_argument("code")
    complete.add_argument("--label", default="My Display")
    complete.set_defaults(func=pair_complete)

    remove = subparsers.add_parser("unpair", help="Remove a paired display")
    remove.add_argument("--device")
    remove.set_defaults(func=unpair)

    send = subparsers.add_parser("notify", help="Send a custom notification")
    send.add_argument("message")
    send.add_argument("--device")
    send.add_argument("--size", type=int, default=2)
    send.add_argument("--color", default="green")
    send.add_argument("--sound", type=int, default=20)
    send.add_argument("--dry-run", action="store_true")
    send.set_defaults(func=notify)

    layout = subparsers.add_parser("layout", help="Send a rich-layout JSON file")
    layout.add_argument("file")
    layout.add_argument("--device")
    layout.add_argument("--dry-run", action="store_true")
    layout.set_defaults(func=send_layout)

    show_usage = subparsers.add_parser("usage", help="Read or display Codex usage")
    show_usage.add_argument("--display", action="store_true")
    show_usage.add_argument("--json", action="store_true")
    show_usage.add_argument("--transcript")
    show_usage.add_argument("--device")
    show_usage.set_defaults(func=usage)

    config = subparsers.add_parser("config", help="Change a display setting")
    config.add_argument("key")
    config.add_argument("value")
    config.set_defaults(func=configure)

    show_status = subparsers.add_parser("status", help="Show pairing status")
    show_status.set_defaults(func=status)
    return parser


def main():
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
