# Tmux persistence

This configuration adds tmux-resurrect and tmux-continuum. It saves layout and
process metadata, not running process memory. It does not make automation or
media jobs restart-safe.

## Policy

- Continuum may save every 60 minutes, when tmux refreshes an enabled status line.
  This is not a wall-clock service. Detached servers may not save on schedule.
- Automatic restore and boot integration are off.
- Pane-content capture and both legacy shell-history save options are off.
- Resurrect process replay is disabled with `@resurrect-processes 'false'`.
- `@resurrect-never-overwrite 'on'` protects existing panes during manual restore.
- `prefix` then uppercase `S` saves manually. `prefix` then uppercase `U` restores
  layout manually. Neither action runs until someone requests it.
- The existing prefixes remain `C-m` and `C-a`. The `h/j/k/l` pane bindings stay
  unchanged. Both conditional Pi includes remain at the end of the config.

Manual restore can create sessions, windows and new shells in saved directories.
It can change the selected window, pane and layout. It must not be used as a way
to resume jobs, and should not be invoked around active work without review.
Shell startup files still run when a manual restore creates shells.

## Reproducible source installation

Run from the repository root:

```sh
./setup_tmux_persistence.sh             # preview only, no network or writes
./setup_tmux_persistence.sh --dry-run   # same preview
./setup_tmux_persistence.sh --install   # prepare private state, verify/install two sources
```

The helper requires Git, Python 3 and Linux `renameat2`. Explicit `--install`
first runs the local private-state guard, then verifies or installs the two
source checkouts. Preview mode does not run the guard or create directories.
The helper does not install packages, call tmux, run TPM, execute plugin scripts,
restore anything or create services. It does not change `setup_tmux.sh` or depend
on its TPM version.

| Official repository | Published tag | Pinned peeled commit | Destination |
| --- | --- | --- | --- |
| https://github.com/tmux-plugins/tmux-resurrect | `v4.0.0` | `e87d7d592cac97fa38c12395ebec042c154a1844` | `~/.tmux/plugins/tmux-resurrect` |
| https://github.com/tmux-plugins/tmux-continuum | `v3.1.0` | `46e0e0023476018ddb4cc0d44783eede27e5a8ec` | `~/.tmux/plugins/tmux-continuum` |

Both refs are annotated tags. Their tag objects are not the commit pins above.
These are the latest published stable tags found during implementation. The
resurrect tag dates to 2022-04-10 and the continuum tag to 2015-03-14. They were
chosen over unbounded default-branch updates. Verification checks the official
HTTPS origin, fetched tag's peeled commit, checked-out HEAD, full Git object
integrity and a clean working tree. It does not verify a maintainer's signature.

The installer rejects symlink destination components, wrong ownership,
group/other-writable directories, unexpected local Git configuration and dirty
or mismatched existing checkouts. It also rejects `assume-unchanged` and
`skip-worktree` index flags, even on currently unchanged files. Those flags can
hide changed tracked bytes from `git status`. The verifier reads flags with
`git ls-files -v -z` and refuses the checkout without clearing flags or changing
the index. `HOME` must be an absolute canonical path.
It disables Git hooks, external user/system Git configuration and templates.
Submodules are not initialized or fetched. Resurrect includes an upstream test
submodule and test symlinks; they remain unused.

Each clone uses a unique private staging directory next to its destination.
The helper checks the pin before a detached checkout, verifies the tree, flushes
the source bytes and atomically publishes with no-overwrite semantics. It never
merges into an existing destination, even if another installer creates one
concurrently. It removes only its own unused staging tree. A matching existing
checkout is verified and left unchanged. Different or dirty checkouts fail
closed. A failure after publication leaves the destination in place for review.
The two publications are independent. A second-plugin failure does not remove
an already verified first plugin.

On the implementation machine, both destinations in the table were installed
and verified at the listed commits. A second `--install` verified them unchanged.
The source installer itself runs no upstream plugin script. After independent
review, the parent separately performed guarded, scoped live activation as
recorded below.

The existing live TPM checkout was intentionally left at
`99469c4a9b1ccf77fade25842dc7bafbc8ce9946`, which differs from the pin in
`setup_tmux.sh`. Do not replace or reset it merely to add these plugins.

## Private snapshot storage

Snapshots use the exact path `~/.local/state/tmux-resurrect`, set by
`@resurrect-dir`. The executable guard is
`tmux/.config/tmux/prepare-persistence-state.py` inside the tmux dotfile root, so
the normal dotfile installation also links it under `~/.config/tmux`.

The guard requires user-owned `HOME`, `.local` and `.local/state` directories
without group/other write access. Missing state parents are created with mode
0700. It refuses symlink components, nonowner directories and unsafe existing
parents rather than changing shared parent permissions. It creates the snapshot
leaf as 0700 or tightens an already user-owned leaf to exactly 0700. Directory
file descriptors and no-follow opens bind permission checks and chmod to the
same inode.

The guard never enumerates, reads or migrates snapshots. It does not touch
`~/.tmux` permissions or existing `~/.tmux/resurrect` metadata. There is no fallback
to that old default directory. Files created inside the 0700 directory remain
inaccessible to other users even if the tmux server has umask 022. No global
shell or server umask change is needed. Full process arguments may still be
stored in snapshots even when process replay and pane capture are off.

To prepare or verify only this private directory, without loading any plugins:

```sh
"$HOME/.config/tmux/prepare-persistence-state.py"
```

A nonzero result is a blocker for activation. Do not bypass the guard or switch
back to the upstream default save directory.

## Loading behavior

The tmux config declares tagged plugins and keeps continuum last, after plugins
that may set the status line. Reviewed TPM code parses the config's plugin
declarations, strips the `#ref` suffix for the local path and runs installed
`*.tmux` entry points. Its normal runtime does not install missing plugins.
No TPM install/update/clean command is part of this integration.

Before either loading path, the config runs the private-state guard and checks
its exit status. A missing, nonexecutable or unsuccessful guard stops the loader
before TPM or either plugin runs. This fails closed, with no public-directory
fallback. When TPM is executable, its existing runtime loads installed plugins.
When TPM is absent, a conditional fallback loads only resurrect and then
continuum, and only if their entry points exist. These paths are mutually exclusive to
avoid duplicate initialization. Repeated config loads do not fetch dependencies.
The helper is the reproducible pin-enforcing installer; manually running TPM
updates is outside its guarantees.

Reviewed entry points are `resurrect.tmux` at the pinned resurrect revision and
`continuum.tmux` at the pinned continuum revision. Resurrect binds the requested
keys and publishes save/restore script paths. Continuum reads those paths and
prepends this command interpolation to the current `status-right`:

```text
#(/home/recent_travels/.tmux/plugins/tmux-continuum/scripts/continuum_save.sh)
```

The path uses the activating user's home on another machine. Continuum does not
change `status-interval` or install a timer service. Status refreshes run a small
interval check. When a save is due, that check launches resurrect's quiet save in
the background. First initialization seeds a last-save timestamp, delaying the
first automatic save for about 60 minutes. If an old timestamp already exists,
a save may be due immediately after activation.

Continuum can skip installing its status interpolation if its process-count
heuristic sees another tmux server. Its old tagged implementation uses `ps` and
client counts for that check. A blocking `tmux run-shell` invocation can itself
look like one extra tmux process and cause a false second-server result. Scoped
activation below uses an explicit, verified server context without that transient
client. Confirm actual activation instead of assuming an hourly timer exists.
Changing `status-right` later can remove the interpolation.
Do not replace a custom status line just to make saving work.

## Activation is deliberately separate

Source installation and repository edits do not reload a running tmux server.
On this machine `~/.config/tmux` is a live symlink into the repository, so a future
config load or a newly started tmux server will see the edits. Neither source
installer performs that action. The parent separately activated only the two
reviewed entry points on the existing server. All nine pre-existing pane process
IDs, prefixes, navigation, status mode and status interval were preserved. No
save, restore, full config reload, process replay or session restart was invoked.

For a running server with active jobs, prefer scoped activation over reloading
TPM and every installed plugin. After review, run the following **inside the
intended existing tmux server**. This block is documentation, not an installer
step. Do not run it from an unrelated private test server. Review any existing
`@continuum-save-last-timestamp` before activating so that an old timestamp does
not cause an unexpected immediate save.

```sh
# Abort the activation block if private state cannot be established.
if "$HOME/.config/tmux/prepare-persistence-state.py"; then

tmux show-option -gqv @continuum-save-last-timestamp

# Apply only persistence options. Preserve prefixes, Pi settings and other plugins.
tmux set-option -g @resurrect-dir "$HOME/.local/state/tmux-resurrect"
tmux set-option -g @resurrect-save S
tmux set-option -g @resurrect-restore U
tmux set-option -g @resurrect-processes false
tmux set-option -g @resurrect-never-overwrite on
tmux set-option -g @resurrect-capture-pane-contents off
tmux set-option -g @resurrect-save-shell-history off
tmux set-option -g @resurrect-save-bash-history off
tmux set-option -g @continuum-save-interval 60
tmux set-option -g @continuum-restore off
tmux set-option -g @continuum-boot off

# Only these entry points; do not run TPM install/update or a restore script.
# Avoid a transient run-shell client confusing continuum's process-count check.
_dotfiles_tmux_context="$(tmux display-message -p '#{socket_path},#{pid},0')"
env -u BASH_ENV -u ENV -u CDPATH TMUX="$_dotfiles_tmux_context" "$HOME/.tmux/plugins/tmux-resurrect/resurrect.tmux"
env -u BASH_ENV -u ENV -u CDPATH TMUX="$_dotfiles_tmux_context" "$HOME/.tmux/plugins/tmux-continuum/continuum.tmux"
unset _dotfiles_tmux_context

# Read-only confirmation on the intended server.
tmux show-option -gqv @continuum-restore
tmux show-option -gqv @continuum-save-interval
tmux show-option -gqv @resurrect-save-script-path
tmux show-option -gqv status-right
tmux show-option -gqv status-interval
tmux list-keys -T prefix S
tmux list-keys -T prefix U

else
    printf '%s\n' 'Private state guard failed. Plugins were not activated.' >&2
fi
```

A normal `tmux source-file ~/.config/tmux/tmux.conf` is another activation route,
but it also executes the existing TPM runtime and reloads unrelated settings.
It is not necessary for scoped activation and was not run during installation.
Do not invoke manual save or restore just to test activation on a busy server.
Deferring activation is safe. No active jobs need to be stopped or restarted.

After activation, scheduled saves inspect pane/process metadata and write under
the guarded 0700 directory `~/.local/state/tmux-resurrect`. They do not replay
processes, send shell-history commands or capture screen contents under this
policy. The plugin may briefly unzoom and
rezoom a pane while reading its layout. Metadata includes directory paths and
process command lines, which may contain sensitive arguments even with content
capture off. Keep save files private. Upstream defaults prune old metadata
backups after 30 days while retaining at least five snapshots. Existing custom
resurrect hooks or strategy overrides must be reviewed separately before live
activation. Do not change them automatically as part of this integration.

## Validation

```sh
bash -n setup_tmux_persistence.sh
python3 -m unittest discover -s tests -p test_tmux_persistence.py -v
```

Tests use fake Git for safety failures, pin checks, idempotence, staging cleanup,
concurrent no-overwrite publication and TPM preservation. Additional regressions
use real temporary Git repositories and indexes. They modify tracked bytes under
`assume-unchanged` and `skip-worktree`, demonstrate that status reports clean,
and check that the actual installer verifier refuses both without altering the
flags or bytes. No live plugin index is modified.

Guard tests exercise umask 022, owned-leaf permission tightening, symlink and
nonowner rejection, unsafe parents and preservation of old test snapshots.
Private-socket tmux tests copy the executable guard into their isolated config
root and use an inert sleep process and authored plugin stubs. They check the
config with absent plugins, fallback loading and TPM loading, option values,
uppercase bindings and unchanged navigation. They also prove that missing or
failing guards block both TPM and fallback loading. No upstream plugin script
runs, and no test inspects or mutates a user's tmux server.

These tests do not prove that a live hourly save fired or that a restore works.
Those actions were deliberately not run around the user's active jobs.
