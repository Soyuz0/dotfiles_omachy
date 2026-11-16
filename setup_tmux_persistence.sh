#!/usr/bin/env bash
# Prepare private state and fetch sources only. Never invoke tmux, TPM, or a plugin.
set -euo pipefail
plugins=(
  'tmux-resurrect|v4.0.0|e87d7d592cac97fa38c12395ebec042c154a1844'
  'tmux-continuum|v3.1.0|46e0e0023476018ddb4cc0d44783eede27e5a8ec'
)
mode=plan
mode_set=false
fail() { printf 'setup_tmux_persistence: %s\n' "$*" >&2; exit 1; }
while (( $# )); do
  case "$1" in
    --install|--dry-run)
      $mode_set && fail 'choose only one of --install and --dry-run'
      mode_set=true
      [[ $1 != --install ]] || mode=install
      ;;
    -h|--help)
      printf 'Usage: setup_tmux_persistence.sh [--dry-run | --install]\n'
      printf 'Default: preview only. --install prepares private state and fetches two pinned plugin checkouts. No activation.\n'
      exit 0
      ;;
    *) fail "unknown argument: $1" ;;
  esac
  shift
done
[[ -n ${HOME:-} ]] || fail 'HOME is required'
for spec in "${plugins[@]}"; do
  IFS='|' read -r name ref rev <<< "$spec"
  printf 'Destination: %s/.tmux/plugins/%s\nPinned ref: %s\nExpected peeled commit: %s\n' "$HOME" "$name" "$ref" "$rev"
done
printf 'Private snapshot directory: %s/.local/state/tmux-resurrect (0700)\n' "$HOME"
printf 'TPM and existing destinations are never updated or replaced. No live tmux commands.\n'
if [[ $mode == plan ]]; then
  printf 'Plan only. Use --install to fetch sources without loading any plugin scripts.\n'
  exit 0
fi
command -v python3 >/dev/null 2>&1 || fail 'python3 is required for checked atomic publication'
command -v git >/dev/null 2>&1 || fail 'git is required'
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
state_guard="$script_dir/tmux/.config/tmux/prepare-persistence-state.py"
[[ -x $state_guard ]] || fail "private-state guard is missing or not executable: $state_guard"
"$state_guard" || fail 'private snapshot directory could not be prepared; no plugin install attempted'
printf 'Private snapshot directory prepared and verified. Old snapshots untouched.\n'
python3 - "$HOME" "${plugins[@]}" <<'PY'
import ctypes
import errno
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


def fail(message):
    raise RuntimeError(message)


# Ignore user/system Git config, templates, hooks, filters and environment overrides.
# Repository-local config is checked before any operation that examines files.
env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_SYSTEM='/dev/null',
           GIT_CONFIG_GLOBAL='/dev/null', GIT_TERMINAL_PROMPT='0')
GIT = ['git', '--no-optional-locks', '-c', 'core.hooksPath=/dev/null',
       '-c', 'core.fsmonitor=false', '-c', 'init.templateDir=',
       '-c', 'submodule.recurse=false', '-c', 'protocol.file.allow=never',
       '-c', 'protocol.ext.allow=never', '-c', 'core.attributesFile=/dev/null']


def git(directory, *args):
    result = subprocess.run(GIT + ['-C', str(directory), *args], env=env,
                            text=True, capture_output=True)
    if result.returncode:
        fail(f'git {args[0]} failed in {directory}: {result.stderr.strip()}')
    return result.stdout.strip()


def secure_directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022:
        fail(f'not an owned, non-symlink directory without group/other write access: {path}')


def inventory(directory, git_metadata=False):
    for base, dirs, files in os.walk(directory, followlinks=False):
        secure_directory(Path(base))
        for name in dirs + files:
            path = Path(base) / name
            info = path.lstat()
            if info.st_uid != os.getuid():
                fail(f'not owned by this user: {path}')
            if stat.S_ISLNK(info.st_mode):
                if git_metadata:
                    fail(f'symlink in Git metadata: {path}')
                # Published source includes test symlinks into an uninitialised
                # test submodule. Do not follow them or initialise that submodule.
                continue
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)) or info.st_mode & 0o022:
                fail(f'unsafe file type or writable permissions: {path}')


def verify(directory, name, ref, revision):
    secure_directory(directory)
    metadata = directory / '.git'
    secure_directory(metadata)
    inventory(metadata, git_metadata=True)
    # In particular reject include.*, core.worktree, core.sshCommand,
    # core.fsmonitor, filter.*, and submodule.* before status can use them.
    allowed = {'core.repositoryformatversion', 'core.filemode', 'core.bare',
               'core.logallrefupdates', 'remote.origin.url', 'remote.origin.fetch'}
    keys = git(directory, 'config', '--local', '--no-includes', '--name-only', '--list').splitlines()
    if not set(keys) <= allowed:
        fail(f'unexpected local Git config, left untouched: {directory}')
    expected_url = f'https://github.com/tmux-plugins/{name}.git'
    if git(directory, 'config', '--local', '--no-includes', '--get-all', 'remote.origin.url') != expected_url:
        fail(f'origin does not match official repository: {directory}')
    if git(directory, 'rev-parse', '--show-toplevel') != str(directory):
        fail(f'checkout root differs from destination: {directory}')
    if git(directory, 'rev-parse', 'HEAD') != revision:
        fail(f'HEAD differs from pinned {ref}, left untouched: {directory}')
    if git(directory, 'rev-parse', f'refs/tags/{ref}^{{commit}}') != revision:
        fail(f'tag differs from expected peeled commit: {directory}')
    if git(directory, 'config', '--local', '--get', 'core.bare') != 'false':
        fail(f'not a working checkout: {directory}')
    # Never ask status to recurse into an existing submodule working tree.
    for entry in git(directory, 'ls-tree', '-r', 'HEAD').splitlines():
        if entry.startswith('160000 '):
            submodule = directory / entry.split('\t', 1)[1]
            if submodule.is_symlink() or (submodule.exists() and (not submodule.is_dir() or any(submodule.iterdir()))):
                fail(f'submodule must remain uninitialised: {submodule}')
    inventory(directory)
    # -v marks assume-unchanged entries with a lowercase tag and skip-worktree
    # entries with S. Both can hide modified tracked bytes from git status.
    # Reject the flags, even on presently unchanged files, without clearing them.
    for entry in git(directory, 'ls-files', '-v', '-z').split('\0'):
        if entry and (entry[0] == 'S' or entry[0].islower()):
            fail(f'index flags can hide tracked changes, left untouched: {directory}')
    if git(directory, 'status', '--porcelain', '--untracked-files=all', '--ignored', '--ignore-submodules=none'):
        fail(f'checkout is not clean, left untouched: {directory}')
    entry = directory / ('resurrect.tmux' if name == 'tmux-resurrect' else 'continuum.tmux')
    if entry.is_symlink() or not entry.is_file() or not os.access(entry, os.X_OK):
        fail(f'entry point is not a regular executable file: {entry}')
    git(directory, 'fsck', '--full', '--no-reflogs')


def sync_tree(directory):
    # Flush source bytes and directory entries before making the tree visible.
    for base, dirs, files in os.walk(directory, topdown=False, followlinks=False):
        for path in [*(Path(base) / name for name in files), Path(base)]:
            if path.is_symlink():
                continue
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)


def main():
    os.umask(0o077)
    home = Path(sys.argv[1])
    if not home.is_absolute() or home.resolve() != home:
        fail('HOME must be an absolute canonical path without symlink components')
    secure_directory(home)
    parent = home
    for component in ('.tmux', 'plugins'):
        parent = parent / component
        if not os.path.lexists(parent):
            parent.mkdir(mode=0o700)
        secure_directory(parent)
    # Linux renameat2 with RENAME_NOREPLACE gives an atomic no-overwrite
    # publication, including when an empty destination appears concurrently.
    rename = getattr(ctypes.CDLL(None, use_errno=True), 'renameat2', None)
    if rename is None:
        fail('Linux renameat2 is required; no checkout was published')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    specs = [spec.split('|') for spec in sys.argv[2:]]
    # Preflight both existing destinations before fetching anything.
    for name, ref, revision in specs:
        destination = parent / name
        if os.path.lexists(destination):
            verify(destination, name, ref, revision)
    for name, ref, revision in specs:
        destination = parent / name
        if os.path.lexists(destination):
            verify(destination, name, ref, revision)
            print(f'Already verified, unchanged: {destination} {revision}')
            continue
        staging = Path(tempfile.mkdtemp(prefix=f'.{name}-install.', dir=parent))
        try:
            secure_directory(parent)
            git(parent, 'clone', '--depth', '1', '--single-branch', '--branch', ref,
                '--no-checkout', '--no-recurse-submodules', '--',
                f'https://github.com/tmux-plugins/{name}.git', str(staging))
            if git(staging, 'rev-parse', f'refs/tags/{ref}^{{commit}}') != revision:
                fail(f'fetched tag differs from expected pin: {name}')
            git(staging, 'checkout', '--detach', revision)
            verify(staging, name, ref, revision)
            sync_tree(staging)
            secure_directory(parent)
            if rename(-100, os.fsencode(staging), -100, os.fsencode(destination), 1) != 0:
                error = ctypes.get_errno()
                if error == errno.EEXIST:
                    fail(f'destination appeared concurrently, left untouched: {destination}')
                raise OSError(error, os.strerror(error), str(destination))
            parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(parent_fd)
            finally:
                os.close(parent_fd)
            verify(destination, name, ref, revision)
            print(f'Installed and verified: {destination} {revision}')
        finally:
            # Only this invocation's private staging tree. Never a destination.
            if staging.exists():
                shutil.rmtree(staging)
    print('Sources installed only. TPM untouched. No plugin scripts or live tmux commands ran.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(f'setup_tmux_persistence: {error}', file=sys.stderr)
        sys.exit(1)
PY
