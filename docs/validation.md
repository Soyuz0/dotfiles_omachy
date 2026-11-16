# Validation record

Date: 2026-11-15. These checks covered the repository update without running a real
installation against the source machine's home or changing its services.

## Offline checks

- `PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover -s tests -v` passed
  all 72 tests. The suite uses temporary homes, synthetic config roots, and inert
  provider stubs. It covers preview, conflicts, backups, original bytes/modes and
  dangling symlinks, repeat runs, restore and interrupted restore, automatic
  rollback, unsafe paths/parents, source exclusions, concurrent planning edits,
  optional apps, and helper preview/help behavior.
- All setup scripts and the Bash fragment passed `bash -n`. Lua source files
  passed `luac -p`; Python, JSON, JSONC where applicable, and TOML source data
  passed parsing checks. No editor or live shell configuration was loaded.
- `git diff --check` passed. Existing personal desktop edits were retained.
- A separate real staging-home smoke test previewed without writes, installed
  links, reran without changes, and restored successfully. Its job-owned temporary
  home was then removed, without following its symlinks.
- All 51 original files/links in the ignored legacy `scripts/` tree remained
  unchanged against the before-update SHA-256/link inventory. The live
  `~/.local/bin` symlink was not migrated or changed. No original repository
  file was deleted.
- Gitleaks 8.30.1 scanned all 86 Git-visible candidate files, excluding the legacy
  installed artifacts and private ignored files. It reported no findings. This
  is a scanner result, not a guarantee that every possible secret format is known.

Optional development helper validation also exercised all 15 nonempty tool
selections through inert mise stubs, provider failures, and credential/runtime
sentinels. Hardware helper validation used isolated fixtures for header/source
checks, unsupported hardware, module paths, drop-in refusal, and command failure.
No real provider install, DKMS build, module load, or service activation was run.

## Read-only upstream checks

- GitHub's public TPM refs were queried without cloning or running plugin code.
  `refs/tags/v3.1.0` is annotated tag object
  `c628645dfa7c4fc16acfb7a73c9d7a98697b472c`; its peeled commit is
  `7bdb7ca33c9cc6440a600202b50142f401b6fe21`. The helper verifies the latter
  against checkout HEAD. A persistent inert-clone test guards this distinction.
- The public npm registry returned the exact versions `@openai/codex@0.164.0`,
  `prettier@3.6.2`, and `cspell@9.2.1`. Their declared Node minimums were 16, 14,
  and 20 respectively, compatible with the selected Node major.
- Node's official `v26.12.1/SHASUMS256.txt` listed the Linux x64 and arm64
  archives. No runtime archive or npm package was downloaded or installed.
- All declared desktop, development, and optional application package names
  resolved in the source machine's existing Arch/Omarchy sync databases. This
  check did not refresh those databases or prove future package availability.

## Review findings addressed

The independent review reproduced two issues: private/generated source-directory
contents could enter the plan, and generated Bash/monitor actions could accept a
newer destination edit as their baseline. Component-aware directory pruning and
decision-time destination fingerprints address those cases. Six persistent
regression tests cover the reported cases and related symlink/create-only paths.
The source-exclusion tests also cover root-level generated-artifact patterns and
ignored directory symlinks. The same independent reviewer rechecked the fixes,
confirmed both original findings closed, and found no new concrete defect in the
focused changes. Its stable snapshot passed all 72 tests. The reviewer also
independently verified the corrected TPM commit handling with inert Git fixtures.

## Limits

The configured LSP executables were unavailable. A full LSP pass would require
installing the configured tools, including `bash-language-server`,
`lua-language-server`, and the configured Python server, or correcting their
commands in `pi-lsp.json`. No Pi configuration was changed for this task.
ShellCheck was not installed. Syntax tests are not a substitute for those checks.

A fresh graphical Omarchy VM was not provisioned. Actual login, first-start plugin
and Mason downloads, package installation, module signing/ABI acceptance,
DisplayLink output, and behavior on another Omarchy release remain untested.
Use the documented previews and review hardware settings on the target machine.

The baseline inventory and original setup scripts were saved outside Git under
`~/.local/state/dotfiles-omachy/before-20261115-225105/`. They are small recovery
records, not a copy of credentials or the full home directory. Keep these local
recovery records outside the published repository.

## Selected desktop additions follow-up

The subsequent update adds the two small Neovim mappings, the explicitly requested
`e!` reload mapping, LazyGit preferences, local-only Atuin, Fastfetch startup,
and pinned tmux persistence sources.

- Actual headless Neovim with no init or plugins tested `e!` against a temporary
  modified buffer and confirmed the original disk bytes were unchanged.
- Atuin 18.24.1 was installed in the user account from the official release after
  archive checksum verification. Tests use temporary homes, prove the managed
  config is read, parse generated Bash initialization, and check synthetic history
  database permissions under a normal umask. No live history was read or imported.
- Fastfetch 2.70.0 was already installed. Seven inert pseudo-terminal tests cover
  one banner per interactive shell, opt-out, missing/failing binaries, redirected
  output and noninteractive shells. No live startup file was sourced.
- The pinned tmux sources passed commit, byte-state and index-flag checks. New
  snapshot storage is guarded at `~/.local/state/tmux-resurrect` with mode `0700`.
  Private-socket tests cover failure blocking, hidden index modifications and
  loader behavior. No old snapshots were read or migrated.
- Scoped live activation loaded only resurrect and continuum. All nine existing
  pane process IDs, prefixes, pane navigation, status mode and status interval
  were preserved. The status save interpolation is attached for the 60-minute
  interval. No save, restore, process replay, full config reload or session restart
  was requested by setup. A real save/restore cycle was not used as a test around
  active work. See the persistence doc for its status-refresh scheduling limits.

Private backups and scoped live-operation records for these changes are under
`~/.local/state/dotfiles-omachy/desktop-additions-before-20261115-234420/`.
The Bash backup may contain credentials and must never be published.

## Pi fresh-restore validation scope

`--pi` is an explicit opt-in and is incompatible with offline home staging or
file-restore mode. Orchestration tests use inert commands to check package
selection, preflight/install ordering, no-write previews and refusal behavior.
The helper's bootstrap tests use synthetic repositories and provider stubs.

The real private bootstrap was not run against this machine. It has an active Pi
and an existing private checkout with unrelated edits, which the helper correctly
refuses to adopt. Read-only checks confirmed that the current non-secret version
metadata is supported: Pi 1.5.2, Node v26.12.1 and three pinned source entries.
No private configuration, credentials, provider stores, sessions or source trees
were copied into the public dotfiles. The live private checkout was not changed
or synchronized by this task. A real fresh-target dependency build and SDK
startup remain required end-to-end validation, beyond the isolated stub suite.

The final full suite passed all 154 tests. Direct Ruff, shell/Lua syntax, Python
AST and config parsing checks passed; the final candidate scan covered 101
Git-visible files with no Gitleaks findings. Default LSP executables remain
unavailable as noted above. No extra tools were installed to change that routing.

Independent review caught a Pi working-directory error and insufficient checkout
byte verification. The corrected implementation uses the resolved managed Node
without changing the caller's cwd, and checks raw tracked bytes, symlink targets
and executable bits against pinned trees. The reviewer reran the two original
reproductions and all 43 focused Pi tests, confirmed both findings closed, and
reported no remaining concrete blocker within the focused scope. A separate
review likewise closed the tmux snapshot-privacy and hidden-index findings.

## Authorized app cleanup follow-up

The user subsequently authorized exact cleanup targets. Native targets are
Alacritty, Signal, Blueberry and Spotify. Web shortcut targets are Zoom, HEY,
Basecamp, Google Contacts, Google Messages, Google Maps, X, Figma, Discord and
Fizzy. Aether, cliamp, bluetui, iCloud and all other apps remain outside the policy.
`--cleanup` is an explicit setup option; Spotify and Signal were removed from the
optional install manifest to prevent reintroduction.

Independent review caught a last-comparison race before unlink/MIME replacement.
The fix atomically captures the actual inode, validates after capture, retains it
in the private journal, and uses no-overwrite publication/recovery. The reviewer
closed the finding after all 46 focused tests and 10 independent boundary probes
passed. The final full suite passed all 200 tests. Direct Ruff, syntax and diff
checks passed. The cleanup follow-up source scan covered 106 candidate files
with no Gitleaks findings. Configured LSP executables remain unavailable; install them or
correct their commands in `pi-lsp.json` for those optional diagnostics.

Live application deliberately used only `--apply --shortcuts-only`, because the
user deferred Spotify's administrator-authenticated removal. Zoom's launcher was
removed, the other nine were already absent, and one stale HEY mailto token was
removed. All unrelated launchers, the Zoom icon, other MIME values/comments and
MIME permissions were preserved. No package, app-data, cache or service operation
was performed. Alacritty, Signal and Blueberry remain absent. Spotify remains
installed/pending, and Aether, cliamp and bluetui remain installed.

The successful run and held originals are private under
`~/.local/state/dotfiles-omachy/cleanup/20261116T101606Z-98a732cfcfdc4542be7f1a98aadf06a9/`.
Its run directory is `0700`, and its manifest/before-copies are `0600`. A clean
repeat created no journal and did not rewrite MIME data. The full read-only
preview now reports only Spotify as remaining native work. No root authentication
workaround was attempted.

No current Pi configuration was changed, so the private Pi sync workflow was not
run over its unrelated pending edits. Git history records subsequent commits;
the live Spotify removal remains a separate administrator-authenticated action.
