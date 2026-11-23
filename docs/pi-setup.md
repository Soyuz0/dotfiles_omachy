# Pi on a fresh machine

`setup_pi.sh` restores the user's private [Soyuz0/pi-config](https://github.com/Soyuz0/pi-config) repository. It does not contain a copy of that repository, credentials, or private settings. It is not an updater for a working Pi installation.

```bash
./setup_pi.sh                 # Print the plan only.
./setup_pi.sh --dry-run       # Same plan, no writes or network.
./setup_pi.sh --preflight     # Check local paths and prerequisites only.
./setup_pi.sh --install       # Explicitly permit cloning, downloads and installation.
```

The first three modes never execute Git, mise, npm, cargo, Pi, package managers, or provider commands. Preflight checks executable availability and destination paths through the filesystem. It cannot prove access to the private GitHub repository. `--help` describes the interface. The mode flags are mutually exclusive. Failures return a nonzero exit status.

`--home PATH` changes the printed destination. For preflight and installation it must equal `HOME`, refer to an existing user-owned directory, and contain no symlink components. The helper refuses root. It does not install into a staged home or change the invoking user's global Pi/npm/mise configuration.

## Main installer contract

The main installer can call these commands as the normal user, after its own argument and destination checks:

```bash
bash "$repo/setup_pi.sh" --dry-run --home "$HOME"
bash "$repo/setup_pi.sh" --preflight --home "$HOME"
bash "$repo/setup_pi.sh" --install --home "$HOME"
```

Use the dry-run call for `setup.sh --pi --dry-run`. Use the explicit install call only for an authorized applying invocation. The helper does not invoke the parent installer or install prerequisites itself. `packages/pi.txt` lists the Arch prerequisites for the parent `--packages` flow. That flow should add this manifest only when Pi is selected. An existing mise core provider installs the Node/npm version recorded in the private backup. RTK needs Rust, a C toolchain, pkg-config and OpenSSL development files. No `sudo`, AUR helper, `curl | sh`, or shell-profile edit appears in the Pi helper.

If the parent accepts a different target home, reject an applying `--pi` invocation rather than pretending the helper can configure another account. Read-only Pi preview can still print that home. Run preflight before parent configuration writes when prerequisites are already installed. With `--packages`, run it after prerequisite installation and before invoking Pi installation. Parent package actions retain their own explicit authorization requirements.

## What installation does

1. Reject existing destinations before invoking any installer or Git command. This includes any `~/.pi`, even an empty, clean, dirty, or previously restored checkout. It also rejects an existing Pi executable on `PATH`, `~/.local/bin/pi`, `~/.local/bin/rtk`, the helper's state/runtime directories, and the known external source destinations. Symlinked and foreign-owned destination parents are refused.
2. Reserve `~/.local/state/dotfiles-omachy/pi-restore` exclusively and write a mode-600 receipt. Clone the private repository into a new mode-700 `~/.pi` through normal Git authentication. `GIT_TERMINAL_PROMPT=0` and `GCM_INTERACTIVE=never` prevent interactive credential prompts. No token is extracted, printed or passed on an argument list. Missing private GitHub access stops the restore. The helper does not start a login flow.
3. Pin the fetched private commit, check its tracked paths against the reviewed backup allowlist before checkout, and compare every checked-out tracked file with that commit's blob identity before reading metadata or running its tracked backup safety checker. Set only this new checkout's `core.hooksPath` to `scripts/hooks`. The repository stays detached at the fetched commit. No pull, reset, update, staging, commit or push occurs.
4. Read `installed-versions.json` from that clone. Its exact Pi and Node versions override the old version example in the private README. The reviewed metadata currently records Pi 1.5.2 and Node 26.12.1. The helper accepts Pi 1.5.x, exact numeric versions, full source commit hashes, the known upstream URLs, and the recorded `~/Projects/...` paths. A changed schema, new source or newer Pi SDK needs review rather than guessing.
5. Install the recorded `core:node@VERSION` through mise without selecting it globally. Resolve its managed Node and npm CLI paths using `mise where` from the owned receipt directory. Execute those paths directly with the managed Node directory first on `PATH`, preserving each dependency/check command's intended working directory. No project mise configuration is loaded by these calls. Install `@earendil-works/pi-coding-agent@VERSION` using `npm install --global --prefix ~/.local/share/dotfiles-omachy/pi-runtime --ignore-scripts --no-audit --no-fund`. This is an isolated user-owned npm prefix, not the invoking user's global package tree. The Node and Pi version outputs must match the metadata. npm pins Pi itself but does not pin all transitive dependencies of the CLI, as documented upstream.
6. Run `npm ci --ignore-scripts --legacy-peer-deps` in all three recorded locations:
   - `~/.pi/agent/npm`
   - `~/.pi/agent/local-packages/davis`
   - `~/.pi/agent/agents/resources/web-access`

   Run Davis's root `npm run check`, whose reviewed runner excludes paid/live backend tests. Preserve its root lockfile, host-Pi peers, matching Effect pins, source patches, resource exclusions, and Tokyo Night preference. Do not install nested extension manifests or restore the removed competing subagent/footer packages. Explicit `npm run check` still runs with lifecycle scripts disabled. Its `npm root -g` lookup uses the restore's isolated prefix.
7. Clone SoL-Pi and RTK into new `~/Projects/sol-pi` and `~/Projects/rtk` directories. Check out and verify the exact commits recorded in the metadata, not the moving branch tips. Run `npm ci --ignore-scripts` in SoL-Pi. Run `cargo build --release --locked` in RTK. Cargo's normal pinned build may execute build scripts; npm lifecycle scripts stay disabled. Current metadata also lists `~/Projects/computer-use-linux`. The helper clones that pinned source-review checkout when present, without running its installer or build.
8. Load the restored non-secret resources through the installed Pi SDK in a temporary isolated `HOME` and empty working directory. The fixture copies tracked files only and links the newly installed dependency trees. It contains no credentials or old runtime state. It uses `PI_OFFLINE=1`, disables telemetry/version checks, blocks Node fetch/HTTP/socket attempts, creates an in-memory session, binds print-mode extensions, checks extension import/startup errors, and disposes the session. It never calls `prompt`, a model, a tool, a gateway, or a login command. An extension or network error blocks completion. This check is not an OS sandbox or a functional provider test.
9. Only after that check passes, copy and SHA-256-verify RTK into a new `~/.local/bin/rtk`. Create a new `~/.local/bin/pi` wrapper that executes the resolved managed Node and this private runtime's CLI directly. It preserves the invoking project directory and arguments, sets the matching Node directory first on `PATH`, and does not invoke mise or load project mise configuration before Pi's trust decision. Ensure `~/.local/bin` is on `PATH`. Write the completed receipt with the fetched commit, source pins, completed steps and command checksums.

## Install Codex and Claude Code

When following this guide on a fresh machine, install both the native Codex CLI and Claude Code as part of completing the setup. These are separate installation steps; `setup_pi.sh` does not install either CLI.

1. Check whether `codex` and `claude` are already available on `PATH`. Reuse working installations.
2. Install each missing CLI using its current official installation instructions. Installing Pi or configuring its GPT/Claude models does not satisfy this step.
3. Verify that `codex --version` and `claude --version` both succeed in the user's normal shell. Report any missing or failed installation before calling the setup complete.

Keep existing CLI configuration, authentication and gateway routing intact. New authentication and machine-specific routing remain separate steps below.

## Source verification limits

The helper reads the pinned commit tree, then hashes raw tracked-file bytes with Git's blob header and compares the resulting object identities. It also checks filesystem types, exact symlink target bytes, and Git's executable bit. It does not trust `git status`, index stat caches, `assume-unchanged`, or `skip-worktree`. A checkout filter, line-ending conversion, or LFS materialization that changes raw committed bytes causes refusal, not a reset or silent normalization. Submodules and non-SHA-1 tree formats require manual review.

External trees are checked after checkout, immediately before npm/build consumption, after those operations, and before publication. The private tree is checked before metadata consumption and intentional portability edits, then before/after dependency checks and startup. Only the expected settings and Omarchy-link edits receive explicit identity overrides. A mismatch retains the checkout and leaves the transaction incomplete.

These checks do not lock out another same-user writer or create an immutable build sandbox. They can detect persistent modifications and changes during an individual hash read, but cannot prove that a writer did not briefly change and restore a file between checks. They cover tracked inputs, not the provenance or contents of downloaded dependencies, generated/untracked files, upstream signatures, or a previously modified managed Node installation. The exact Node version is checked, but this helper does not independently authenticate mise's release download.

## Portability and deliberately manual integrations

The helper adapts only the new checkout. It recognizes the original home through the known dashboard package path and Omarchy skill link, not a hardcoded account name. It converts the redundant absolute dashboard package path to a settings-relative path. It preserves the model selection, thinking level, keybindings, package resource exclusions and other preferences. Unrecognized absolute home paths in active agent configuration/resources stop the restore for private review. It does not perform a broad text replacement across code or documentation.

The Omarchy skill link is recreated relative to the new home only if `~/.local/share/omarchy/default/omarchy-skill` exists. Otherwise the helper omits that freshly cloned link. It does not modify the Omarchy installation. Other hosts need an intentional replacement for that skill.

The dashboard package and its redundant bridge source receive empty resource filters in the new settings. Its bridge can start a server automatically, so preserving its enabled state would violate this helper's no-service default. The custom computer-desktop extension is disabled until its separately reviewed binary and desktop dependency installers have been run. These intentional edits leave the new checkout dirty. Review them before any later private backup sync; the helper never runs `sync.sh`.

These components remain manual:

- Provider login, any additional machine-specific model configuration, and native Codex/Claude CLI authentication. Install the CLIs as requested above. Credential-free tracked model overrides return through the clone, but no authentication files, provider stores, history or sessions are copied. No provider is tested by making a paid request.
- Dashboard pairing, local server, machine-specific Tailscale hostname and Serve routes. The installed dashboard also embeds its own older Pi dependency. Installing the shell CLI does not upgrade that embedded runtime.
- Computer-use release executables and desktop libraries. The private README documents the reviewed executable installer and pinned desktop dependency installer. npm `--ignore-scripts` deliberately skips the executable download. Review and install those separately, then intentionally re-enable the adapter.
- Gateway runtime, account enrollment, subscription probes, paid fallback, management UI, systemd services, lingering, Homarr, and all associated keys/state. Tracked restore scripts are resources, not permission to execute them here. Machine-specific script/template paths may still require review.
- Optional language-server binaries, Slack tooling/skills, terminal integration and other desktop services. Slack skills are explicitly excluded from the permanent setup. No optional service is started or enabled.

The private README and Davis integration notes record upstream dependency advisories and compatibility limits. This helper does not run audit fixes, change pins, replace upstream source, or claim to reproduce private source edits that were never backed up.

## Failure and repeat-run behavior

The helper intentionally refuses every existing installation. A completed receipt is an audit record, not permission to adopt, update or overwrite a live setup. There is no automatic resume, cleanup, rollback, reset, or idempotent success shortcut.

A failed transaction retains its new clone, source directories, installed prefix, and an `incomplete` receipt. Inspect the receipt's last step locally. Review those exact owned paths before manually moving or removing them to retry. Do not delete a working Pi, another checkout, or authentication/runtime state to get past the guard. Command output is withheld because Git and dependency tools can echo credential-bearing URLs or configuration. The receipt stores step names and non-secret identities, not raw subprocess logs.

## Validation in this dotfiles repository

```bash
python3 -m unittest discover -s tests -p 'test_pi_setup.py' -v
bash -n setup_pi.sh
```

The tests use temporary homes, synthetic non-secret restore repositories, and inert Git/mise/npm/cargo/Node/Pi executables. They exercise refusal paths, metadata validation, pinned commands, portability, the isolated startup invocation, failures and receipts. The mise stub applies `--cd`, npm checks require a local manifest, and an installed-wrapper regression verifies caller-directory preservation with no mise invocation. Synthetic checkout-filter, hidden-index, executable-bit, symlink-target and concurrent-writer cases verify that unchanged `HEAD` is not accepted as byte proof. These are inert Git simulations, not live Git-filter integration tests. They do not download providers, clone the real private repository, install Pi, or run live model requests.

The actual private bootstrap cannot be tested on the source machine because `~/.pi` is dirty and active. The helper must refuse it. A successful stub test is not proof that every pinned upstream dependency builds on a fresh machine. The real isolated SDK startup and dependency checks run only during an explicitly authorized fresh-machine restore. This change does not customize the current Pi runtime, so it does not run the private sync workflow or edit the already-dirty private README. Any later private restore-documentation update needs a separate reviewed edit that preserves that file's unrelated changes.
