#!/usr/bin/env bash
# Compatibility name retained for existing callers. This is DisplayLink, not Thunderbolt setup.
set -euo pipefail
script_dir=$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
printf 'setup_thunderbold.sh is a compatibility wrapper for setup_displaylink.sh.\n' >&2
exec bash "$script_dir/setup_displaylink.sh" "$@"
