#!/usr/bin/env bash
# Close a Chromium tab, or the focused window for other applications.
set -euo pipefail
command -v hyprctl >/dev/null || { printf 'hyprctl is required\n' >&2; exit 1; }
command -v jq >/dev/null || { printf 'jq is required\n' >&2; exit 1; }
cls=$(hyprctl -j activewindow | jq -er '.class | select(length > 0)')
case "$cls" in
  Chromium|chromium|Chrome|chrome|omarchy-chromium)
    hyprctl dispatch sendshortcut 'CTRL, W,'
    ;;
  *) hyprctl dispatch killactive ;;
esac
