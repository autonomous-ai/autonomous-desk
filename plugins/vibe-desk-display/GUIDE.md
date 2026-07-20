# Autonomous Desk Display — Codex Setup Guide

## 1. Install

```bash
codex plugin marketplace add https://github.com/autonomous-ai/autonomous-desk
codex plugin add vibe-desk-display@autonomous-desk
```

Restart Codex or start a new task so the new skill and hooks are loaded.

## 2. Trust the hooks

In Codex CLI, run `/hooks`. Review and trust the plugin's `Stop` and
`PermissionRequest` command hooks. Codex records trust against the exact hook
definition, so it may ask you to review again after an update changes a hook.

Hooks are enabled by default. If your configuration disables them, ensure this
is not present in `~/.codex/config.toml`:

```toml
[features]
hooks = false
```

An administrator can also restrict hooks through managed Codex policy.

## 3. Pair the display

Ask Codex:

```text
Pair my Autonomous Desk display.
```

Codex scans the local network, sends a unique code to each reachable display,
and asks for the 4-digit code visible on your device. The code expires after
10 minutes. After pairing, update the display firmware from the Thinking Desk
mobile app.

## What happens next

The `Stop` hook sends a `Codex Done` card after each completed turn, limited to
once per minute. If an available account rate-limit window reaches the usage
threshold (80% by default), up to two usage cards follow.

The `PermissionRequest` hook sends a distinct `CODEX NEEDS YOU` card when Codex
is waiting for approval. It does not depend on terminal focus or idle notices.

## Usage and data

Ask `Show my Codex usage on the desk display` to refresh usage immediately.
The plugin reads the latest local Codex `token_count` event and shows the
available rate-limit windows, percentages, and reset times. Window availability
depends on the active account and model; some sessions expose only one window.
When builder insights are enabled, one ambient profile card follows each usage
refresh so the display gently rotates through the profile over time.

This deliberately avoids reading Codex credentials or calling an undocumented
OpenAI endpoint. Codex transcripts are a best-effort local source and their
format may evolve, so an updated plugin may be needed after a future Codex
format change.

Ask `Show my Codex builder profile` to rotate private local insight cards:

- archetype and activity streak
- peak working hour and session count
- most-used model
- prompting style and manners
- repeated short prompts and top tools

No transcript content leaves the machine.

## Settings

Ask Codex in natural language, for example:

- `Mute the desk display`
- `Stop the Codex completion card`
- `Stop pinging the display for approvals`
- `Set my usage warning threshold to 60`
- `Hide builder insights`
- `Turn every desk notification back on`

The shared configuration is stored at `~/.config/autonomous-lcd.json`, the same
location used by the Claude Code plugin. This lets one paired display work with
both integrations. Settings also apply to both unless a setting is specific to
one plugin.

## Auto-reconnect and troubleshooting

If the display receives a new IP address, the next failed send triggers a LAN
rescan and one retry. If it still cannot be reached:

1. Check that the display is powered on.
2. Confirm the Mac and display are on the same Wi-Fi and not isolated by a
   guest network or VPN.
3. Ask Codex to pair the display again.
4. Run `/hooks` and confirm both hooks are enabled and trusted.
5. Complete a Codex turn before requesting usage, so a current local usage
   event exists.

## Local development

From the repository root:

```bash
codex plugin marketplace add .
codex plugin add vibe-desk-display@autonomous-desk
```

After changing the plugin, reinstall it and start a new task. Validate the
plugin and run the tests before distribution:

```bash
python3 /path/to/plugin-creator/scripts/validate_plugin.py plugins/vibe-desk-display
python3 -m unittest discover -s plugins/vibe-desk-display/tests -v
```

## Uninstall

```bash
codex plugin remove vibe-desk-display
```

Removing the plugin leaves the paired-device configuration in place so the
Claude Code integration can continue using it. Ask Codex to unpair the display
before uninstalling if you want the device entry removed.
