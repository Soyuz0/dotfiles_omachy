#!/usr/bin/env bash
# Fresh-machine restore only. Never source this file from shell startup.
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1
exec python3 "$root/lib/pi_setup.py" "$@"
