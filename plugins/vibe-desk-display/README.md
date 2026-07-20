# Autonomous Thinking Desk Display for Codex

Turn an [Autonomous Thinking Desk](https://www.autonomous.ai/standing-desks/autonomous-desk-5-ai)
into a live Codex companion. Completion notifications, approval pings, usage,
and local builder insights appear directly on the desk display.

## Features

- **Task complete** — `Codex Done` after a completed turn
- **Approval required** — a distinct `CODEX NEEDS YOU` card and triple-ping
- **Account usage** — local Codex rate-limit windows and reset times
- **Builder insights** — local profile from Codex sessions, with one ambient
  card rotated after a usage refresh; never uploaded
- **OTP pairing** — enter the 4-digit code shown on the display
- **Auto-reconnect** — rediscover the display when DHCP changes its address
- **Custom notifications** — send plain-text or rich-layout status cards
- **Zero Python dependencies** — Python 3 standard library only

## Install from GitHub

```bash
codex plugin marketplace add https://github.com/autonomous-ai/autonomous-desk
codex plugin add vibe-desk-display@autonomous-desk
```

Restart Codex or open a new task. In the CLI, run `/hooks`, review the two
plugin hooks, and trust them. Then ask Codex:

```text
Pair my Autonomous Desk display.
```

After pairing, update the display firmware in the Thinking Desk mobile app.

See [GUIDE.md](GUIDE.md) for settings, privacy details, local development, and
troubleshooting.

## Requirements

- macOS
- Python 3.9 or newer
- A Thinking Desk display on the same Wi-Fi
- A current Codex build with stable plugin and hook support

## Privacy

The plugin talks to the display over the local network. It does not read
`auth.json`, call a private usage API, or upload session content. Account usage
and builder insights are derived locally from Codex JSONL session events.
