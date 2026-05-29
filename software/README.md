# Autonomous VibeDesk Display for Claude Code

Turn your [VibeDesk](https://www.autonomous.ai/standing-desks/autonomous-desk-5-ai) into a live Claude Code companion. Task-done notifications and usage data appear on your desk display ??? no dashboard, no browser, just a glance.

https://github.com/user-attachments/assets/c82094b5-4b77-46ee-b667-aca28d9a6bfc

## Quick Start

```bash
claude plugins marketplace add https://github.com/autonomous-ai/vibe-desk-display
claude plugins install vibe-desk-display
```

Restart Claude Code, then type `pair my display` and follow the on-screen instructions.

See the full [Setup Guide](GUIDE.md) for details.

## Features

- **Task done + usage display** ??? when Claude completes a task, shows a "Task Done" notification followed by 5-hour and 7-day usage
- **Notifications** ??? send custom messages to the screen ("notify my display when done")
- **OTP pairing** ??? no sticker reading, just enter the code shown on screen
- **Zero dependencies** ??? Python 3 stdlib only, no pip install needed

## Commands

| Command | Description |
|---------|-------------|
| `/vibe-desk-display:usage` | Refresh usage display now |
| `/vibe-desk-display:notify` | Send a notification |

Or use natural language: "show my usage on display", "notify my display", "unpair my display"

## Requirements

- macOS
- Python 3
- A VibeDesk device on the same WiFi
- Claude Code with OAuth login

## Update / Uninstall

```bash
claude plugins update vibe-desk-display@vibe-desk-display   # pull latest
claude plugins uninstall vibe-desk-display                  # remove plugin
```
