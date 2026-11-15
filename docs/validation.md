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
