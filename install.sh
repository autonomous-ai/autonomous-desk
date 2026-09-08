#!/bin/sh
# Autonomous Thinking Desk Display — installer
#
# Installs the desk-display plugin for whichever AI coding agent CLIs you have.
# Both plugins are Python 3 stdlib only; nothing is compiled and nothing is
# downloaded except the plugin source itself.
#
#   curl -fsSL https://raw.githubusercontent.com/autonomous-ai/autonomous-desk/main/install.sh | sh
#
# Flags:
#   --claude-only   install for Claude Code only
#   --codex-only    install for Codex only

set -eu

REPO_URL="https://github.com/autonomous-ai/autonomous-desk"
MARKETPLACE="autonomous-desk"
PLUGIN="thinking-desk"
OLD_PLUGIN="vibe-desk-display"   # renamed in 2026; removed on upgrade

WANT_CLAUDE=1
WANT_CODEX=1

for arg in "$@"; do
  case "$arg" in
    --claude-only) WANT_CODEX=0 ;;
    --codex-only)  WANT_CLAUDE=0 ;;
    -h|--help)     sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ -t 1 ]; then
  B=$(printf '\033[1m'); D=$(printf '\033[2m'); R=$(printf '\033[0m')
else
  B=''; D=''; R=''
fi

say()  { printf '%s\n' "$*"; }
step() { printf '%s==>%s %s\n' "$B" "$R" "$*"; }
warn() { printf '%s!!%s  %s\n' "$B" "$R" "$*" >&2; }

installed_claude=0
installed_codex=0
migrated=0

# The plugin used to be called vibe-desk-display. It is a different plugin id,
# so leaving it installed alongside the new one registers the Stop hook twice
# and you get two cards and two buzzes per task. Remove it first.
old_is_installed() {
  case "$1" in
    # codex lists every plugin its marketplaces offer, including ones marked
    # "not installed" — match the row and exclude that state.
    codex) codex plugin list 2>/dev/null | grep "^$OLD_PLUGIN@" | grep -qv "not installed" ;;
    # claude lists installed plugins only.
    *)     claude plugin list 2>/dev/null | grep -q "$OLD_PLUGIN" ;;
  esac
}

remove_old() {
  cli="$1"; sub="$2"
  if old_is_installed "$cli"; then
    step "Removing the old $OLD_PLUGIN plugin ($cli)"
    if "$cli" plugin "$sub" "$OLD_PLUGIN" >/dev/null 2>&1; then
      migrated=1
    else
      warn "Could not remove it automatically. Run: $cli plugin $sub $OLD_PLUGIN"
    fi
  fi
}

# --- Claude Code -------------------------------------------------------------
if [ "$WANT_CLAUDE" -eq 1 ] && command -v claude >/dev/null 2>&1; then
  step "Claude Code detected — installing $PLUGIN"
  remove_old claude uninstall
  # --sparse keeps the marketplace checkout to the plugin dirs, skipping the
  # CAD/STL/video payload in this repo. Fall back if the flag is unsupported.
  claude plugin marketplace add "$REPO_URL" --sparse .claude-plugin software/claude-code \
    || claude plugin marketplace add "$REPO_URL" \
    || true
  # `add` fails when the marketplace is already configured, and its cached
  # manifest may predate the rename — refresh it or the plugin won't be found.
  claude plugin marketplace update "$MARKETPLACE" >/dev/null 2>&1 || true
  if claude plugin install "$PLUGIN@$MARKETPLACE" -y; then
    installed_claude=1
  else
    warn "Claude Code install failed. Try manually:"
    say  "    claude plugin install $PLUGIN@$MARKETPLACE"
  fi
fi

# --- Codex -------------------------------------------------------------------
if [ "$WANT_CODEX" -eq 1 ] && command -v codex >/dev/null 2>&1; then
  step "Codex detected — installing $PLUGIN"
  remove_old codex remove
  codex plugin marketplace add "$REPO_URL" --sparse .agents --sparse software/codex \
    || codex plugin marketplace add "$REPO_URL" \
    || true
  # Same as above: refresh a marketplace that was already configured.
  codex plugin marketplace upgrade "$MARKETPLACE" >/dev/null 2>&1 || true
  if codex plugin add "$PLUGIN@$MARKETPLACE"; then
    installed_codex=1
  else
    warn "Codex install failed. Try manually:"
    say  "    codex plugin add $PLUGIN@$MARKETPLACE"
  fi
fi

# --- Nothing found -----------------------------------------------------------
if [ "$installed_claude" -eq 0 ] && [ "$installed_codex" -eq 0 ]; then
  warn "No supported agent CLI was installed successfully."
  say  ""
  say  "This installer needs ${B}claude${R} or ${B}codex${R} on your PATH."
  say  "  Claude Code   https://claude.com/claude-code"
  say  "  Codex         https://developers.openai.com/codex"
  say  ""
  say  "Then re-run this installer."
  exit 1
fi

# --- Next steps --------------------------------------------------------------
say ""
step "Installed. Three things left:"
say ""
say "  ${B}1.${R} Restart your agent (exit and reopen)."
if [ "$installed_codex" -eq 1 ]; then
  say ""
  say "  ${B}2.${R} ${B}Codex only:${R} run ${B}/hooks${R} in the Codex ${B}CLI${R} and trust the plugin's"
  say "     Stop and PermissionRequest hooks. In the Codex app or IDE chat"
  say "     ${D}/hooks${R} is an ordinary message and won't open the trust prompt —"
  say "     run ${B}codex${R} once in a terminal instead. Trust is saved to"
  say "     ${D}~/.codex/config.toml${R} and applies everywhere after."
fi
say ""
say "  ${B}3.${R} Put your desk on the same Wi-Fi, then say: ${B}pair my display${R}"
say "     A 4-digit code appears on the display — type it back."
say ""
if [ "$migrated" -eq 1 ]; then
  say ""
  say "  ${D}Note: the plugin was renamed ${OLD_PLUGIN} -> ${PLUGIN}. The old one was${R}"
  say "  ${D}removed. Your paired display and settings carry over untouched, but the${R}"
  say "  ${D}slash commands are now /${PLUGIN}:usage, :insights, :notify.${R}"
fi
say ""
say "  ${D}Afterwards, update the desk firmware in the Thinking Desk mobile app.${R}"
say "  ${D}Guides: $REPO_URL/tree/main/software${R}"
say ""
