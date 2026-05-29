---
name: vibe-desk-display
description: >
  Interact with the user's desk display device (VibeDesk) over LAN.
  Supports pairing, sending notifications with plain text,
  rich layout (positioned text, shapes, progress bars), and buzzer sounds.
  Sends task-done notification + usage data when Claude completes a task.
  Triggers: "pair my display", "show on my screen", "notify my display",
  "ping my display when done", "send to my screen",
  "show my usage on display", "unpair my display".
allowed-tools: Bash(*)
---

# Vibe Desk Display Skill

Discover, pair, and send notifications to a VibeDesk display on the local network.
After pairing, Claude proactively sends a task-done notification + usage data when completing a task.

## Config

Path: `~/.config/autonomous-lcd.json`

```json
{
  "devices": [
    {
      "device_id": "lcd-bd4a14",
      "label": "My Display",
      "last_known_ip": "192.168.1.42",
      "last_seen_at": "2026-05-18T10:30:00Z"
    }
  ],
  "default_device_id": "lcd-bd4a14"
}
```

Device ID format: `lcd-<6 lowercase hex digits>` (from last 3 bytes of MAC address).

---

## 1. Discover

Find devices on the LAN using the bundled discovery script.

**When to use:** during pairing, or when a notification fails with connection error/timeout.

### Run discovery

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/discover.py
```

**Output:** JSON array of found devices, e.g.:
```json
[{"device_id": "lcd-bd4a14", "ip": "192.168.1.42"}]
```

**How it works (automatic):**
1. Cache check — tries cached IPs from config (instant)
2. Parallel scan — runs mDNS browse + UDP subnet sweep simultaneously (~10s)
3. Returns all found devices, deduplicated by device_id

**On failure:** exits with code 1, stderr contains `{"error": "not_found"}`. Suggest: device powered on? Same WiFi?

---

## 2. Pair

One-time setup to register a new device. Uses OTP code displayed on the device screen — no need to read device ID stickers.

**When to use:** "pair my display", "add a screen", "set up device".

### User-facing messages

Only show simple, non-technical messages to the user during pairing:

1. "Scanning your network..." (while discovery runs)
2. "Found N device(s). Check your display for a pairing code." (after discovery)
3. "What code do you see on your device?" (ask user)
4. "Paired successfully! Your display should now show a confirmation." (after done)

**Do NOT show** to user: device IDs, IP addresses, config paths, HTTP status codes, raw JSON, error tracebacks, or internal debug info. These are implementation details.

**Bash output:** All bash commands in the pair flow should redirect stdout to `/dev/null` or use a wrapper that only prints a single friendly message (e.g. `"done"` or `"ok"`). Never let raw JSON, device IDs, or HTTP responses appear in the transcript. Pipe discovery output into a variable and process silently within the same script.

### Procedure

1. Tell user: **"Scanning your network..."**
2. Run discovery (section 1) to find **all** devices on the network.
3. If no devices found → tell user: "No devices found. Make sure your display is powered on and connected to the same WiFi."
4. Tell user: **"Found N device(s). Check your display for a pairing code."**
5. For each discovered device, generate a random **4-digit code** (1000–9999, unique per device).
6. Send each device its code as a notification (silently, don't show HTTP results to user):
   ```json
   {
     "play_sound": 20,
     "items": [
       { "type": "text", "text": "Pairing", "x": 0, "y": 0, "width": 220, "align": "center", "size": 3, "color": "#7eb8da" },
       { "type": "text", "text": "<CODE>", "x": 0, "y": 35, "width": 220, "align": "center", "size": 4, "color": "#e8dcc8" },
       { "type": "text", "text": "Enter this code", "x": 0, "y": 85, "width": 220, "align": "center", "size": 2, "color": "#9a9488" }
     ]
   }
   ```
   Skip devices that fail to respond — don't mention them to the user.
7. Ask user: **"What code do you see on your device?"** — match input to a device.
8. Label defaults to **"My Display"** (skip asking).
9. Write to `~/.config/autonomous-lcd.json`:
   - New device → append to `devices[]`
   - Existing device ID → update entry
   - First device → set as `default_device_id`
   - Set file permission `0600`
10. Send confirmation notification: `{"text": "Paired with Claude", "color": "green", "play_sound": 20}`
11. Tell user: **"Paired successfully! Your display should now show a confirmation."**

Re-pairing same device ID is an update, not an error.

---

## 3. Unpair

Remove a device.

**When to use:** "unpair my display", "remove my display", "stop display updates".

### Procedure

1. Identify which device to unpair (default if not specified).
2. Remove device from `~/.config/autonomous-lcd.json`.
3. If removed device was `default_device_id`, clear it (or set to next device if any remain).
4. Report success.

---

## 4. Notify

Send a notification to a paired device. This is the most frequently used operation.

**When to use:** "show on my screen", "notify my display", "ping my display when done". Also use proactively at end of long tasks (build, test, deploy).

### 4.1 Pick device

- Use device ID the user specified, OR
- Use `default_device_id` from config, OR
- Error if neither available. If no config or no devices → tell user to pair first.

### 4.2 Build payload

**Legacy text mode** — simple notification:

```json
{
  "text": "Build passed in 3m 12s",
  "size": 2,
  "color": "green",
  "play_sound": 20
}
```

- `text` (required) — max 500 chars, strip markdown to plain text
- `size` (optional) — 1 to 4, default 2
- `color` (optional) — `red`, `green`, `blue`, `yellow`, `white`, or hex `#RRGGBB`
- `play_sound` — always include **20** (`claude_style`) unless user specifies otherwise

**Rich layout mode** — positioned items:

```json
{
  "play_sound": 20,
  "items": [
    { "type": "text", "text": "Title", "x": 12, "y": 0, "width": 196, "size": 4, "color": "#ffffff" },
    { "type": "rect", "x": 6, "y": 34, "width": 208, "height": 72, "radius": 10, "color": "#171d18" },
    { "type": "progress", "x": 18, "y": 78, "width": 184, "height": 14, "radius": 4, "value": 50, "color": "#9bad67", "bg_color": "#2f2f2f" }
  ]
}
```

When `items[]` has at least one valid item, rich layout is used and `text` is ignored.

**Coordinate system:**
- Viewport: **220 x 117** pixels (inner content area, not full 240x135 screen)
- Origin `(0, 0)` = top-left of content area
- Last usable point: `(219, 116)`

**Limits:**
- Max **6** items (extra ignored)
- Item text max **95** chars
- `value`: 0..100, `radius`: 0..50, `stroke_width`: 1..32

### 4.3 Send

```python
import json, urllib.request

payload = json.dumps(<json_payload>).encode()
req = urllib.request.Request(
    "http://<last_known_ip>:3000/lcd",
    data=payload,
    headers={
        "Content-Type": "application/json",
        "X-Device-ID": "<device_id>",
    },
    method="POST",
)
with urllib.request.urlopen(req, timeout=3) as resp:
    print(f"HTTP {resp.status}")
    print(resp.read().decode())
```

### 4.4 Handle response

| Status | Action |
|--------|--------|
| **200** | Success. Update `last_seen_at` in config. |
| **400** | Malformed payload. Check JSON. |
| **403** | Device ID mismatch. Run rediscovery. |
| **413** | Text >500 chars. Truncate to 497 + `"..."`, retry once. |
| **Connection error/timeout** | Cached IP stale. Run rediscovery (section 1), retry once. |

### 4.5 Dry run

If user asks for dry run, show the payload and target URL without sending.

---

## 5. Task Done Notification

Handled automatically by the `Stop` hook (`scripts/on-stop-done.py`). Every time Claude finishes a response, the hook:

1. Sends a "Task Done" notification with sound #20.
2. Fetches current usage from the API.
3. If **either** 5-hour or 7-day utilization `>=` the configured threshold → sends usage section 1 (5-hour) after 5s, then usage section 2 (7-day) after another 5s.
4. If both are below threshold → stops after Task Done.

Rate-limited to once per 60 seconds. No action needed from Claude — the hook runs automatically.

### Config: `usage_threshold`

Set `usage_threshold` (integer, 0–100) in `~/.config/autonomous-lcd.json` to control when usage is shown after Task Done. Default: **80**.

```json
{
  "devices": [...],
  "default_device_id": "...",
  "usage_threshold": 80
}
```

---

## 6. Usage Monitor (One-Shot)

Fetch real usage data from the Claude Code API and display immediately. Used by the `/vibe-desk-display:usage` slash command or as part of the Task Done flow (section 5).

**When to use:** "show my usage on display", "update usage now", "refresh display".

### 6.1 Get OAuth token

```python
import json, os, subprocess

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
            capture_output=True, text=True
        )
        if kc.returncode == 0:
            data = json.loads(kc.stdout.strip())
            for v in _find_strings(data):
                if v.startswith("sk-ant-oat"):
                    return v
    except Exception:
        pass
    return None
```

### 6.2 Fetch usage

```python
import urllib.request
from datetime import datetime, timezone

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
```

### 6.3 Build and send

```python
token = get_token()
usage = fetch_usage(token)
pct_5h = int(usage["five_hour"]["utilization"])
pct_7d = int(usage["seven_day"]["utilization"])
reset_5h = time_left(usage["five_hour"]["resets_at"])
reset_7d = time_left(usage["seven_day"]["resets_at"])
```

**Section 1 — Header + Current (5-hour):**

```json
{
  "play_sound": 20,
  "items": [
    { "type": "text", "text": "Usage", "x": 0, "y": 5, "width": 220, "align": "center", "size": 4, "color": "#d4845a" },
    { "type": "text", "text": "<pct_5h>%", "x": 18, "y": 38, "width": 100, "size": 4, "color": "<progress_color>" },
    { "type": "text", "text": "Current", "x": 100, "y": 46, "width": 105, "align": "right", "size": 1, "color": "#7eb8da" },
    { "type": "progress", "x": 18, "y": 70, "width": 184, "height": 12, "radius": 6, "value": <pct_5h>, "color": "<progress_color>", "bg_color": "#3a3a3a" },
    { "type": "text", "text": "Resets in <reset_5h>", "x": 18, "y": 90, "width": 180, "size": 1, "color": "#e8dcc8" }
  ]
}
```

**Section 2 — Weekly (7-day) + status:**

```json
{
  "play_sound": 20,
  "items": [
    { "type": "text", "text": "<pct_7d>%", "x": 18, "y": 10, "width": 100, "size": 4, "color": "#e8dcc8" },
    { "type": "text", "text": "Weekly", "x": 100, "y": 18, "width": 105, "align": "right", "size": 1, "color": "#a09888" },
    { "type": "progress", "x": 18, "y": 45, "width": 184, "height": 12, "radius": 6, "value": <pct_7d>, "color": "<progress_color>", "bg_color": "#3a3a3a" },
    { "type": "text", "text": "Resets in <reset_7d>", "x": 18, "y": 63, "width": 180, "size": 1, "color": "#9a9488" },
    { "type": "text", "text": "* Baking...", "x": 0, "y": 87, "width": 220, "align": "center", "size": 2, "color": "#d4845a" }
  ]
}
```

Send section 1 first (with `play_sound: 20`), wait 5 seconds, then send section 2 (with `play_sound: 0`).

Progress bar color: green `#6b8f4e` (<60%), orange `#d4845a` (60-79%), red `#c0392b` (≥80%).

**Rate limit:** The usage API rate-limits hard. Do NOT poll faster than once per minute.

---

## 7. Rich Layout Reference

### Item types

**text** — Render text at position

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `text` | string | *(required)* | Text content (max 95 chars) |
| `size` | int 1-4 | 2 | Font size |
| `align` | string | `left` | `left`, `center`, `right` |
| `width` | int | 0 | Layout width (0 = remaining) |
| `color` | string | `blue` | Text color |

**rect** — Rectangle or rounded rectangle

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `width` | int | *(required)* | Width |
| `height` | int | *(required)* | Height |
| `radius` | int | 0 | Corner radius |
| `filled` | bool | true | Fill or outline |

**progress** — Progress bar

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `width` | int | *(required)* | Width |
| `height` | int | *(required)* | Height |
| `value` | int 0-100 | *(required)* | Percentage |
| `radius` | int | 0 | Corner radius |
| `bg_color` | string | `#303030` | Track color |

**line** — Line between two points

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `x2` | int | *(required)* | End X |
| `y2` | int | *(required)* | End Y |
| `stroke_width` | int | 1 | Thickness |

**circle** — Circle (set width = height)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `width` | int | *(required)* | Diameter |
| `height` | int | *(required)* | = width |
| `filled` | bool | true | Fill or outline |

**ellipse** — Same fields as circle, different width/height.

**arc** — Arc stroke over angle range

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `width` | int | *(required)* | Bounding width |
| `height` | int | *(required)* | Bounding height |
| `start_angle` | int | 0 | Start angle |
| `end_angle` | int | 360 | End angle |
| `stroke_width` | int | 1 | Arc thickness |

**triangle** — Triangle from 3 points

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `x2` | int | *(required)* | Point 2 X |
| `y2` | int | *(required)* | Point 2 Y |
| `x3` | int | *(required)* | Point 3 X |
| `y3` | int | *(required)* | Point 3 Y |
| `filled` | bool | true | Fill or outline |

**polygon** — Polygon from point list

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `points` | string | *(required)* | `x1,y1; x2,y2; x3,y3 ...` (max 95 chars) |
| `filled` | bool | true | Fill or outline |

**ring** — Circular outline over angle range

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `width` | int | *(required)* | Bounding width |
| `height` | int | *(required)* | Bounding height |
| `start_angle` | int | 0 | Start angle |
| `end_angle` | int | 360 | End angle (360 = full ring) |
| `stroke_width` | int | 1 | Ring thickness |

**pie** — Filled wedge shape

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `width` | int | *(required)* | Bounding width |
| `height` | int | *(required)* | Bounding height |
| `start_angle` | int | 0 | Start angle |
| `end_angle` | int | 360 | End angle |

### Common fields (all item types)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `type` | string | `text` | Item type |
| `x` | int | 0 | X position in viewport |
| `y` | int | 0 | Y position in viewport |
| `color` | string | root `color` | Item color |
| `bg_color` | string | `#303030` | Background (progress) |

---

## 8. Buzzer Sound Presets

`play_sound` can be included in any request (both legacy and rich mode). Plays once when payload is accepted. Requires `text` or `items` — cannot be sent standalone.

| Index | Name | Style |
|-------|------|-------|
| 0 | *(muted)* | Sound off |
| 1 | `triple_ping` | Sharp high triple ping |
| 2 | `lift_chime` | Smooth rising chime |
| 3 | `bright_fanfare` | Bright success fanfare |
| 4 | `micro_success` | Short positive triad |
| 5 | `soft_drop` | Soft descending confirmation |
| 6 | `double_tick` | Quick double tick and resolve |
| 7 | `alert_fall` | Short alert drop |
| 8 | `clean_pop` | Modern light popup sound |
| 9 | `confirm_arc` | Rising confirm arc |
| 10 | `status_ready` | Compact ready cue |
| 11 | `soft_descend` | Calm descending tone |
| 12 | `gentle_open` | Friendly open cue |
| 13 | `focus_ping` | Clean focused ping |
| 14 | `tap_rise` | Tap then rise |
| 15 | `resolve_down` | Downward resolve |
| 16 | `signal_up` | Fast upward signal |
| 17 | `digital_bloom` | Slightly synthetic bloom |
| 18 | `notify_peak` | Peak notification tone |
| 19 | `warning_soft` | Soft warning fall |
| 20 | `claude_style` | Crisp bright code-style notification |

Default notification sound: **20** (`claude_style`).

---

## 9. Tested Examples

Copy-paste ready payloads for quick testing.

### Example 1 — Header + Current (5-hour usage)

```json
{
  "play_sound": 20,
  "items": [
    { "type": "text", "text": "Usage", "x": 0, "y": 5, "width": 220, "align": "center", "size": 4, "color": "#d4845a" },
    { "type": "text", "text": "41%", "x": 18, "y": 38, "width": 100, "size": 4, "color": "#6b8f4e" },
    { "type": "text", "text": "Current", "x": 100, "y": 46, "width": 105, "align": "right", "size": 1, "color": "#7eb8da" },
    { "type": "progress", "x": 18, "y": 70, "width": 184, "height": 12, "radius": 6, "value": 41, "color": "#6b8f4e", "bg_color": "#3a3a3a" },
    { "type": "text", "text": "Resets in 1h 56m", "x": 18, "y": 90, "width": 180, "size": 1, "color": "#e8dcc8" }
  ]
}
```

### Example 2 — Weekly (7-day usage) + status

```json
{
  "play_sound": 20,
  "items": [
    { "type": "text", "text": "48%", "x": 18, "y": 10, "width": 100, "size": 4, "color": "#e8dcc8" },
    { "type": "text", "text": "Weekly", "x": 100, "y": 18, "width": 105, "align": "right", "size": 1, "color": "#a09888" },
    { "type": "progress", "x": 18, "y": 45, "width": 184, "height": 12, "radius": 6, "value": 48, "color": "#6b8f4e", "bg_color": "#3a3a3a" },
    { "type": "text", "text": "Resets in 1d 11h", "x": 18, "y": 63, "width": 180, "size": 1, "color": "#9a9488" },
    { "type": "text", "text": "* Baking...", "x": 0, "y": 87, "width": 220, "align": "center", "size": 2, "color": "#d4845a" }
  ]
}
```

### Example 3 — Simple text notification

```json
{
  "text": "Build passed in 3m 12s",
  "size": 2,
  "color": "green",
  "play_sound": 20
}
```

### Example 4 — Shape demo

```json
{
  "play_sound": 20,
  "items": [
    { "type": "circle", "x": 10, "y": 12, "width": 28, "height": 28, "color": "#7cb342", "filled": true },
    { "type": "ellipse", "x": 52, "y": 10, "width": 48, "height": 30, "color": "#ffffff", "filled": false, "stroke_width": 2 },
    { "type": "line", "x": 8, "y": 64, "x2": 206, "y2": 64, "color": "#4fc3f7", "stroke_width": 3 },
    { "type": "arc", "x": 118, "y": 10, "width": 38, "height": 38, "color": "#ffb300", "stroke_width": 4, "start_angle": 0, "end_angle": 270 },
    { "type": "triangle", "x": 22, "y": 84, "x2": 44, "y2": 112, "x3": 4, "y3": 112, "color": "#ef5350", "filled": true },
    { "type": "pie", "x": 166, "y": 82, "width": 36, "height": 36, "color": "#66bb6a", "start_angle": 0, "end_angle": 120 }
  ]
}
```

---

## Important

- V1: no authentication — only `X-Device-ID` header required (no `X-Token`).
- Always include `"play_sound": 20` unless user specifies otherwise.
- Never print or log device tokens.
- Config file permission should be `0600`.
- If cached IP is stale, run rediscovery automatically.
- Never scan a subnet larger than /22 without user confirmation.
