# Autonomous Thinking Desk Display

Turn your [Thinking Desk](https://www.autonomous.ai/standing-desks/autonomous-desk-5-ai)
into a live companion for your AI coding agent. Task-done notifications, approval
pings, and usage appear on the desk display — no dashboard, no browser, just a glance.

Works with **Claude Code** and **Codex**. Install one or both; they share the same
paired display and the same config file, so one desk serves both agents on one Mac.

https://github.com/user-attachments/assets/c036cb38-f9d6-42e8-8b66-5a09e0e77de2

---

## Install

One command — it detects which agent CLIs you have and installs for each:

```bash
curl -fsSL https://raw.githubusercontent.com/autonomous-ai/autonomous-desk/main/install.sh | sh
```

Prefer to read before you run? Download it first:

```bash
curl -fsSL https://raw.githubusercontent.com/autonomous-ai/autonomous-desk/main/install.sh -o install.sh
less install.sh && sh install.sh
```

<details>
<summary>Or install by hand</summary>

**Claude Code**

```bash
claude plugin marketplace add https://github.com/autonomous-ai/autonomous-desk
claude plugin install thinking-desk@autonomous-desk
```

**Codex**

```bash
codex plugin marketplace add https://github.com/autonomous-ai/autonomous-desk
codex plugin add thinking-desk@autonomous-desk
```

</details>

---

## Then: three steps

**1. Restart your agent** — exit and reopen Claude Code / Codex.

**2. Codex only — trust the hooks.** Run `/hooks` in the Codex **CLI**, then review
and trust the plugin's `Stop` and `PermissionRequest` hooks. In the Codex app or IDE
chat, `/hooks` is just an ordinary message and won't open the trust prompt — run
`codex` once in a terminal instead. Trust is saved to `~/.codex/config.toml` under
`[hooks.state]` and applies everywhere after that.

**3. Pair the display** — once, for both agents. The installer offers to do it
for you; if you skipped that, make sure the desk is on the same Wi-Fi and type:

```text
pair my display
```

Your agent scans the LAN, a **4-digit code** appears on the display, you type it back.
Done. Both plugins share `~/.config/autonomous-lcd.json`, so pairing with one agent
also pairs it for the other — you never do this twice.

> **Update your desk firmware** afterwards, via the Thinking Desk mobile app — older
> firmware renders the notification cards incorrectly.

---

## What it does

| | |
|---|---|
| **Task done** | A card the moment your agent finishes a turn |
| **Waiting on you** | A distinct card + triple-ping buzzer when the agent needs approval, so you don't miss it away from the keyboard |
| **Account usage** | Your remaining usage windows and reset times, shown when you cross a threshold (80% by default) |
| **Builder insights** | A profile computed from your local sessions — archetype, peak hour, top model, go-to prompt — rotated across the display as ambient cards |
| **Custom notifications** | "notify my display when the build is done" |
| **OTP pairing** | No sticker reading — just the code on screen |
| **Auto-reconnect** | If your router hands the display a new IP, the plugin rescans the LAN and updates the saved address |
| **Zero dependencies** | Python 3 standard library only, no `pip install` |

---

## Privacy

Nothing leaves your machine except two things: the call your agent already makes to
its own provider for usage, and a LAN request to your display at
`http://<device_ip>:3000`. Builder insights are computed locally from session files
on disk and are never uploaded. The plugin does not read your credentials.

---

## Turning things on and off

Both plugins read `~/.config/autonomous-lcd.json`. You don't have to edit it — just
say what you want in plain language ("mute the display", "stop pinging me for
approval", "warn me earlier", "turn everything back on") and your agent updates it.
No restart needed.

| Key | Controls |
|-----|----------|
| `sounds_enabled` | Master buzzer. `false` = cards show silently |
| `task_done_enabled` | The task-done card after each response |
| `notify_enabled` | The waiting-on-you approval ping |
| `update_check_enabled` | The silent "Update available" card (at most once a day) |
| `device_warning_enabled` | The in-agent warning when the display can't be reached |
| `done_cooldown_seconds` | Minimum gap between task-done cards |

All default to `true`.

---

## Requirements

- macOS
- Python 3.9 or newer
- A Thinking Desk display on the same Wi-Fi
- Claude Code (OAuth login, not an API key) and/or a current Codex build with
  plugin + hook support

---

## Already using `vibe-desk-display`?

The plugin was renamed to **`thinking-desk`**. Please **remove the old one** —
it is a separate plugin id, so leaving it installed registers the desk hook
twice and you get two cards and two buzzes for every finished task.

The installer above removes it for you. To do it by hand:

```bash
claude plugin uninstall vibe-desk-display     # Claude Code
codex plugin remove vibe-desk-display@autonomous-desk   # Codex
```

Your paired display, threshold, and settings live in `~/.config/autonomous-lcd.json`
and are **not** tied to the plugin name — they carry over untouched, so you do not
need to pair again. The only user-visible change is the slash commands:
`/vibe-desk-display:usage` is now `/thinking-desk:usage` (same for `:insights`
and `:notify`).

---

## Full guides

| | Setup guide | Plugin |
|---|---|---|
| **Claude Code** | [claude-code/GUIDE.md](claude-code/GUIDE.md) | [`software/claude-code/`](claude-code/) |
| **Codex** | [codex/GUIDE.md](codex/GUIDE.md) | [`software/codex/`](codex/) |

Each guide covers settings, troubleshooting, local development, updating, and
uninstalling for that agent.

---

## Layout

```
software/
├── claude-code/    Claude Code plugin (commands, hooks, scripts)
└── codex/          Codex plugin (skill, hooks, scripts, tests)
```

Two separate packages on purpose: each agent CLI installs only its own directory,
so neither ships the other's code to your machine.

## License

Code is [PolyForm Noncommercial 1.0.0](../LICENSE-CODE). See [LICENSE.md](../LICENSE.md)
for the plain-English summary.
