#!/usr/bin/env bash
# Optional activation. Omarchy's theme setter restarts desktop components.
set -euo pipefail
apply=false
case "${1:---dry-run}" in
  --dry-run) ;;
  --apply) apply=true ;;
  -h|--help)
    printf 'Usage: %s [--dry-run|--apply]\nRestores Tokyo Night and the recorded wallpaper. --apply reloads themed components.\n' "${0##*/}"
    exit 0 ;;
  *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { printf 'Supply one option only.\n' >&2; exit 2; }
omarchy_path="${OMARCHY_PATH:-$HOME/.local/share/omarchy}"
wallpaper="$omarchy_path/themes/tokyo-night/backgrounds/1-sunset-lake.png"
expected=06dfb9fce029ec35adb40ea3939296777c2b140d1232b5a1697b15052d575362
printf 'Theme: tokyo-night\nWallpaper: %s\n' "$wallpaper"
if ! "$apply"; then
  printf 'Preview only. --apply runs omarchy-theme-set and omarchy-theme-bg-set, which reload desktop components.\n'
  exit 0
fi
[[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] || { printf 'Run --apply inside your new Omarchy desktop session.\n' >&2; exit 1; }
for cmd in omarchy-theme-set omarchy-theme-bg-set sha256sum; do
  command -v "$cmd" >/dev/null || { printf 'Missing command: %s\n' "$cmd" >&2; exit 1; }
done
[[ -f "$wallpaper" ]] || { printf 'Recorded wallpaper is not shipped by this Omarchy version. Choose a background manually.\n' >&2; exit 1; }
actual=$(sha256sum -- "$wallpaper")
[[ "${actual%% *}" == "$expected" ]] || { printf 'Wallpaper differs from the recorded file. Review it and choose it manually.\n' >&2; exit 1; }
export OMARCHY_PATH="$omarchy_path"
omarchy-theme-set tokyo-night
omarchy-theme-bg-set "$wallpaper"
