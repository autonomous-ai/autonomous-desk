# Thinking Desk Display — Setup Guide

Turn your Thinking Desk into a live Claude Code usage monitor.

---

## What you need

- A Thinking Desk device, set up via the mobile app
- Your computer and Thinking Desk on the same WiFi network
- Claude Code (with OAuth login, not API key)

---

## Install

Open your terminal and run:

```bash
claude plugins marketplace add https://github.com/autonomous-ai/autonomous-desk
```

```bash
claude plugins install vibe-desk-display
```

Then **restart Claude Code** (exit and reopen).

---

## Pair your device

1. Make sure your Thinking Desk is set up and connected to the same WiFi as your computer
2. Open Claude Code and type:

```
pair my display
```

3. Claude will scan your network and find the device
4. A **4-digit code** will appear on the display screen
5. Type that code into Claude Code

That's it — your device is paired.

> **Update your firmware.** After connecting your desk, open the Thinking Desk mobile app and update the firmware to the latest version — this ensures the display renders notifications correctly.

---

## What happens next

Once paired, the display automatically shows a **"Task Done"** notification whenever Claude completes a task. If your usage is **≥ 80%** (5-hour or 7-day), it will also show your current usage stats right after.

You can change the threshold just by asking Claude in plain language:

- "warn me earlier" / "show my usage sooner"
- "set my warning threshold to 60"
- "only warn me near the limit"

Claude updates the config for you. Or edit `~/.config/autonomous-lcd.json` by hand:

```json
{
  "usage_threshold": 80
}
```

Set it lower (e.g. `60`) to see usage more often, or higher (e.g. `90`) to only get alerted when critical.

You can also:

- Say `notify my display` to send a custom message to the screen
- Type `/vibe-desk-display:usage` to refresh the usage display immediately
- Say `unpair my display` to disconnect the device

---

## Waiting-on-you ping

When Claude **needs your approval** to run something (a yes/no prompt, or an
MCP form), the display pings you with a different buzzer (`triple_ping`) than
the Task Done sound — so you'll notice even if you've wandered off to your
phone. The card shows **`CLAUDE NEEDS YOU`** with **`Check your terminal`**, so
you know to go back and respond.

It deliberately stays quiet for Claude Code's plain "idle, waiting for your next
prompt" notice — that isn't asking you for anything, so it shouldn't light up
the display.

## Turning notifications on/off

You don't always want a sound. Just ask Claude in plain language and it updates
the config for you (takes effect immediately, no restart):

- "mute the display" — keep the cards, silence the buzzer
- "stop the task done notification" — no more *Task Done* card
- "stop pinging me for approval" — no more *Claude needs you* ping
- "turn everything back on" — re-enable all

Or edit `~/.config/autonomous-lcd.json` by hand (all default `true`):

```json
{
  "sounds_enabled": true,
  "task_done_enabled": true,
  "notify_enabled": true,
  "update_check_enabled": true,
  "device_warning_enabled": true
}
```

- `sounds_enabled: false` → cards still show, but silently
- `task_done_enabled: false` → no "Task Done" card (usage alerts still fire)
- `notify_enabled: false` → no waiting-on-you ping
- `update_check_enabled: false` → no "Update available" card
- `device_warning_enabled: false` → no in-Claude warning when the display is unreachable

> **Update available card.** When a newer plugin version is published, the
> display shows a silent **`UPDATE AVAILABLE`** card after a task completes —
> at most once a day, and it disappears once you update. It checks GitHub at
> most once every 24 hours.

---

## Builder insights

Beyond live usage, the display can show your **builder profile** — derived from
your local Claude Code session history. It runs entirely on your machine;
nothing is uploaded.

Type:

```
/vibe-desk-display:insights
```

or just ask "show my builder profile". The display rotates through a set of cards:

- **Archetype** — e.g. *The Architect*, *Night Owl*, *Velocity Machine* — plus your day streak
- **Rhythm** — your peak coding hour, session and prompt counts
- **Top model** — the model you use most, plus total tool calls
- **Token economy** — output tokens and cache-hit rate
- **Builder style** — words per prompt, tools per turn, course-correct rate
- **Top projects** and **Top tool**

Once paired, one insight card is also folded into the regular usage refresh, so
the display gently cycles through your profile over time. To turn this off and
keep the ambient display usage-only, set `"show_insights": false` in
`~/.config/autonomous-lcd.json` (default is `true`).

---

## If the display goes quiet

The plugin remembers your display's IP address. If your router later hands the
device a **different IP** (common after a reboot or rejoining Wi-Fi), the hooks
notice the saved address is dead, **rescan your network**, update the saved
address, and retry — so it usually heals itself within a task or two.

If it still can't find the device, you'll see a warning **inside Claude**:

> ⚠️ Couldn't reach My Display on your network — it may be offline or on another Wi-Fi. Re-pair with "pair my display" if it moved.

When that happens, check that the display is powered on and on the **same Wi-Fi**
as your computer, then run `pair my display` again. To silence the warning, set
`"device_warning_enabled": false` in `~/.config/autonomous-lcd.json`.

---

## Update the plugin

Restarting Claude Code does **not** update the plugin on its own. There are two ways to get new versions.

### Option A — Auto-update (set once, recommended)

Turn it on and every new version installs automatically the next time you launch Claude Code:

```
/plugin
```

Go to **Marketplaces → autonomous-desk → Enable auto-update**.

> Auto-update is off by default for community marketplaces like this one, so you have to enable it once. After that you never need to update by hand.

### Option B — Update manually

Pull the latest version right now:

```bash
claude plugins update vibe-desk-display@autonomous-desk
```

Restart Claude Code after updating.

> The reference is `vibe-desk-display@autonomous-desk` — that's `plugin-name@marketplace-name`. To force a marketplace refresh first, run `/plugin marketplace update autonomous-desk`, then update.

---

## Uninstall

```bash
claude plugins uninstall vibe-desk-display
```
