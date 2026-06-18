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

When Claude **needs your approval** to run something (a yes/no prompt) or your
input has been **left idle**, the display pings you with a different buzzer
(`triple_ping`) than the Task Done sound — so you'll notice even if you've
wandered off to your phone. The card shows **`Approve?`** with the tool name, or
**`Your turn`** when it's just waiting for you to type.

## Turning notifications on/off

You don't always want a sound. Just ask Claude in plain language and it updates
the config for you (takes effect immediately, no restart):

- "mute the display" / "im lặng đi" — keep the cards, silence the buzzer
- "stop the task done notification" — no more *Task Done* card
- "stop pinging me for approval" — no more *Approve?/Your turn* ping
- "turn everything back on" — re-enable all

Or edit `~/.config/autonomous-lcd.json` by hand (all default `true`):

```json
{
  "sounds_enabled": true,
  "task_done_enabled": true,
  "notify_enabled": true
}
```

- `sounds_enabled: false` → cards still show, but silently
- `task_done_enabled: false` → no "Task Done" card (usage alerts still fire)
- `notify_enabled: false` → no waiting-on-you ping

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

## Update the plugin

```bash
claude plugins update vibe-desk-display@vibe-desk-display
```

Restart Claude Code after updating.

---

## Uninstall

```bash
claude plugins uninstall vibe-desk-display
```
