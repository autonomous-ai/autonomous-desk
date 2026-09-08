---
description: Fetch and display Claude Code usage on your desk display right now
allowed-tools: Bash(*)
---

Fetch real-time Claude Code usage and send both sections to the display.
Follow SKILL.md section 6 (Usage Monitor) to:

1. Get OAuth token from Keychain / credentials file
2. Fetch usage from the API
3. Build section 1 (5-hour current) and section 2 (7-day weekly)
4. Send section 1 with play_sound: 20, wait 5 seconds, send section 2 with play_sound: 0
5. Report the percentages and reset times
