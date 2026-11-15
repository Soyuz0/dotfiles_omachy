#!/usr/bin/env bash
# Optional tool installation. Never sourced by the shell or config installer.
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: setup_dev.sh [--dry-run | --install] [--tool NAME ...]

With no arguments, print the available tool plan. No provider is invoked.
--dry-run prints the plan for selected tools without installing anything.
--install requires at least one --tool selection and an existing mise provider.

Supported tools: node, prettier, cspell, codex
The npm tools also require the pinned Node runtime, installed through mise.
No packages, global tool selections, dotfiles, or runtime symlinks are replaced.
Codex is optional. No authentication or session state is copied or restored.
USAGE
}

fail() { printf 'setup_dev: %s\n' "$*" >&2; exit 1; }
mode=plan
mode_set=false
selected=()
while (( $# )); do
  case "$1" in
    --install|--dry-run)
      $mode_set && fail 'choose only one of --install and --dry-run'
      mode_set=true
      if [[ $1 == --install ]]; then mode=install; else mode=plan; fi
      shift
      ;;
    --tool)
      (( $# >= 2 )) || fail '--tool needs a name'
      case "$2" in
        node|prettier|cspell|codex) selected+=("$2") ;;
        *) fail "unsupported tool: $2 (choose node, prettier, cspell, or codex)" ;;
      esac
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) fail "unknown argument: $1" ;;
  esac
done
if (( ${#selected[@]} == 0 )); then
  [[ $mode != install ]] || fail '--install requires an explicit --tool selection'
  selected=(node prettier cspell codex)
fi

# These pins are reviewed data, never arbitrary user-supplied provider specs.
node_spec='core:node@26.12.1'
want_prettier=false
want_cspell=false
want_codex=false
for tool in "${selected[@]}"; do
  case "$tool" in
    prettier) want_prettier=true ;;
    cspell) want_cspell=true ;;
    codex) want_codex=true ;;
  esac
done
npm_specs=()
$want_prettier && npm_specs+=('npm:prettier@3.6.2')
$want_cspell && npm_specs+=('npm:cspell@9.2.1')
# Verified from the source machine's installed @openai/codex/package.json.
$want_codex && npm_specs+=('npm:@openai/codex@0.164.0')
printf 'Provider: existing mise with its core Node and npm backends.\n'
printf 'Install managed version: %s\n' "$node_spec"
for spec in "${npm_specs[@]}"; do printf 'Install managed version: %s\n' "$spec"; done
printf 'No mise use, system package installation, runtime link replacement, or reload.\n'
if [[ $mode == plan ]]; then
  printf 'Plan only. Use --install --tool NAME to permit downloads and installation.\n'
  exit 0
fi

command -v mise >/dev/null 2>&1 || fail 'mise is required; install it with Omarchy/Arch first'
case "$(uname -s):$(uname -m)" in
  Linux:x86_64|Linux:aarch64) ;;
  *) fail 'only Linux x86_64 and aarch64 are supported by this plan' ;;
esac
[[ -n ${HOME:-} && -d $HOME ]] || fail 'HOME must name an existing directory'
# Work outside the repository so its project config/tasks cannot enter this run.
# Explicit versions avoid the implicit "install every configured tool" behavior.
mise --cd "$HOME" install "$node_spec"
if (( ${#npm_specs[@]} )); then
  # Node/npm are supplied to mise's npm backend, not installed over /usr/bin or
  # ~/.local/bin. This does not activate the npm tools globally.
  mise --cd "$HOME" exec "$node_spec" -- mise --cd "$HOME" install "${npm_specs[@]}"
fi
printf 'Installed selected managed versions. Global mise selections are unchanged.\n'
printf 'Use mise exec TOOL@VERSION -- COMMAND for tools not selected in your config.\n'
