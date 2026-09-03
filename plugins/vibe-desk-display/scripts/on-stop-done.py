#!/usr/bin/env python3
"""Codex Stop hook: show task completion and account usage on the display."""

import json
import os
import sys
import time
import urllib.request

import codex_usage
import device


COOLDOWN_PATH = os.path.join(device.CONFIG_DIR, "autonomous-lcd-codex-done.last")
UPDATE_STATE_PATH = os.path.join(device.CONFIG_DIR, "autonomous-lcd-codex-update.json")
COOLDOWN_SECONDS = 60
SECTION_DELAY = float(os.environ.get("AUTONOMOUS_LCD_SECTION_DELAY", "5"))
UPDATE_CHECK_INTERVAL = 24 * 3600
PLUGIN_JSON_URL = (
    "https://raw.githubusercontent.com/autonomous-ai/autonomous-desk/"
    "main/plugins/vibe-desk-display/.codex-plugin/plugin.json"
)


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


def _load_update_state():
    value = device.load_json(UPDATE_STATE_PATH, {})
    return value if isinstance(value, dict) else {}


def _save_update_state(value):
    try:
        device.atomic_write_json(UPDATE_STATE_PATH, value)
    except OSError:
        pass


def local_version():
    manifest = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        ".codex-plugin",
        "plugin.json",
    )
    value = device.load_json(manifest, {})
    return value.get("version") if isinstance(value, dict) else None


def _parse_version(value):
    try:
        core = str(value).split("+", 1)[0].split("-", 1)[0]
        return tuple(int(part) for part in core.split("."))
    except (TypeError, ValueError):
        return None


def _latest_if_newer(now=None):
    current = local_version()
    if not current:
        return None
    now = time.time() if now is None else now
    state = _load_update_state()
    latest = state.get("latest")
    if not latest or now - state.get("checked_at", 0) >= UPDATE_CHECK_INTERVAL:
        try:
            request = urllib.request.Request(
                PLUGIN_JSON_URL,
                headers={"User-Agent": "autonomous-desk-codex"},
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                latest = json.loads(response.read()).get("version")
        except Exception:
            latest = state.get("latest")
        state["checked_at"] = now
        if latest:
            state["latest"] = latest
        _save_update_state(state)
    local_parts = _parse_version(current)
    latest_parts = _parse_version(latest)
    if local_parts and latest_parts and latest_parts > local_parts:
        return latest
    return None


def _build_update_card(current, latest):
    return {
        "play_sound": 0,
        "items": [
            {
                "type": "text",
                "text": "UPDATE AVAILABLE",
                "x": 0,
                "y": 22,
                "width": 220,
                "align": "center",
                "size": 2,
                "color": "#d4845a",
            },
            {
                "type": "text",
                "text": "v{} -> v{}".format(current, latest),
                "x": 0,
                "y": 48,
                "width": 220,
                "align": "center",
                "size": 1,
                "color": "#e8dcc8",
            },
            {
                "type": "text",
                "text": "update the plugin",
                "x": 0,
                "y": 70,
                "width": 220,
                "align": "center",
                "size": 1,
                "color": "#9a9488",
            },
        ],
    }


def maybe_show_update(cfg, dev, now=None):
    latest = _latest_if_newer(now)
    if not latest:
        return
    now = time.time() if now is None else now
    today = int(now // 86400)
    state = _load_update_state()
    if state.get("shown_day") == today and state.get("shown_version") == latest:
        return
    time.sleep(min(2, SECTION_DELAY))
    if device.send_with_reconnect(
        cfg, dev, _build_update_card(local_version(), latest)
    ):
        state = _load_update_state()
        state["shown_day"] = today
        state["shown_version"] = latest
        _save_update_state(state)


def event_transcript_path(event):
    """Return the session JSONL path from a Stop hook payload.

    Current Codex (and Claude Code) emit ``transcript_path``. Codex session
    files are also recorded as ``rollout_path`` (rollout-*.jsonl).
    """
    if not isinstance(event, dict):
        return None
    for key in ("transcript_path", "rollout_path"):
        value = event.get(key)
        if value:
            return value
    return None


def _warn_unreachable(cfg, dev):
    if not cfg.get("device_warning_enabled", True):
        return
    try:
        import discover

        discover.warn_user(
            "Could not reach {} on your network. Check that the display is "
            "powered on and on the same Wi-Fi, or pair it again.".format(
                dev.get("label", "your desk display")
            )
        )
    except Exception:
        pass


def main():
    try:
        event = json.load(sys.stdin)
    except (TypeError, ValueError):
        event = {}

    if not should_run():
        return

    cfg = device.load_config()
    dev = device.get_device(cfg)
    if not dev:
        return

    sound = 20 if cfg.get("sounds_enabled", True) else 0
    if cfg.get("task_done_enabled", True):
        if not device.send_with_reconnect(
            cfg, dev, device.build_task_done_payload(sound)
        ):
            mark_ran()
            _warn_unreachable(cfg, dev)
            return

    mark_ran()

    if cfg.get("update_check_enabled", True):
        maybe_show_update(cfg, dev)

    usage = codex_usage.read_usage(event_transcript_path(event))
    limits = (usage or {}).get("limits") or []
    try:
        threshold = int(cfg.get("usage_threshold", 80))
    except (TypeError, ValueError):
        threshold = 80
    if not limits or not any(item["used_percent"] >= threshold for item in limits):
        return

    for index, item in enumerate(limits[:2]):
        if SECTION_DELAY:
            time.sleep(SECTION_DELAY)
        card_sound = sound if index == 0 and not cfg.get("task_done_enabled", True) else 0
        if not device.send_with_reconnect(
            cfg, dev, codex_usage.build_limit_card(item, card_sound)
        ):
            _warn_unreachable(cfg, dev)
            return

    if cfg.get("show_insights", True):
        try:
            import insights

            if SECTION_DELAY:
                time.sleep(SECTION_DELAY)
            insights.rotate_one(cfg, dev)
        except Exception:
            pass


if __name__ == "__main__":
    main()
