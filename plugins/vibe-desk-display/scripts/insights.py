#!/usr/bin/env python3
"""Local Codex builder-insights engine.

Reads local Codex session transcripts (~/.codex/sessions/**/*.jsonl)
and derives a "builder profile" — peak coding hour, archetype, top model, token
economy, steering style, parallelization and velocity — entirely on-device.

Privacy-first: everything is computed on-device and nothing leaves the machine.
Use `--json` to dump the computed profile, or `--display` to rotate the insight
cards onto a paired Thinking Desk display.

Stdlib only — no pip install.
"""

import argparse
import glob
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone

import device

CODEX_HOME = os.path.expanduser(os.environ.get("CODEX_HOME", "~/.codex"))
SESSIONS_DIR = os.path.join(CODEX_HOME, "sessions")
CACHE_PATH = os.path.join(device.CONFIG_DIR, "autonomous-lcd-codex-insights.json")
INDEX_PATH = os.path.join(device.CONFIG_DIR, "autonomous-lcd-codex-insights.idx")
CACHE_TTL = 3600  # recompute the profile at most once an hour
CARD_DELAY = float(os.environ.get("AUTONOMOUS_LCD_CARD_DELAY", "6"))
# Cold-cache analyze() runs on the 60s Stop hook. Bound the scan so a large
# ~/.codex/sessions tree cannot blow the timeout.
SESSION_MAX_AGE_SECONDS = 90 * 24 * 3600
SESSION_MAX_FILES = 120

EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit", "apply_patch"}
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
    """Yield recent local Codex JSONL session transcripts, newest first.

    A cold cache on the Stop hook must finish inside the 60s timeout, so this
    skips files older than SESSION_MAX_AGE_SECONDS (~90 days) and caps the
    number of files at SESSION_MAX_FILES.
    """
    pattern = os.path.join(SESSIONS_DIR, "**", "*.jsonl")
    cutoff = time.time() - SESSION_MAX_AGE_SECONDS
    ranked = []
    for path in glob.glob(pattern, recursive=True):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime >= cutoff:
            ranked.append((mtime, path))
    ranked.sort(reverse=True)
    for _, path in ranked[:SESSION_MAX_FILES]:
        yield path


def parse_ts(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def project_label(cwd):
    """Turn a session working directory into a short display label."""
    if not cwd:
        return "unknown"
    return (os.path.basename(str(cwd).rstrip(os.sep)) or str(cwd))[:18]


def _record_prompt(content, ts, label, stats, by_project, hours, active_days,
                   phrases, crash_out):
    if not isinstance(content, str) or not content.strip():
        return crash_out
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
    if 2 <= len(words) <= 6:
        phrases[" ".join(content.lower().split())] += 1

    stripped = " ".join(content.split())
    if (3 <= len(words) <= 20 and len(stripped) <= 120
            and not any(ch in stripped for ch in "=/{};_<>|")):
        letters = [char for char in stripped if char.isalpha()]
        if len(letters) >= 8:
            upper = sum(1 for char in letters if char.isupper())
            if upper / len(letters) >= 0.7 and len(letters) > crash_out["letters"]:
                crash_out = {"text": stripped, "letters": len(letters)}
    if ts:
        hours[ts.astimezone().hour] += 1
        active_days.add(ts.astimezone().date().isoformat())
    return crash_out


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

    for path in iter_sessions():
        stats["sessions"] += 1
        label = "unknown"
        latest_usage = None
        tools_in_turn = 0
        try:
            fh = open(path, "r", encoding="utf-8")
        except OSError:
            continue
        with fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                typ = d.get("type")
                payload = d.get("payload") if isinstance(d.get("payload"), dict) else {}
                ts = parse_ts(d.get("timestamp"))
                if ts:
                    if first_ts is None or ts < first_ts:
                        first_ts = ts
                    if last_ts is None or ts > last_ts:
                        last_ts = ts

                if typ == "session_meta":
                    label = project_label(payload.get("cwd"))
                elif typ == "turn_context":
                    if tools_in_turn >= 2:
                        stats["multi_tool_turns"] += 1
                    tools_in_turn = 0
                    stats["assistant_turns"] += 1
                    if payload.get("model"):
                        models[payload["model"]] += 1
                elif typ == "event_msg" and payload.get("type") == "user_message":
                    crash_out = _record_prompt(
                        payload.get("message"), ts, label, stats, by_project,
                        hours, active_days, phrases, crash_out,
                    )
                elif typ == "event_msg" and payload.get("type") == "token_count":
                    latest_usage = (payload.get("info") or {}).get("total_token_usage")
                elif typ == "response_item" and payload.get("type") in {
                    "function_call", "custom_tool_call", "local_shell_call",
                }:
                    name = payload.get("name") or payload.get("tool_name") or payload.get("type")
                    stats["tool_calls"] += 1
                    tools_in_turn += 1
                    tools[name] += 1
                    if name in EDIT_TOOLS:
                        stats["edits"] += 1

        if tools_in_turn >= 2:
            stats["multi_tool_turns"] += 1
        if isinstance(latest_usage, dict):
            stats["tok_input"] += latest_usage.get("input_tokens", 0) or 0
            stats["tok_output"] += latest_usage.get("output_tokens", 0) or 0
            stats["tok_cache_read"] += latest_usage.get("cached_input_tokens", 0) or 0
            stats["tok_cache_creation"] += latest_usage.get("cache_write_input_tokens", 0) or 0

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
    from datetime import date
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
    """Single headline label summarising the builder."""
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
    total_input = stats["tok_input"]
    cache_hit = (stats["tok_cache_read"] / total_input * 100) if total_input else 0
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
    if m.startswith("gpt-"):
        return m.upper().replace("GPT-", "GPT ")
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
    cfg = device.load_config()
    dev = device.get_device(cfg)
    return (cfg, dev) if dev else (cfg, None)


def display(profile, once=False):
    cfg, dev = load_device()
    if not dev:
        print("No paired display. Run 'pair my display' first.", file=sys.stderr)
        return 1
    cards = build_cards(profile)
    if once:
        cards = cards[:1]
    for i, payload in enumerate(cards):
        try:
            if not device.send_with_reconnect(cfg, dev, payload):
                raise OSError("display unreachable")
        except Exception as e:
            print(f"send failed: {e}", file=sys.stderr)
            return 1
        if i < len(cards) - 1:
            time.sleep(CARD_DELAY)
    return 0


def display_card(profile, index):
    """Send exactly one card (by rotation index). Used by the daemon."""
    cfg, dev = load_device()
    if not dev:
        return 1
    cards = build_cards(profile)
    if not cards:
        return 1
    try:
        if not device.send_with_reconnect(cfg, dev, cards[index % len(cards)]):
            raise OSError("display unreachable")
    except Exception as e:
        print(f"send failed: {e}", file=sys.stderr)
        return 1
    return 0


def rotate_one(cfg=None, dev=None):
    """Send the next ambient insight card and advance the private local index."""
    cfg = cfg or device.load_config()
    dev = dev or device.get_device(cfg)
    if not dev or not cfg.get("show_insights", True):
        return 1
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as handle:
            index = int(handle.read().strip())
    except (OSError, TypeError, ValueError):
        index = 0
    cards = build_cards(get_profile())
    if not cards or not device.send_with_reconnect(cfg, dev, cards[index % len(cards)]):
        return 1
    try:
        os.makedirs(device.CONFIG_DIR, mode=0o700, exist_ok=True)
        with open(INDEX_PATH, "w", encoding="utf-8") as handle:
            handle.write(str(index + 1))
        os.chmod(INDEX_PATH, 0o600)
    except OSError:
        pass
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
        device.atomic_write_json(CACHE_PATH, profile)
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
    ap = argparse.ArgumentParser(description="Local Codex builder insights")
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
