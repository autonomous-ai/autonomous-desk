# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Autonomous Desk** — an open-hardware "Thinking Desk" with an LCD, plus its software:
two sibling `thinking-desk` plugins (in `software/`) — one for **Claude Code**,
one for **Codex**. Each shows task-done + account usage % on the desk LCD, buzzes when
its agent needs approval/input, and analyzes that agent's local sessions into a
"builder profile". Nothing leaves the machine except the agent's own usage call
(Anthropic OAuth for Claude Code; local session files for Codex) and a LAN `HTTP POST
http://<device_ip>:3000/lcd` to the desk firmware (`sds-firmware-desk-ai`); device
discovery is via mDNS/UDP. This repo is **independent** of the SDS e-commerce backend
(no shared-protos / BFF / ecm-sds).

## Repo Layout

- `software/` — the two agent plugins. `software/README.md` is the **public landing
  page** for both (the autonomous.ai product page links straight to
  `/tree/main/software`, so keep that path and that file intact).
  - `software/claude-code/` — Claude Code plugin: `plugin.json`, `.claude-plugin/`,
    `hooks/` (Stop/Notification), `commands/`, `scripts/`. See its `GUIDE.md`, `SKILL.md`.
  - `software/codex/` — Codex plugin: `.codex-plugin/plugin.json`, `hooks/`
    (Stop/PermissionRequest), `skills/`, `scripts/`, `tests/`. See its `GUIDE.md`.
  - Both are Python 3 stdlib only (zero deps), macOS.
  - They are **separate packages on purpose**: each CLI installs only its own
    directory, so neither ships the other's code. Shared-looking files
    (`discover.py`, `insights.py`, `on-stop-done.py`) have diverged and are *not*
    a single source — change one, decide consciously about the other.
- `install.sh` (repo root) — one-command installer; detects `claude` / `codex` on
  PATH and installs for each.
- Marketplace manifests live at the repo root and hardcode plugin paths:
  `.claude-plugin/marketplace.json` (`software/claude-code`) and
  `.agents/plugins/marketplace.json` (`./software/codex`). Both `on-stop-done.py`
  files also hardcode a raw.githubusercontent URL for the update check. **Moving a
  plugin directory means updating all of these.**
- `cad/`, `electronics/`, `bom/`, `assembly/`, `firmware/` — open hardware (CAD/PCB/BOM/build).
- `docs/` — extra guides.

## Git LFS

CAD, STL, STEP, PCB, video, and PDF are stored in **Git LFS**. Run `git lfs install`
once before cloning/pushing (see `docs/git-lfs.md`).

## Working Rules

1. **Commit when done, don't push** — When a task/change is complete, commit it locally
   with a clear message. Do **NOT** push unless the user explicitly asks.
2. **Python: stdlib only** — The plugin has zero third-party dependencies. Keep it that way.
3. **Nothing leaves the machine** — Preserve the privacy model: only the Anthropic API and
   the LAN call to the desk firmware are allowed to leave the local host.
