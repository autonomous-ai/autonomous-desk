#!/usr/bin/env python3
"""Read Codex usage from local session events without accessing credentials.

Codex records token-count events, including rate-limit windows, in its local
JSONL session transcript. Hook input supplies the active transcript path. For
manual refreshes we fall back to the newest local session containing the same
event. The transcript format is treated as best-effort because it is not a
stable public API.
"""

import glob
import json
import os
from datetime import datetime, timezone


CODEX_HOME = os.path.expanduser(os.environ.get("CODEX_HOME", "~/.codex"))
SESSIONS_DIR = os.path.join(CODEX_HOME, "sessions")


def iter_lines_reverse(path, chunk_size=65536):
    """Yield UTF-8 JSONL lines newest-first without loading a large file."""
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        remainder = b""
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            block = handle.read(read_size) + remainder
            lines = block.split(b"\n")
            remainder = lines[0]
            for line in reversed(lines[1:]):
                if line:
                    yield line.decode("utf-8", errors="replace")
        if remainder:
            yield remainder.decode("utf-8", errors="replace")


def _latest_token_event(path):
    try:
        for line in iter_lines_reverse(path):
            try:
                event = json.loads(line)
            except (TypeError, ValueError):
                continue
            if event.get("type") != "event_msg":
                continue
            payload = event.get("payload") or {}
            if payload.get("type") == "token_count":
                return event
    except OSError:
        pass
    return None


def _candidate_paths(transcript_path=None):
    seen = set()
    if transcript_path:
        path = os.path.abspath(os.path.expanduser(transcript_path))
        if os.path.isfile(path):
            seen.add(path)
            yield path
    pattern = os.path.join(SESSIONS_DIR, "**", "*.jsonl")
    paths = glob.glob(pattern, recursive=True)
    def modified_at(item):
        try:
            return os.path.getmtime(item)
        except OSError:
            return 0

    paths.sort(key=modified_at, reverse=True)
    for path in paths:
        if path not in seen:
            yield path


def _limit_label(window_minutes):
    try:
        minutes = int(window_minutes)
    except (TypeError, ValueError):
        return "Account"
    if 240 <= minutes <= 360:
        return "5 hour"
    if 9000 <= minutes <= 11000:
        return "7 day"
    if minutes % 10080 == 0:
        weeks = minutes // 10080
        return "{} week".format(weeks)
    if minutes % 1440 == 0:
        return "{} day".format(minutes // 1440)
    if minutes % 60 == 0:
        return "{} hour".format(minutes // 60)
    return "{} min".format(minutes)


def _normalize_limits(rate_limits):
    normalized = []
    if not isinstance(rate_limits, dict):
        return normalized
    for key in ("primary", "secondary", "individual_limit"):
        raw = rate_limits.get(key)
        if not isinstance(raw, dict) or raw.get("used_percent") is None:
            continue
        try:
            used = float(raw.get("used_percent"))
        except (TypeError, ValueError):
            continue
        minutes = raw.get("window_minutes")
        normalized.append(
            {
                "kind": key,
                "label": _limit_label(minutes),
                "used_percent": max(0, min(100, int(round(used)))),
                "window_minutes": minutes,
                "resets_at": raw.get("resets_at"),
            }
        )
    normalized.sort(key=lambda item: item.get("window_minutes") or 10**12)
    return normalized


def read_usage(transcript_path=None):
    for path in _candidate_paths(transcript_path):
        event = _latest_token_event(path)
        if not event:
            continue
        payload = event.get("payload") or {}
        info = payload.get("info") or {}
        last_usage = info.get("last_token_usage") or {}
        context_window = info.get("model_context_window")
        context_percent = None
        if context_window:
            try:
                context_percent = int(
                    round(float(last_usage.get("total_tokens", 0)) / float(context_window) * 100)
                )
            except (TypeError, ValueError, ZeroDivisionError):
                context_percent = None
        return {
            "source_path": path,
            "timestamp": event.get("timestamp"),
            "limits": _normalize_limits(payload.get("rate_limits")),
            "tokens": info.get("total_token_usage") or {},
            "last_tokens": last_usage,
            "model_context_window": context_window,
            "context_percent": context_percent,
            "plan_type": (payload.get("rate_limits") or {}).get("plan_type"),
        }
    return None


def time_left(value, now=None):
    if value in (None, ""):
        return "N/A"
    now = now or datetime.now(timezone.utc)
    try:
        if isinstance(value, (int, float)):
            reset = datetime.fromtimestamp(value, timezone.utc)
        else:
            reset = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if reset.tzinfo is None:
                reset = reset.replace(tzinfo=timezone.utc)
        seconds = int((reset - now).total_seconds())
    except (TypeError, ValueError, OSError):
        return "N/A"
    if seconds <= 0:
        return "now"
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return "{}d {}h".format(days, hours)
    return "{}h {}m".format(hours, minutes)


def progress_color(percent):
    if percent >= 80:
        return "#c0392b"
    if percent >= 60:
        return "#d4845a"
    return "#6b8f4e"


def build_limit_card(limit_data, sound=0):
    percent = int(limit_data.get("used_percent", 0))
    label = str(limit_data.get("label") or "Account")
    reset = time_left(limit_data.get("resets_at"))
    return {
        "play_sound": sound,
        "items": [
            {
                "type": "text",
                "text": "Codex Usage",
                "x": 0,
                "y": 4,
                "width": 220,
                "align": "center",
                "size": 3,
                "color": "#d4845a",
            },
            {
                "type": "text",
                "text": "{}%".format(percent),
                "x": 18,
                "y": 38,
                "width": 100,
                "size": 4,
                "color": progress_color(percent),
            },
            {
                "type": "text",
                "text": label,
                "x": 100,
                "y": 46,
                "width": 105,
                "align": "right",
                "size": 1,
                "color": "#7eb8da",
            },
            {
                "type": "progress",
                "x": 18,
                "y": 70,
                "width": 184,
                "height": 12,
                "radius": 6,
                "value": percent,
                "color": progress_color(percent),
                "bg_color": "#3a3a3a",
            },
            {
                "type": "text",
                "text": "Resets in {}".format(reset),
                "x": 18,
                "y": 90,
                "width": 184,
                "size": 1,
                "color": "#e8dcc8",
            },
        ],
    }


def public_summary(usage):
    if not usage:
        return {"available": False, "limits": []}
    return {
        "available": True,
        "limits": usage.get("limits", []),
        "context_percent": usage.get("context_percent"),
        "last_tokens": usage.get("last_tokens", {}),
        "plan_type": usage.get("plan_type"),
        "timestamp": usage.get("timestamp"),
    }
