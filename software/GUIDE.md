# Vibe Desk Display — Setup Guide

Turn your VibeDesk into a live Claude Code usage monitor.

---

## What you need

- A VibeDesk device, set up via the mobile app
- Your computer and VibeDesk on the same WiFi network
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

1. Make sure your VibeDesk is set up and connected to the same WiFi as your computer
2. Open Claude Code and type:

```
pair my display
```

3. Claude will scan your network and find the device
4. A **4-digit code** will appear on the display screen
5. Type that code into Claude Code

That's it — your device is paired.

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
