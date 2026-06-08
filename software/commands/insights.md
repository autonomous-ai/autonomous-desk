---
description: Analyze your local Claude Code sessions and rotate a builder-profile on your desk display
allowed-tools: Bash(*)
---

Compute the user's **local builder profile** from their Claude Code session
transcripts and show it on the paired VibeDesk display. Everything runs
on-device — no transcript content leaves the machine.

Run the bundled analyzer:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/insights.py --display
```

This reads `~/.claude/projects/**/*.jsonl`, derives the profile (archetype,
peak coding hour, top model, token economy + cache-hit rate, steering style,
velocity), and rotates five cards on the display:

1. **Archetype** — headline label + day streak
2. **Rhythm** — peak coding hour, session/prompt counts
3. **Top model** — most-used model + total tool calls
4. **Token economy** — output tokens + cache-hit %
5. **Builder style** — words/prompt, tools/turn, course-correct rate

Then report the highlights back to the user in plain language (archetype, peak
hour, streak, top model). Use `--json` instead of `--display` if the user just
wants the numbers, or `--once` to send only the headline archetype card.
