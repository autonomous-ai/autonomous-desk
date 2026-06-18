# Autonomous Thinking Desk Display for Claude Code

Turn your [Thinking Desk](https://www.autonomous.ai/standing-desks/autonomous-desk-5-ai) into a live Claude Code companion. Task-done notifications and usage data appear on your desk display — no dashboard, no browser, just a glance.

https://github.com/user-attachments/assets/c036cb38-f9d6-42e8-8b66-5a09e0e77de2

## Quick Start

```bash
claude plugins marketplace add https://github.com/autonomous-ai/autonomous-desk
claude plugins install vibe-desk-display
```

Restart Claude Code, then type `pair my display` and follow the on-screen instructions.

> **After connecting your desk, update the firmware to the latest version** (via the Thinking Desk mobile app) to make sure the display works correctly.

See the full [Setup Guide](GUIDE.md) for details.

## Features

- **Task done + usage display** — when Claude completes a task, shows a "Task Done" notification followed by 5-hour and 7-day usage
- **Waiting-on-you ping** — when Claude needs your approval (yes/no) or your input is idle, the display pings with a distinct buzzer (triple_ping) so you don't miss it while away from the keyboard
- **Builder insights** — analyze your local Claude Code sessions on-device and rotate a builder profile (archetype, peak hour, top model, go-to prompt, style) across the display. Everything is computed locally — nothing leaves your machine
- **Notifications** — send custom messages to the screen ("notify my display when done")
- **OTP pairing** — no sticker reading, just enter the code shown on screen
- **Zero dependencies** — Python 3 stdlib only, no pip install needed

## Commands

| Command | Description |
|---------|-------------|
| `/vibe-desk-display:usage` | Refresh usage display now |
| `/vibe-desk-display:insights` | Analyze local sessions, rotate builder profile on display |
| `/vibe-desk-display:notify` | Send a notification |

Or use natural language: "show my usage on display", "notify my display", "unpair my display"

## Turning notifications on/off

You don't always want the buzzer. Just tell Claude in plain language — it edits `~/.config/autonomous-lcd.json` for you (no restart needed):

- "mute the display" → keep the cards, silence the buzzer
- "stop the task done notification" → no more "Task Done" card
- "stop pinging me for approval" → no more "Approve?/Your turn" ping
- "turn everything back on" → re-enable all

The flags (all default `true`):

| Key | Controls |
|-----|----------|
| `sounds_enabled` | Master buzzer. `false` = cards show silently |
| `task_done_enabled` | The "Task Done" card after each response |
| `notify_enabled` | The waiting-on-you ping (approval / idle) |

## Requirements

- macOS
- Python 3
- A Thinking Desk device on the same WiFi
- Claude Code with OAuth login

## Update / Uninstall

```bash
claude plugins update vibe-desk-display@vibe-desk-display   # pull latest
claude plugins uninstall vibe-desk-display                  # remove plugin
```
