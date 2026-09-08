---
name: vibe-desk-display
description: Pair and control an Autonomous Thinking Desk display from Codex. Use for desk-display pairing, custom notifications, Codex usage, builder insights, notification settings, status, or unpairing.
---

# Autonomous Desk Display for Codex

Use the scripts bundled with this skill. Resolve `../../scripts` relative to
this `SKILL.md` and use that absolute directory as `SCRIPT_DIR`. Do not assume
that the current working directory is the plugin directory.

Keep pairing output friendly. Do not show device IDs, IP addresses, config
paths, HTTP responses, pending pairing data, or raw tracebacks to the user.

These scripts POST to the display on the LAN. The Codex turn sandbox has
`network_access: false`, so run every command that talks to the display
(`pair-start`, `pair-complete`, `notify`, `layout`, `usage --display`,
`insights.py --display`) with escalated permissions
(`with_escalated_permissions: true`, or `sandbox_permissions=require_escalated`)
and a short justification that it is a local-network POST to the paired
display. A sandbox-blocked POST is not a Wi-Fi failure — the display is
often up. Hooks run outside the sandbox and do not need this.

## Pair a display

1. Tell the user: `Scanning your network...`
2. Run `python3 "$SCRIPT_DIR/desk_display.py" pair-start`.
3. Relay the script's friendly result. If a display was found, ask for the
   4-digit code shown on it.
4. After the user supplies the code, run
   `python3 "$SCRIPT_DIR/desk_display.py" pair-complete CODE`.
5. Relay the success or retry message exactly. Do not expose raw pairing data.

Pairing uses a 10-minute, one-time code and writes the shared Autonomous Desk
configuration with permission `0600`. Re-pairing the same device updates it.

## Send a custom notification

Run:

```bash
python3 "$SCRIPT_DIR/desk_display.py" notify "MESSAGE"
```

The script strips Markdown, caps messages at 500 characters, reconnects after
an IP change, and respects the user's sound setting. Optional flags are
`--size 1..4`, `--color COLOR`, `--sound NUMBER`, `--device LABEL`, and
`--dry-run`.

For a rich layout, create a JSON file in the user's workspace and run:

```bash
python3 "$SCRIPT_DIR/desk_display.py" layout /absolute/path/layout.json
```

The viewport is 220×117 pixels. A layout may contain up to six `text`, `rect`,
`line`, or `progress` items. Keep item text to 95 characters. Progress values
are clamped to 0..100. Use `--dry-run` to inspect the validated payload without
sending it. Do not create the layout file outside the user's workspace.

## Show Codex usage

Run:

```bash
python3 "$SCRIPT_DIR/desk_display.py" usage --display
```

For a text-only report, omit `--display`. For structured data, use `--json`.
Usage is read locally from Codex's latest `token_count` session event. Do not
read or print `auth.json`; this plugin never needs an OpenAI credential.

## Show builder insights

Run:

```bash
python3 "$SCRIPT_DIR/insights.py" --display
```

Use `--json` for the profile without sending cards, `--once` with `--display`
for the headline card, or `--fresh` to bypass the one-hour local cache. The
analyzer reads local Codex JSONL sessions and never uploads transcript data.

## Change settings

Run `python3 "$SCRIPT_DIR/desk_display.py" config KEY VALUE`.

Map natural-language requests as follows:

- mute/unmute the display -> `sounds_enabled false/true`
- stop/start completion cards -> `task_done_enabled false/true`
- stop/start approval pings -> `notify_enabled false/true`
- stop/start update cards -> `update_check_enabled false/true`
- hide/show builder insights -> `show_insights false/true`
- silence/enable offline warnings -> `device_warning_enabled false/true`
- set the warning threshold -> `usage_threshold 0..100`
- set the completion-card cooldown -> `done_cooldown_seconds` (seconds, 0 or more)

Settings take effect on the next event; Codex does not need to restart.

## Status and unpairing

- Status: `python3 "$SCRIPT_DIR/desk_display.py" status`
- Unpair default: `python3 "$SCRIPT_DIR/desk_display.py" unpair`
- Unpair by label: `python3 "$SCRIPT_DIR/desk_display.py" unpair --device LABEL`

## Automatic hooks

The bundled hooks do the following after the user trusts them in `/hooks`:

- `Stop`: show `Codex Done`, then show account usage cards when a local rate
  limit reaches the configured threshold. Rate-limited by
  `done_cooldown_seconds` (default 60).
- `PermissionRequest`: show `CODEX NEEDS YOU` with a distinct triple-ping.
  Rate-limited to once every eight seconds.

Both hooks fail silently when no display is paired. If a paired device changes
IP, they rescan the LAN, refresh the cached address, and retry once.
