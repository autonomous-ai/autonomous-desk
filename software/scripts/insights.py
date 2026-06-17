#!/usr/bin/env python3
"""Local Claude Code builder-insights engine.

Reads your local Claude Code session transcripts (~/.claude/projects/**/*.jsonl)
and derives a "builder profile" — peak coding hour, archetype, top model, token
economy, steering style, parallelization and velocity — entirely on-device.

Inspired by Paxel (paxel.ycombinator.com), but privacy-first: nothing leaves the
machine. Use `--json` to dump the computed profile, or `--display` to rotate the
insight cards onto a paired VibeDesk display.

Stdlib only — no pip install.
"""

import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone

PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
CONFIG_PATH = os.path.expanduser("~/.config/autonomous-lcd.json")
CACHE_PATH = os.path.expanduser("~/.config/autonomous-lcd-insights.json")
CACHE_TTL = 3600  # recompute the profile at most once an hour
LCD_PORT = 3000
CARD_DELAY = 6  # seconds between rotating cards

EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
# short, corrective prompts that signal a "Director" steering style
CORRECTION_RE = re.compile(
    r"^\s*(no|nope|stop|wait|undo|revert|fix|don'?t|wrong|again|"
    r"actually|instead|not that|go back|khong|sai|lam lai)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Transcript parsing
# --------------------------------------------------------------------------- #
def iter_sessions():
    """Yield (project_name, filepath) for every session transcript."""
    pattern = os.path.join(PROJECTS_DIR, "*", "*.jsonl")
    for path in glob.glob(pattern):
        project = os.path.basename(os.path.dirname(path))
        yield project, path


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def project_label(raw):
    """Turn a flattened project dir name into a readable label."""
    # dirs look like '-Volumes-SamsungSSD-bvm-autonomous-desk'
    parts = [p for p in raw.split("-") if p]
    if not parts:
        return raw
    return parts[-1][:18]


def analyze():
    stats = {
        "sessions": 0,
        "user_prompts": 0,
        "assistant_turns": 0,
        "prompt_words": 0,
        "corrections": 0,
        "tool_calls": 0,
        "multi_tool_turns": 0,
        "edits": 0,
        "tok_input": 0,
        "tok_output": 0,
        "tok_cache_read": 0,
        "tok_cache_creation": 0,
    }
    models = Counter()
    tools = Counter()
    by_project = Counter()
    hours = Counter()          # local hour-of-day -> prompt count
    active_days = set()        # local date strings
    first_ts = None
    last_ts = None

    for project, path in iter_sessions():
        stats["sessions"] += 1
        label = project_label(project)
        try:
            fh = open(path, "r")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                typ = d.get("type")
                msg = d.get("message") if isinstance(d.get("message"), dict) else {}
                ts = parse_ts(d.get("timestamp"))
                if ts:
                    local = ts.astimezone()
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts

                if typ == "user" and not d.get("isSidechain"):
                    content = msg.get("content")
                    if isinstance(content, str) and content.strip():
                        # real human prompt (tool results arrive as a list)
                        stats["user_prompts"] += 1
                        by_project[label] += 1
                        words = content.split()
                        stats["prompt_words"] += len(words)
                        if CORRECTION_RE.match(content) and len(words) <= 12:
                            stats["corrections"] += 1
                        if ts:
                            hours[ts.astimezone().hour] += 1
                            active_days.add(ts.astimezone().date().isoformat())

                elif typ == "assistant":
                    stats["assistant_turns"] += 1
                    if msg.get("model"):
                        models[msg["model"]] += 1
                    usage = msg.get("usage") or {}
                    stats["tok_input"] += usage.get("input_tokens", 0) or 0
                    stats["tok_output"] += usage.get("output_tokens", 0) or 0
                    stats["tok_cache_read"] += usage.get("cache_read_input_tokens", 0) or 0
                    stats["tok_cache_creation"] += usage.get("cache_creation_input_tokens", 0) or 0
                    content = msg.get("content")
                    if isinstance(content, list):
                        turn_tools = [
                            b.get("name")
                            for b in content
                            if isinstance(b, dict) and b.get("type") == "tool_use"
                        ]
                        stats["tool_calls"] += len(turn_tools)
                        if len(turn_tools) >= 2:
                            stats["multi_tool_turns"] += 1
                        for name in turn_tools:
                            tools[name] += 1
                            if name in EDIT_TOOLS:
                                stats["edits"] += 1

    return _derive(stats, models, tools, by_project, hours, active_days, first_ts, last_ts)


# --------------------------------------------------------------------------- #
# Derived metrics + archetype
# --------------------------------------------------------------------------- #
def _streak(active_days):
    """Consecutive days up to today (local)."""
    if not active_days:
        return 0
    days = sorted(active_days, reverse=True)
    today = datetime.now().astimezone().date()
    from datetime import date, timedelta
    cur = date.fromisoformat(days[0])
    # streak only counts if the most recent active day is today or yesterday
    if (today - cur).days > 1:
        return 0
    streak = 1
    prev = cur
    for d in days[1:]:
        dd = date.fromisoformat(d)
        if (prev - dd).days == 1:
            streak += 1
            prev = dd
        elif (prev - dd).days == 0:
            continue
        else:
            break
    return streak


def _archetype(peak_hour, corr_ratio, avg_tools, avg_words):
    """Single headline label, Paxel-style."""
    if peak_hour is not None and (peak_hour >= 22 or peak_hour <= 4):
        return "Night Owl"
    if peak_hour is not None and 5 <= peak_hour <= 8:
        return "Early Bird"
    if avg_tools >= 2.2:
        return "Velocity Machine"
    if avg_words >= 40:
        return "The Architect"
    if corr_ratio >= 0.18:
        return "Quality Guardian"
    return "Steady Builder"


def _derive(stats, models, tools, by_project, hours, active_days, first_ts, last_ts):
    prompts = max(stats["user_prompts"], 1)
    turns = max(stats["assistant_turns"], 1)
    peak_hour = hours.most_common(1)[0][0] if hours else None
    total_cache = stats["tok_cache_read"] + stats["tok_cache_creation"] + stats["tok_input"]
    cache_hit = (stats["tok_cache_read"] / total_cache * 100) if total_cache else 0
    corr_ratio = stats["corrections"] / prompts
    avg_tools = stats["tool_calls"] / turns
    avg_words = stats["prompt_words"] / prompts

    top_model = models.most_common(1)[0][0] if models else "n/a"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "span": {
            "first": first_ts.isoformat() if first_ts else None,
            "last": last_ts.isoformat() if last_ts else None,
            "active_days": len(active_days),
            "streak": _streak(active_days),
        },
        "activity": {
            "sessions": stats["sessions"],
            "prompts": stats["user_prompts"],
            "assistant_turns": stats["assistant_turns"],
            "peak_hour": peak_hour,
            "hour_histogram": dict(sorted(hours.items())),
        },
        "models": {
            "top": short_model(top_model),
            "top_raw": top_model,
            "breakdown": {short_model(k): v for k, v in models.most_common(5)},
        },
        "tokens": {
            "input": stats["tok_input"],
            "output": stats["tok_output"],
            "cache_read": stats["tok_cache_read"],
            "cache_creation": stats["tok_cache_creation"],
            "cache_hit_pct": round(cache_hit, 1),
        },
        "steering": {
            "avg_prompt_words": round(avg_words, 1),
            "correction_ratio": round(corr_ratio, 3),
        },
        "velocity": {
            "tool_calls": stats["tool_calls"],
            "avg_tools_per_turn": round(avg_tools, 2),
            "multi_tool_turns": stats["multi_tool_turns"],
            "edits": stats["edits"],
            "top_tools": dict(tools.most_common(5)),
        },
        "top_projects": dict(by_project.most_common(5)),
        "archetype": _archetype(peak_hour, corr_ratio, avg_tools, avg_words),
    }


def short_model(m):
    if not m or m == "n/a":
        return "n/a"
    m = m.replace("claude-", "").replace("<synthetic>", "synthetic")
    # opus-4-7 -> Opus 4.7
    mm = re.match(r"(opus|sonnet|haiku)-(\d+)-(\d+)", m)
    if mm:
        return f"{mm.group(1).title()} {mm.group(2)}.{mm.group(3)}"
    return m


# --------------------------------------------------------------------------- #
# Display cards
# --------------------------------------------------------------------------- #
def fmt_tokens(n):
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.0f}K"
    return str(n)


def fmt_hour(h):
    if h is None:
        return "n/a"
    suffix = "am" if h < 12 else "pm"
    hh = h % 12 or 12
    return f"{hh}{suffix}"


# The device font is ~6px wide per character at size 1, scaling linearly with
# the size multiplier. The content viewport is 220px wide, so pick the largest
# size (down to 1) whose rendered width fits the box — keeps long archetype
# names, model ids and project labels from running off the screen edge.
CHAR_W = 6


def fit_size(text, box_w, max_size=4, min_size=1):
    n = max(len(text), 1)
    for s in range(max_size, min_size - 1, -1):
        if n * CHAR_W * s <= box_w:
            return s
    return min_size


def ellipsize(text, box_w, size):
    """Trim text (with a trailing ellipsis) so it fits box_w at the given size."""
    max_chars = max(box_w // (CHAR_W * size), 1)
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return text[:max_chars]
    return text[: max_chars - 1] + "…"


ACCENT = "#d4845a"
CREAM = "#e8dcc8"
BLUE = "#7eb8da"
MUTE = "#9a9488"
GREEN = "#9bad67"


def card_archetype(p):
    span = p["span"]
    arch = p["archetype"]
    arch_size = fit_size(arch, 220, max_size=3)
    return {
        "play_sound": 20,
        "items": [
            {"type": "text", "text": "You are", "x": 0, "y": 6, "width": 220, "align": "center", "size": 1, "color": MUTE},
            {"type": "text", "text": arch, "x": 0, "y": 24, "width": 220, "align": "center", "size": arch_size, "color": ACCENT},
            {"type": "text", "text": f"{span['streak']}d streak", "x": 0, "y": 70, "width": 110, "align": "center", "size": 2, "color": GREEN},
            {"type": "text", "text": f"{span['active_days']} active days", "x": 110, "y": 73, "width": 110, "align": "center", "size": 1, "color": CREAM},
        ],
    }


def card_rhythm(p):
    act = p["activity"]
    peak = fmt_hour(act["peak_hour"])
    return {
        "play_sound": 0,
        "items": [
            {"type": "text", "text": "Peak Hour", "x": 0, "y": 6, "width": 220, "align": "center", "size": 2, "color": BLUE},
            {"type": "text", "text": peak, "x": 0, "y": 30, "width": 220, "align": "center", "size": 4, "color": CREAM},
            {"type": "text", "text": f"{act['sessions']} sessions", "x": 0, "y": 80, "width": 110, "align": "center", "size": 1, "color": MUTE},
            {"type": "text", "text": f"{act['prompts']} prompts", "x": 110, "y": 80, "width": 110, "align": "center", "size": 1, "color": MUTE},
        ],
    }


def card_model(p):
    top = p["models"]["top"]
    return {
        "play_sound": 0,
        "items": [
            {"type": "text", "text": "Top Model", "x": 0, "y": 6, "width": 220, "align": "center", "size": 2, "color": BLUE},
            {"type": "text", "text": top, "x": 0, "y": 34, "width": 220, "align": "center", "size": fit_size(top, 220, max_size=3), "color": ACCENT},
            {"type": "text", "text": f"{p['velocity']['tool_calls']} tool calls", "x": 0, "y": 82, "width": 220, "align": "center", "size": 1, "color": MUTE},
        ],
    }


def card_tokens(p):
    t = p["tokens"]
    hit = int(t["cache_hit_pct"])
    out = fmt_tokens(t["output"])
    return {
        "play_sound": 0,
        "items": [
            {"type": "text", "text": "Token Economy", "x": 0, "y": 4, "width": 220, "align": "center", "size": 2, "color": BLUE},
            {"type": "text", "text": out, "x": 18, "y": 28, "width": 100, "size": fit_size(out, 96, max_size=4), "color": CREAM},
            {"type": "text", "text": "out", "x": 120, "y": 40, "width": 90, "align": "right", "size": 1, "color": MUTE},
            {"type": "text", "text": f"cache hit {hit}%", "x": 18, "y": 72, "width": 184, "size": 1, "color": GREEN},
            {"type": "progress", "x": 18, "y": 90, "width": 184, "height": 10, "radius": 5, "value": hit, "color": GREEN, "bg_color": "#3a3a3a"},
        ],
    }


def card_style(p):
    s = p["steering"]
    v = p["velocity"]
    return {
        "play_sound": 0,
        "items": [
            {"type": "text", "text": "Builder Style", "x": 0, "y": 4, "width": 220, "align": "center", "size": 2, "color": BLUE},
            {"type": "text", "text": f"{s['avg_prompt_words']} words/prompt", "x": 12, "y": 32, "width": 200, "size": 1, "color": CREAM},
            {"type": "text", "text": f"{v['avg_tools_per_turn']} tools/turn", "x": 12, "y": 52, "width": 200, "size": 1, "color": CREAM},
            {"type": "text", "text": f"{int(s['correction_ratio']*100)}% course-corrects", "x": 12, "y": 72, "width": 200, "size": 1, "color": ACCENT},
        ],
    }


def card_projects(p):
    items = [
        {"type": "text", "text": "Top Projects", "x": 0, "y": 4, "width": 220, "align": "center", "size": 2, "color": BLUE},
    ]
    y = 30
    for name, count in list(p["top_projects"].items())[:3]:
        # name column spans x14..x140; trim so it never collides with the count
        label = ellipsize(name, 126, 2)
        items.append({"type": "text", "text": label, "x": 14, "y": y, "width": 126, "size": 2, "color": CREAM})
        items.append({"type": "text", "text": str(count), "x": 150, "y": y + 2, "width": 56, "align": "right", "size": 1, "color": MUTE})
        y += 26
    return {"play_sound": 0, "items": items[:6]}


def card_tools(p):
    v = p["velocity"]
    top = list(v["top_tools"].items())
    top_name, top_n = (top[0] if top else ("n/a", 0))
    return {
        "play_sound": 0,
        "items": [
            {"type": "text", "text": "Top Tool", "x": 0, "y": 6, "width": 220, "align": "center", "size": 2, "color": BLUE},
            {"type": "text", "text": top_name, "x": 0, "y": 32, "width": 220, "align": "center", "size": fit_size(top_name, 220, max_size=3), "color": ACCENT},
            {"type": "text", "text": f"{top_n} calls", "x": 0, "y": 68, "width": 110, "align": "center", "size": 1, "color": MUTE},
            {"type": "text", "text": f"{v['edits']} edits", "x": 110, "y": 68, "width": 110, "align": "center", "size": 1, "color": GREEN},
        ],
    }


CARDS = [card_archetype, card_rhythm, card_model, card_tokens, card_style, card_projects, card_tools]


# --------------------------------------------------------------------------- #
# Device send (mirrors on-stop-done.py)
# --------------------------------------------------------------------------- #
def load_device():
    if not os.path.exists(CONFIG_PATH):
        return None
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    devices = cfg.get("devices", [])
    if not devices:
        return None
    default_id = cfg.get("default_device_id", devices[0].get("device_id"))
    dev = next((d for d in devices if d["device_id"] == default_id), devices[0])
    return dev["last_known_ip"], dev["device_id"]


def send_to_lcd(ip, device_id, payload):
    req = urllib.request.Request(
        f"http://{ip}:{LCD_PORT}/lcd",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Device-ID": device_id},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=3)


def display(profile, once=False):
    dev = load_device()
    if not dev:
        print("No paired display. Run 'pair my display' first.", file=sys.stderr)
        return 1
    ip, device_id = dev
    cards = CARDS[:1] if once else CARDS
    for i, builder in enumerate(cards):
        try:
            send_to_lcd(ip, device_id, builder(profile))
        except Exception as e:
            print(f"send failed: {e}", file=sys.stderr)
            return 1
        if i < len(cards) - 1:
            time.sleep(CARD_DELAY)
    return 0


def display_card(profile, index):
    """Send exactly one card (by rotation index). Used by the daemon."""
    dev = load_device()
    if not dev:
        return 1
    ip, device_id = dev
    builder = CARDS[index % len(CARDS)]
    try:
        send_to_lcd(ip, device_id, builder(profile))
    except Exception as e:
        print(f"send failed: {e}", file=sys.stderr)
        return 1
    return 0


# --------------------------------------------------------------------------- #
# Cached profile (avoid re-scanning every transcript on each daemon tick)
# --------------------------------------------------------------------------- #
def get_profile(force=False):
    if not force and os.path.exists(CACHE_PATH):
        try:
            age = time.time() - os.path.getmtime(CACHE_PATH)
            if age < CACHE_TTL:
                with open(CACHE_PATH) as f:
                    return json.load(f)
        except Exception:
            pass
    profile = analyze()
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(profile, f)
        os.chmod(CACHE_PATH, 0o600)
    except Exception:
        pass
    return profile


# --------------------------------------------------------------------------- #
def render_text(p):
    s = p["span"]
    a = p["activity"]
    lines = [
        f"  Archetype : {p['archetype']}",
        f"  Streak    : {s['streak']}d  ({s['active_days']} active days)",
        f"  Peak hour : {fmt_hour(a['peak_hour'])}",
        f"  Sessions  : {a['sessions']}   Prompts: {a['prompts']}",
        f"  Top model : {p['models']['top']}",
        f"  Tokens    : {fmt_tokens(p['tokens']['output'])} out, "
        f"{p['tokens']['cache_hit_pct']}% cache hit",
        f"  Style     : {p['steering']['avg_prompt_words']} words/prompt, "
        f"{p['velocity']['avg_tools_per_turn']} tools/turn",
        f"  Projects  : " + ", ".join(p["top_projects"].keys()),
    ]
    return "Builder Profile (local)\n" + "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Local Claude Code builder insights")
    ap.add_argument("--json", action="store_true", help="dump full profile as JSON")
    ap.add_argument("--display", action="store_true", help="rotate cards on paired display")
    ap.add_argument("--once", action="store_true", help="with --display, send only the first card")
    ap.add_argument("--card", type=int, metavar="N", help="send only card N (mod rotation length)")
    ap.add_argument("--fresh", action="store_true", help="force a recompute, ignore cache")
    args = ap.parse_args()

    profile = analyze() if args.fresh else get_profile(force=args.fresh)

    if args.card is not None:
        return display_card(profile, args.card)
    if args.display:
        return display(profile, once=args.once)
    if args.json:
        print(json.dumps(profile, indent=2))
    else:
        print(render_text(profile))
    return 0


if __name__ == "__main__":
    sys.exit(main())
