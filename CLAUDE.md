# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Autonomous Desk** — an open-hardware "Thinking Desk" with an LCD, plus its software:
a **Claude Code plugin** named `vibe-desk-display` (in `software/`). The plugin shows
task-done + Anthropic usage % on the desk LCD, buzzes when Claude needs approval/input,
and analyzes local Claude Code sessions into a "builder profile". Nothing leaves the
machine except calls to the Anthropic API (OAuth usage) and a LAN `HTTP POST
http://<device_ip>:3000/lcd` to the desk firmware (`sds-firmware-desk-ai`); device
discovery is via mDNS/UDP. This repo is **independent** of the SDS e-commerce backend
(no shared-protos / BFF / ecm-sds).

## Repo Layout

- `software/` — the `vibe-desk-display` Claude Code plugin: `plugin.json`, `hooks/`
  (Stop/Notification), `commands/`, `scripts/`. Python 3 stdlib only (zero deps), macOS.
  See `software/GUIDE.md`, `software/SKILL.md`, `software/README.md`.
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
