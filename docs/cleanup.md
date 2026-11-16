# Scoped cleanup

`setup_cleanup.sh` removes only the targets authorized for this repository. It is separate from file installation. The root installer's `--cleanup` integration belongs to `lib/install.py`; this helper does not install main files itself.

```bash
./setup_cleanup.sh                         # Read-only preview
./setup_cleanup.sh --dry-run               # Same preview
./setup_cleanup.sh --apply                 # Native + web cleanup; native removal is currently deferred
./setup_cleanup.sh --apply --shortcuts-only # Current authorized live mode; no sudo or pacman
```

`--shortcuts-only` also works with preview. There is no `--all`, package selector, or `--home` staging option. The helper uses the invoking user's home. Do not run the whole helper with sudo. For tests, use the fixture suite below, not an alternate live home.

## Fixed targets

The native package names are exactly `alacritty`, `signal-desktop`, `blueberry`, and `spotify`. Preview reads `pacman -Qq`. Apply selects only installed names from that list and makes one removal attempt:

```text
sudo pacman -R --noconfirm -- <installed authorized subset>
```

Outside a terminal the helper adds sudo's `-n` option so authentication cannot hang. In a terminal it allows the normal sudo prompt. It never uses `-Rns`, cascade, force, orphan cleanup, package installation, database lock removal, network access, or an authentication workaround. Pacman keeps its normal dependency checks.

Aether, cliamp, bluetui, iCloud/Snap, drivers, services, and every other package remain outside this helper's removal list.

The web targets are exactly:

- Zoom
- HEY
- Basecamp
- Google Contacts
- Google Messages
- Google Maps
- X
- Figma
- Discord
- Fizzy

The only user shortcut capture candidates are `~/.local/share/applications/<exact name>.desktop`. Spaces and case matter. The helper never treats `X Tools.desktop`, for example, as X. Each existing target must be a regular, singly linked file owned by the current UID. Its main desktop group must have the exact `Name`, `Type=Application`, and a recognized Omarchy webapp `Exec`.

Recognized commands are the exact `omarchy-webapp-handler-<lowercase-hyphenated-name> %u` form or `omarchy-launch-webapp` with one HTTPS URL on the target's listed host. The current `Zoom.desktop` handler form is supported. Shell wrappers, arbitrary executable paths, extra arguments, duplicate keys, unexpected names, and unrelated launch commands cause refusal. A custom launcher may need separate review; the helper will not guess.

The helper also checks other user desktop files for conflicting exact `Name` values. Ambiguous aliases, unreadable entries, and user desktop symlinks cause refusal rather than broader deletion. This conservative check can block cleanup because of an unrelated symlink; resolve it separately rather than bypassing validation.

System entries with the exact selected desktop IDs under `/usr/share/applications` or `/usr/local/share/applications` are unsupported and cause refusal. The helper neither deletes system files nor creates masks. Other system entries, including separately named protocol handlers, remain untouched. Custom XDG data locations are not cleanup targets.

## MIME edits and preserved data

Only `~/.config/mimeapps.list` is eligible for an association edit. In its `Default Applications`, `Added Associations`, and `Removed Associations` groups, the helper removes exact selected desktop-ID tokens, such as `HEY.desktop`, from semicolon lists. A verified or absent selected user desktop allows this edit. An ambiguous entry blocks the entire preflight, including its associations.

All other tokens, comments, sections, and line endings retain their bytes. An emptied list remains empty; the helper does not choose a replacement default or modify other MIME files.

The helper never deletes application configuration, browser profiles, icons, cache folders, or other app data. Leftover icons are harmless and remain in place. It does not run Omarchy's stock package-drop or webapp-remove helpers. The stock package command uses broader package removal, and the stock webapp remover deletes icons and restarts Walker, which exceed this authorization.

## Preflight, journal, and failures

Preview performs no package mutation, network request, file write, journal creation, cache refresh, or service restart. Apply checks all selected desktop files, MIME files, safe parent directories, and state-path conflicts before any package or target-file mutation. Home and target parents must be real directories owned by the user and not writable by others. The helper uses no-follow directory descriptors and refuses symlink redirects and hardlinked target files.

For a nonempty apply, the helper creates a private run directory:

```text
~/.local/state/dotfiles-omachy/cleanup/<UTC timestamp>-<unique ID>/
```

The run directory has mode `0700`. Copied before-byte backups and `manifest.json` have mode `0600`. An existing cleanup state directory must also have mode `0700`; the helper will not silently change its permissions. Backups and intent records are flushed to disk before mutations. Each file intent includes its original byte fingerprint, file identity, and predetermined private held-inode name.

A comparison followed by unlink or overwrite is not safe against another writer. Instead, the helper uses Linux `renameat2(RENAME_NOREPLACE)` to move the actual target directory entry into the private journal without overwriting any destination. It then revalidates the captured bytes, inode, ownership, link count, mode, size, and mtime. It ignores only ctime, which the rename itself can change. Missing primitive support or different filesystems cause refusal; there is no copy-and-unlink fallback. Device checks run during preflight before native removal and again against the actual journal before file changes. A filesystem rejecting the required rename also fails closed.

The actual captured inode remains as `<number>.held`, even after successful cleanup. It is never physically deleted by this helper. These held originals keep their original permission bits inside the private `0700` directory; they are separate from the immutable copied `0600` before-byte backups. Do not automatically purge them. An application with an already-open file descriptor can still write to that inode, so its later bytes need this protected pathname.

For a desktop entry, successful capture removes its original shortcut name but keeps that actual inode. For MIME, the helper first prepares and flushes its authored replacement in the private journal, captures and validates the original, then publishes only with another no-overwrite rename. `mimeapps.list` is briefly absent between capture and publication. If an application creates a new file in that gap, that new file wins and the helper reports an incomplete result instead of overwriting it. The replacement keeps the original permission bits, and both affected directories are flushed.

On a captured mismatch or a failed publication, the helper attempts to hardlink the held inode back to the original name only if that name is still absent. This no-overwrite link retains the protected held inode as well. If the target is occupied, both that new target and the held inode remain. If restoration fails for another reason, the held inode remains in the journal and the report identifies it. A restored target and its held recovery link share an inode; later cleanup will refuse that hardlinked target until the user reviews the recovery case. The helper never restores by overwriting user work.

This is not a lock against other processes or malicious same-UID writers. Observed changes after capture or publication produce a nonzero, partial result. A writer can still change a file after the final observation, or continue writing through an old descriptor after a successful return. Completion describes the observed cleanup, not a promise that those files stay unchanged. The retained actual inode protects those late bytes; the immutable before-copy and recorded fingerprints may no longer describe its current contents.

The manifest records package return codes, a fresh remaining-package inventory, per-file capture and publication intents, held-inode proofs, restoration outcomes, completions, and a final `complete`, `partial`, or `failed` status. A crash can leave an `intent` journal. Keep that journal and inspect current files and package inventory before deciding what happened. Do not treat an intent as completion or blindly restore old files over newer content. Backups are recovery evidence, not a command to restore package state.

There is exactly one native removal attempt per apply. The helper reconciles fresh inventory even after an error. A nonzero command exit remains an incomplete result even if the selected packages now appear absent. A failed or unavailable inventory also leaves the result incomplete. It never retries an ambiguous transaction. Independently verified user shortcut and MIME cleanup can finish after a native failure, and the journal records the partial result.

Exit `0` means preview succeeded, apply completed, or no work remained. Exit `1` means refusal, failure, or incomplete cleanup. Invalid flags exit `2`. A clean rerun does not create another journal or write files.

## Native cleanup is deferred

The user has deferred live Spotify removal. The applied live operation used only
`--apply --shortcuts-only`: Zoom's entry was removed, the other nine entries were
already absent, and the stale HEY mailto association was cleared. No native package
operation was attempted. Alacritty, Signal and Blueberry were already absent;
Spotify remains installed, as do Aether, cliamp and bluetui. Unrelated launchers,
icons, other MIME settings and app data were preserved. A clean repeat wrote no
new journal or MIME file.

The fixed native removal path remains available for future use, but its presence
is not an instruction to run it now. Development tests use fixtures, not live
package operations.

For any future authorized native run, the helper supports normal sudo authentication in the user's terminal. If pacman reports dependencies or a database lock, address that normal pacman condition separately. Do not add force options or remove the lock. A later `./setup_cleanup.sh --dry-run` reads the current package inventory without changing it.

The helper does not restart Walker or any service, and it does not run `update-desktop-database`. Reopen the launcher so it can read the desktop directory again. If desktop caching remains stale, review the user application's refresh behavior separately. Do not run a system-wide refresh as part of this cleanup.

## Fixture-only tests

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -p test_cleanup.py -v
```

The suite uses temporary homes, inert command stubs, and mocked subprocess calls. It does not run live pacman removal, sudo authentication, Omarchy commands, or service commands. Coverage includes preview and no-op writes, exact names with spaces, the Spotify argument vector, installed-subset filtering, authentication and dependency failures, fresh inventory reconciliation, ambiguous entries, unowned files, symlinks, hardlinks, special files, changed-byte refusals, backup bytes and permissions, MIME preservation, system-desktop refusal, and preserved app data. Boundary regressions modify bytes or replace an inode at capture, write through an open descriptor after capture, create a new MIME file immediately before publication, occupy the target immediately before restoration, and reject cross-filesystem capture before native or file mutation. They verify that newer bytes remain protected and observed conflicts never report completion.
