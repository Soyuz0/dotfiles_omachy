#!/usr/bin/env bash
# Restore personal configuration onto an existing Omarchy installation.
set -euo pipefail
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3 is required. On Omarchy: sudo pacman -S --needed python\n' >&2
  exit 1
fi
exec python3 "$REPO_DIR/lib/install.py" "$@"
