#!/usr/bin/env python3
"""Hook: send Task Done notification to LCD when Claude stops.
If usage >= threshold, also sends usage sections after a delay.
Rate-limited to once per 60s."""

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

CONFIG_PATH = os.path.expanduser("~/.config/autonomous-lcd.json")
COOLDOWN_PATH = os.path.expanduser("~/.config/autonomous-lcd-done.last")
COOLDOWN_SECONDS = 60
DEFAULT_USAGE_THRESHOLD = 80
LCD_PORT = 3000
SECTION_DELAY = 5

# Update-available card: GitHub is polled at most once per day; the card is
# shown at most once per day and disappears once you're on the latest version.
UPDATE_STATE_PATH = os.path.expanduser("~/.config/autonomous-lcd-update.json")
UPDATE_CHECK_INTERVAL = 24 * 3600
PLUGIN_JSON_URL = (
    "https://raw.githubusercontent.com/autonomous-ai/autonomous-desk/main/software/plugin.json"
)


def should_run():
    try:
        last = float(open(COOLDOWN_PATH).read().strip())
        return (time.time() - last) >= COOLDOWN_SECONDS
    except Exception:
        return True


def mark_ran():
    with open(COOLDOWN_PATH, "w") as f:
        f.write(str(time.time()))


def send_to_lcd(ip, device_id, payload):
    req = urllib.request.Request(
        f"http://{ip}:{LCD_PORT}/lcd",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Device-ID": device_id},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=3)


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


def build_usage_section1(pct_5h, reset_5h, sound=20):
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


def build_usage_section2(pct_7d, reset_7d):
    return {
        "play_sound": 0,
        "items": [
            {"type": "text", "text": f"{pct_7d}%", "x": 18, "y": 10, "width": 100, "size": 4, "color": "#e8dcc8"},
            {"type": "text", "text": "Weekly", "x": 100, "y": 18, "width": 105, "align": "right", "size": 1, "color": "#a09888"},
            {"type": "progress", "x": 18, "y": 45, "width": 184, "height": 12, "radius": 6, "value": pct_7d, "color": progress_color(pct_7d), "bg_color": "#3a3a3a"},
            {"type": "text", "text": f"Resets in {reset_7d}", "x": 18, "y": 63, "width": 180, "size": 1, "color": "#9a9488"},
            {"type": "text", "text": "* Baking...", "x": 0, "y": 87, "width": 220, "align": "center", "size": 2, "color": "#d4845a"},
        ],
    }


def _load_update_state():
    try:
        with open(UPDATE_STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_update_state(state):
    try:
        with open(UPDATE_STATE_PATH, "w") as f:
            json.dump(state, f)
    except Exception:
        pass


def local_version():
    """Version of the plugin this script ships with (../plugin.json)."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "plugin.json")) as f:
            return json.load(f).get("version")
    except Exception:
        return None


def _fetch_latest_version():
    try:
        req = urllib.request.Request(
            PLUGIN_JSON_URL, headers={"User-Agent": "vibe-desk-display"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read()).get("version")
    except Exception:
        return None


def _parse_version(v):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except Exception:
        return None


def latest_if_newer():
    """Return the latest version string if it's newer than the local one, else
    None. Hits GitHub at most once per UPDATE_CHECK_INTERVAL; result cached."""
    local = local_version()
    if not local:
        return None
    state = _load_update_state()
    now = time.time()
    latest = state.get("latest")
    if not latest or (now - state.get("checked_at", 0)) >= UPDATE_CHECK_INTERVAL:
        fetched = _fetch_latest_version()
        if fetched:
            latest = fetched
            state["latest"] = latest
        state["checked_at"] = now
        _save_update_state(state)
    lv, cv = _parse_version(latest), _parse_version(local)
    if lv and cv and lv > cv:
        return latest
    return None


def _should_show_update(latest):
    """Show the card at most once per day per pending version."""
    state = _load_update_state()
    today = int(time.time() // 86400)
    return not (state.get("shown_day") == today and state.get("shown_version") == latest)


def _mark_update_shown(latest):
    state = _load_update_state()
    state["shown_day"] = int(time.time() // 86400)
    state["shown_version"] = latest
    _save_update_state(state)


def build_update_card(local, latest):
    # Silent on purpose — an update notice shouldn't buzz like a real alert.
    return {
        "play_sound": 0,
        "items": [
            {"type": "text", "text": "UPDATE AVAILABLE", "x": 0, "y": 22, "width": 220, "align": "center", "size": 2, "color": "#d4845a"},
            {"type": "text", "text": f"v{local} -> v{latest}", "x": 0, "y": 48, "width": 220, "align": "center", "size": 1, "color": "#e8dcc8"},
            {"type": "text", "text": "run /plugin update", "x": 0, "y": 70, "width": 220, "align": "center", "size": 1, "color": "#9a9488"},
        ],
    }


def maybe_show_update(ip, device_id):
    """After Task Done, surface an update card if one is pending (≤1/day)."""
    try:
        latest = latest_if_newer()
        if not latest or not _should_show_update(latest):
            return
        time.sleep(2)
        send_to_lcd(ip, device_id, build_update_card(local_version(), latest))
        _mark_update_shown(latest)
    except Exception:
        pass


def main():
    json.load(sys.stdin)

    if not should_run():
        sys.exit(0)

    if not os.path.exists(CONFIG_PATH):
        sys.exit(0)

    with open(CONFIG_PATH) as f:
        cfg = json.load(f)

    devices = cfg.get("devices", [])
    if not devices:
        sys.exit(0)

    default_id = cfg.get("default_device_id", devices[0].get("device_id"))
    dev = next((d for d in devices if d["device_id"] == default_id), devices[0])
    ip = dev["last_known_ip"]
    device_id = dev["device_id"]
    threshold = cfg.get("usage_threshold", DEFAULT_USAGE_THRESHOLD)

    # User toggles (default on, preserving prior behaviour)
    sound = 20 if cfg.get("sounds_enabled", True) else 0

    # 1. Send Task Done (unless disabled)
    if cfg.get("task_done_enabled", True):
        task_done_payload = {
            "play_sound": sound,
            "items": [
                {"type": "text", "text": "Task Done", "x": 0, "y": 34, "width": 220, "align": "center", "size": 4, "color": "#6b8f4e"},
            ],
        }
        try:
            send_to_lcd(ip, device_id, task_done_payload)
        except Exception:
            pass

    mark_ran()

    # 1b. Show an update-available card if a newer version exists (silent,
    # at most once/day). Runs before the usage early-exits below.
    if cfg.get("update_check_enabled", True):
        maybe_show_update(ip, device_id)

    # 2. Check usage against threshold
    token = get_token()
    if not token:
        sys.exit(0)

    try:
        usage = fetch_usage(token)
    except Exception:
        sys.exit(0)

    pct_5h = int(usage["five_hour"]["utilization"])
    pct_7d = int(usage["seven_day"]["utilization"])

    if pct_5h < threshold and pct_7d < threshold:
        sys.exit(0)

    reset_5h = time_left(usage["five_hour"]["resets_at"])
    reset_7d = time_left(usage["seven_day"]["resets_at"])

    # 3. Send usage sections
    try:
        time.sleep(SECTION_DELAY)
        send_to_lcd(ip, device_id, build_usage_section1(pct_5h, reset_5h, sound))
        time.sleep(SECTION_DELAY)
        send_to_lcd(ip, device_id, build_usage_section2(pct_7d, reset_7d))
    except Exception:
        pass


if __name__ == "__main__":
    main()
