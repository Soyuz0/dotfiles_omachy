#!/usr/bin/env bash
# Install TPM only on explicit request. Do not start/reload tmux or plugins.
set -euo pipefail

TPM_URL='https://github.com/tmux-plugins/tpm.git'
TPM_REF='v3.1.0'
# v3.1.0 is an annotated tag. Pin its peeled commit, not the tag object ID.
TPM_REV='7bdb7ca33c9cc6440a600202b50142f401b6fe21'
mode=plan
mode_set=false
fail() { printf 'setup_tmux: %s\n' "$*" >&2; exit 1; }
while (( $# )); do
  case "$1" in
    --install|--dry-run)
      $mode_set && fail 'choose only one of --install and --dry-run'
      mode_set=true
      if [[ $1 == --install ]]; then mode=install; fi
      ;;
    -h|--help)
      printf 'Usage: setup_tmux.sh [--dry-run | --install]\n'
      printf 'Default: print a plan only. --install fetches pinned TPM, not its plugins.\n'
      exit 0
      ;;
    *) fail "unknown argument: $1" ;;
  esac
  shift
done
[[ -n ${HOME:-} ]] || fail 'HOME is required'
TPM_DIR="$HOME/.tmux/plugins/tpm"
printf 'TPM destination: %s\nPinned ref: %s\nExpected revision: %s\n' "$TPM_DIR" "$TPM_REF" "$TPM_REV"
printf 'Existing directories are verified, never updated or replaced. No tmux reload.\n'
if [[ $mode == plan ]]; then
  printf 'Plan only. Use --install to permit the pinned Git clone.\n'
  exit 0
fi
command -v git >/dev/null 2>&1 || fail 'git is required; install it with Omarchy/Arch first'
# Do not follow machine-specific plugin-directory symlinks or replace a live tree.
for path in "$HOME/.tmux" "$HOME/.tmux/plugins" "$TPM_DIR"; do
  [[ ! -L $path ]] || fail "refusing symlink destination component: $path"
done
verify() {
  local dir=$1 revision root
  [[ -d "$dir/.git" ]] || fail "not a standalone Git checkout: $dir"
  root=$(git -C "$dir" rev-parse --show-toplevel) || fail 'cannot inspect TPM checkout'
  [[ $root == "$dir" ]] || fail 'TPM checkout root does not match destination'
  revision=$(git -C "$dir" rev-parse HEAD) || fail 'cannot resolve TPM revision'
  [[ $revision == "$TPM_REV" ]] || fail "existing TPM differs from pinned $TPM_REF; left untouched"
  [[ -z $(git -C "$dir" status --porcelain --untracked-files=all) ]] || fail 'TPM has local changes; left untouched'
  [[ -f "$dir/tpm" && -x "$dir/tpm" ]] || fail 'TPM entry point is missing or not executable'
}
if [[ -e $TPM_DIR ]]; then
  verify "$TPM_DIR"
  printf 'Existing TPM matches the pin. Nothing changed.\n'
  exit 0
fi
mkdir -p -- "$HOME/.tmux/plugins"
staging=$(mktemp -d "$HOME/.tmux/plugins/.tpm-install.XXXXXXXX")
# Only this invocation's newly created staging directory is removed on failure.
cleanup() { [[ -z ${staging:-} ]] || rm -rf -- "$staging"; }
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
git clone --depth 1 --branch "$TPM_REF" --no-checkout -- "$TPM_URL" "$staging"
actual=$(git -C "$staging" rev-parse HEAD)
[[ $actual == "$TPM_REV" ]] || fail 'fetched tag revision differs from expected pin'
git -C "$staging" -c core.hooksPath=/dev/null checkout --detach "$TPM_REV"
verify "$staging"
# GNU mv -T -n refuses a destination created concurrently. Never merge trees.
mv -T -n -- "$staging" "$TPM_DIR"
[[ ! -d $staging ]] || fail 'TPM destination appeared during install; left untouched'
staging=''
printf 'Pinned TPM installed. Plugins are a separate manual network action in tmux.\n'
