#!/usr/bin/env bash
# Preview by default. This helper has no staging-home option.
set -euo pipefail
REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
if ! command -v python3 >/dev/null 2>&1; then
  printf 'Python 3 is required for the scoped cleanup helper.\n' >&2
  exit 1
fi
exec python3 -B "$REPO_DIR/lib/cleanup.py" "$@"
