---
description: Analyze your local Claude Code sessions and rotate a builder-profile on your desk display
allowed-tools: Bash(*)
---

Compute the user's **local builder profile** from their Claude Code session
transcripts and show it on the paired Thinking Desk display. Everything runs
on-device — no transcript content leaves the machine.

Run the bundled analyzer:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/insights.py --display
```

This reads `~/.claude/projects/**/*.jsonl`, derives the profile, and rotates up
to **7 cards** on the display:

1. **Archetype** — headline label + day streak
2. **Peak hour** — when you code most + session count
3. **Top model** — most-used model + its share of turns
4. **Your style** — detailed vs concise prompting
5. **Manners** — how often you thank your agents
6. **Most used** — your go-to prompt *(only if a phrase recurs)*
7. **Crash out** — your loudest ALL-CAPS moment *(only if one exists)*

Cards 6–7 appear only when there's real data for them, so a profile may rotate
5–7 cards. Then report the highlights back to the user in plain language
(archetype, peak hour, streak, top model, go-to prompt). Use `--json` instead of
`--display` for the raw numbers, or `--once` to send only the headline card.
