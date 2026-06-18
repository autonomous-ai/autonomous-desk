#!/usr/bin/env python3
"""Local Claude Code builder-insights engine.

Reads your local Claude Code session transcripts (~/.claude/projects/**/*.jsonl)
and derives a "builder profile" — peak coding hour, archetype, top model, token
economy, steering style, parallelization and velocity — entirely on-device.

Inspired by Paxel (paxel.ycombinator.com), but privacy-first: nothing leaves the
machine. Use `--json` to dump the computed profile, or `--display` to rotate the
insight cards onto a paired Thinking Desk display.

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
# polite prompts — "thanks", "thank you", "thx", "ty", "cảm ơn"
THANKS_RE = re.compile(
    r"\b(thanks|thank you|thank u|thx|tysm|cz\b|cam on|cảm ơn)\b|\bty\b",
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
        "thanks": 0,
        "short_prompts": 0,      # prompts under 10 words (concise-ness)
    }
    models = Counter()
    tools = Counter()
    by_project = Counter()
    hours = Counter()          # local hour-of-day -> prompt count
    active_days = set()        # local date strings
    phrases = Counter()        # normalized short prompts -> count (go-to prompt)
    crash_out = {"text": None, "letters": 0}  # loudest ALL-CAPS rant
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
                        if len(words) < 10:
                            stats["short_prompts"] += 1
                        if CORRECTION_RE.match(content) and len(words) <= 12:
                            stats["corrections"] += 1
                        if THANKS_RE.search(content):
                            stats["thanks"] += 1
                        # go-to prompt: repeated short phrases (2..6 words)
                        if 2 <= len(words) <= 6:
                            phrases[" ".join(content.lower().split())] += 1
                        # crash out: a short, mostly-UPPERCASE rant (not pasted config/code)
                        stripped = " ".join(content.split())
                        if (3 <= len(words) <= 20 and len(stripped) <= 120
                                and not any(ch in stripped for ch in "=/{};_<>|")):
                            letters = [c for c in stripped if c.isalpha()]
                            if len(letters) >= 8:
                                upper = sum(1 for c in letters if c.isupper())
                                if upper / len(letters) >= 0.7 and len(letters) > crash_out["letters"]:
                                    crash_out = {"text": stripped, "letters": len(letters)}
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

    return _derive(stats, models, tools, by_project, hours, active_days,
                   phrases, crash_out, first_ts, last_ts)


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


def _derive(stats, models, tools, by_project, hours, active_days,
            phrases, crash_out, first_ts, last_ts):
    prompts = max(stats["user_prompts"], 1)
    turns = max(stats["assistant_turns"], 1)
    peak_hour = hours.most_common(1)[0][0] if hours else None
    total_cache = stats["tok_cache_read"] + stats["tok_cache_creation"] + stats["tok_input"]
    cache_hit = (stats["tok_cache_read"] / total_cache * 100) if total_cache else 0
    corr_ratio = stats["corrections"] / prompts
    avg_tools = stats["tool_calls"] / turns
    avg_words = stats["prompt_words"] / prompts
    short_pct = stats["short_prompts"] / prompts * 100

    # go-to prompt: most repeated short phrase (must recur at least twice)
    goto = next(((p, n) for p, n in phrases.most_common(20) if n >= 2), (None, 0))

    top_model = models.most_common(1)[0][0] if models else "n/a"
    model_total = sum(models.values()) or 1
    top_model_pct = (models.most_common(1)[0][1] / model_total * 100) if models else 0
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
            "top_pct": round(top_model_pct, 1),
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
            "short_prompt_pct": round(short_pct, 1),
        },
        "habits": {
            "goto_prompt": goto[0],
            "goto_count": goto[1],
            "thanks": stats["thanks"],
            "crash_out": crash_out["text"],
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


# The device font is PROPORTIONAL and renders wider than a naive 6px/char — in
# practice ~7px per character at size 1, scaling with the size multiplier. The
# content viewport is 220px wide, so size text against a conservative budget and
# keep big titles short (≤ ~8 chars) to avoid clipping at the screen edge.
CHAR_W = 7
NOTIFY_SOUND = 2  # lift_chime — gentle reveal cue on the first (archetype) card


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
RED = "#c0392b"


def _card(title, content, sub, c_color=ACCENT, c_max=3, sound=0):
    """Standard 3-line card: short title, auto-fit headline, small footnote.

    Headline is sized against a conservative 185px budget; if even size 1 is too
    wide it gets ellipsized. Sub line is trimmed to fit at size 1.
    """
    size = fit_size(content, 185, c_max)
    return {
        "play_sound": sound,
        "items": [
            {"type": "text", "text": ellipsize(title, 210, 2), "x": 0, "y": 8, "width": 220, "align": "center", "size": fit_size(title, 200, 2), "color": BLUE},
            {"type": "text", "text": ellipsize(content, 200, size), "x": 0, "y": 36, "width": 220, "align": "center", "size": size, "color": c_color},
            {"type": "text", "text": ellipsize(sub, 210, 1), "x": 0, "y": 80, "width": 220, "align": "center", "size": 1, "color": MUTE},
        ],
    }


def _owl_label(h):
    if h is None:
        return "builder"
    if h >= 22 or h <= 4:
        return "Night owl"
    if 5 <= h <= 8:
        return "Early bird"
    if 9 <= h <= 11:
        return "Morning"
    if 12 <= h <= 17:
        return "Afternoon"
    return "Evening"


def build_cards(p):
    """Return the rotation of card payloads, derived from the live profile.

    Always shows the 5 stable cards; appends the go-to-prompt and crash-out
    cards only when there's real data for them (no blank cards)."""
    span, act, hab = p["span"], p["activity"], p.get("habits", {})
    cards = []

    # 1. Archetype (first card carries the reveal sound)
    cards.append(_card(
        "You are", p["archetype"],
        f"{span['streak']}d streak · {span['active_days']} days",
        ACCENT, 3, sound=NOTIFY_SOUND))

    # 2. Peak hour
    cards.append(_card(
        "Peak hour", fmt_hour(act["peak_hour"]),
        f"{_owl_label(act['peak_hour'])} · {act['sessions']} sess",
        CREAM, 4))

    # 3. Top model
    cards.append(_card(
        "Top model", p["models"]["top"],
        f"{int(p['models']['top_pct'])}% of turns", ACCENT, 3))

    # 4. Prompt style (dynamic: detailed vs concise)
    s = p["steering"]
    if s["avg_prompt_words"] >= 40:
        cards.append(_card("Your style", "Detailed",
                           f"~{int(s['avg_prompt_words'])} words/prompt", CREAM, 3))
    else:
        cards.append(_card("Your style", "Concise",
                           f"{int(s['short_prompt_pct'])}% under 10 words", CREAM, 3))

    # 5. Manners (thanks count — always available, even if 0)
    thanks = hab.get("thanks", 0)
    polite_sub = "robots remember you" if thanks >= 10 else \
                 ("a quiet nod" if thanks else "straight to business")
    cards.append(_card("Manners", f"{thanks} thanks", polite_sub, GREEN, 3))

    # 6. Go-to prompt (only if a phrase recurs)
    if hab.get("goto_prompt"):
        cards.append(_card("Most used", f'"{hab["goto_prompt"]}"',
                           f"{hab['goto_count']}× across sessions", ACCENT, 2))

    # 7. Crash out (only if a loud ALL-CAPS rant exists)
    if hab.get("crash_out"):
        cards.append(_card("Crash out", hab["crash_out"],
                           "caps lock engaged", RED, 1))

    return cards


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
    cards = build_cards(profile)
    if once:
        cards = cards[:1]
    for i, payload in enumerate(cards):
        try:
            send_to_lcd(ip, device_id, payload)
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
    cards = build_cards(profile)
    if not cards:
        return 1
    try:
        send_to_lcd(ip, device_id, cards[index % len(cards)])
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
    hab = p.get("habits", {})
    if hab.get("goto_prompt"):
        lines.append(f"  Go-to     : \"{hab['goto_prompt']}\" ({hab['goto_count']}x)")
    lines.append(f"  Manners   : {hab.get('thanks', 0)} thanks")
    if hab.get("crash_out"):
        lines.append(f"  Crash out : {hab['crash_out']}")
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
