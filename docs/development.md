# Development configs

Config installation and tool installation are separate. The main installer owns
config placement, backups, and the Bash source-line edit. Neither optional setup
script installs dotfiles, copies live wrappers, or starts/reloads tmux or Neovim.

## Installer handoff

Install these repository paths at their corresponding paths under the target home:

| Repository path | Target |
| --- | --- |
| `bash/.config/bash/custom.sh` | `~/.config/bash/custom.sh` |
| `git/.config/git/config` | `~/.config/git/config` |
| `mise/.config/mise/config.toml` | `~/.config/mise/config.toml` |
| `tmux/.config/tmux/tmux.conf` | `~/.config/tmux/tmux.conf` |
| `nvim/.config/nvim/` | `~/.config/nvim/` |
| `lazygit/.config/lazygit/config.yml` | `~/.config/lazygit/config.yml` |
| `atuin/.config/atuin/config.toml` | `~/.config/atuin/config.toml` |

Keep Omarchy's stock `~/.bashrc`. After its stock initialization, add exactly this
line once through the main installer's backed-up, idempotent edit mechanism:

```bash
[ -r "$HOME/.config/bash/custom.sh" ] && . "$HOME/.config/bash/custom.sh"
```

Do not source any live startup script to validate it. `custom.sh` only affects
interactive Bash. Omarchy already supplies aliases such as `g`, `n`, and `t`,
completion, and mise activation. The custom file appends `~/.local/bin` without
duplicating it. It does not retain the source machine's fixed runtime paths.
When Atuin is present, it initializes history once after Omarchy's fzf setup,
using `atuin init bash --disable-up-arrow --disable-ai`. Ctrl-R searches Atuin;
Up-arrow is unchanged. Atuin 18.24.1 bundles the Bash preexec hook. Noninteractive
shells do not initialize it. `DOTFILES_DISABLE_ATUIN=1` opts out. Fastfetch also
runs once per interactive terminal with TTY output, before Atuin initializes.
It skips scripts and redirected output; `DOTFILES_DISABLE_FASTFETCH=1` opts out.
Both tools are in the package manifests. Open a new shell rather than executing
a live startup file during validation.

`~/.config/bash/local.sh` is an optional, private source hook. The installer must
not create or copy it, including when the source machine has one. The scoped
ignore file also excludes its backups. Credentials in the live `.bashrc` were not
copied. The existing `scripts/.local/bin` binaries and wrappers stay on the live
machine; they are not configuration or dependencies to capture.

Git preferences retain `master` as the default branch, rebasing pulls, automatic
upstream setup on push, rerere, and histogram diffs. They contain no identity,
credentials, remotes, or URL rewrites. A missing `~/.config/git/local.conf` is fine;
a user may create that ignored file for identity and machine-specific preferences.
An existing `~/.gitconfig` takes precedence over the XDG config, so inspect
conflicts locally rather than replacing it or copying it into this repository.

The mise config selects only `node = "26.12.1"`, matching the source config. No
installs, shims, caches, or environment secrets are captured. Omarchy's stock Bash
startup activates mise when it is available. The main installer should include
`tmux` and `nvim` configs by default but must not infer permission to install tools.

## Optional tool installation

`packages/development.txt` lists optional Arch package dependencies. It is not a
package snapshot or a main-installer default. `base-devel` supplies the compiler
and make needed by native Neovim plugins and Treesitter; `ripgrep` and `fd` support
Telescope; `wl-clipboard` supports Wayland clipboard operations. Git and unzip are
needed by plugin/tool managers. `python` supports the existing Python mappings.
Mise, Neovim, and tmux must already exist before their corresponding tools are used.

Both scripts print plans by default and with `--dry-run`, even without providers.
Only `--install` can download/install anything. Do not invoke that mode during
repository validation.

```bash
./setup_dev.sh
./setup_dev.sh --dry-run --tool cspell
./setup_dev.sh --dry-run --tool codex
# Explicit opt-in examples for a later target-machine operation:
./setup_dev.sh --install --tool node
./setup_dev.sh --install --tool prettier --tool cspell
./setup_dev.sh --install --tool codex
./setup_tmux.sh --install
```

`setup_dev.sh` requires an existing mise with its core Node and npm backends and
supports Linux x86_64/aarch64. It accepts only the reviewed selections below:

| Selection | Provider/version | Notes |
| --- | --- | --- |
| `node` | `core:node@26.12.1` | Also a dependency of each npm selection |
| `prettier` | `npm:prettier@3.6.2` | Optional formatter |
| `cspell` | `npm:cspell@9.2.1` | Optional spelling diagnostics |
| `codex` | `npm:@openai/codex@0.164.0` | Optional AI CLI; no auth/session state |

Node's version came from the source mise config. The Codex version was verified
from `~/.local/share/mise/installs/node/26.12.1/lib/node_modules/@openai/codex/package.json`;
it is not a guessed pin. Prettier and cspell use explicit portable pins, not a
claim about globally installed source tools. The default plan lists all available
selections, but installation always requires explicit `--install --tool NAME`.
Selecting another tool never implicitly selects Codex.
Mise validates provider downloads through its own backends. These pins are not an
offline artifact mirror or a lock of every transitive npm dependency. Installation
fails rather than bootstrapping a missing provider through curl, an AUR helper, or
sudo. The script uses explicit `mise install` arguments and never `mise use`,
`mise link`, or forced installation. It does not change global tool selections or
replace current runtime symlinks in `/usr/bin` or `~/.local/bin`. Managed versions
may already be active when the target's mise config selects them.

The npm tools are installed but not globally selected. Run one without changing
configuration, for example:

```bash
mise exec core:node@26.12.1 npm:prettier@3.6.2 -- prettier --version
mise exec core:node@26.12.1 npm:cspell@9.2.1 -- cspell --version
mise exec core:node@26.12.1 npm:@openai/codex@0.164.0 -- codex --version
```

These commands can install missing tools, so they are not validation commands.
Installing Codex supplies only the CLI. Authenticate separately on the target;
never copy Codex authentication files, session/conversation state, or caches.

The helper does not restore every installed AI CLI or development tool. Claude's
native installation at version `2.1.310` and the pipx-managed Poetry, uv, and
detect-secrets tools need separate manual/bootstrap setup. Neither setup script
installs those tools, bootstraps their providers, or copies their private state.

The existing Neovim Mason setup separately installs language servers and
formatters when Neovim is first used. Its requested tools include checkmake,
prettier, stylua, shfmt, ruff, and cspell. `terraform` is needed only for the
configured Terraform formatter. `setup_dev.sh` does not run Mason or Neovim.

## Tmux

The config tolerates absent TPM and missing optional `~/.pi/scripts/tmux-pi-*.conf`
files. The Pi files are not copied. Existing prefixes and navigation bindings
remain unchanged; persistence adds uppercase `prefix+S` and `prefix+U`.

`setup_tmux.sh` installs only TPM at `~/.tmux/plugins/tpm`. It clones upstream tag
`v3.1.0` and verifies commit `7bdb7ca33c9cc6440a600202b50142f401b6fe21` before
publishing the checkout. This is the annotated tag's peeled commit, not its tag
object ID. Both refs were verified against upstream GitHub without cloning or
running plugin code. It does not overwrite, reset, or update an existing
checkout. A different revision, dirty tree, or symlink destination is a clear
error, not permission to replace it. The source machine currently has a different
TPM revision; it remains untouched. Failed new clones remove only that invocation's
staging directory. The installer needs Git and GNU `mv`, `mktemp`, and standard
shell utilities.

`setup_tmux_persistence.sh --install` separately installs and verifies only
resurrect and continuum at pinned commits. It does not require replacing an
existing TPM checkout, execute plugin scripts, or reload tmux. See
[tmux persistence](tmux-persistence.md) for the no-process-replay policy and scoped
activation. Other TPM plugins still require separate installation and are not
covered by a complete lockfile.

## Neovim and cspell

`nvim/.config/nvim/.gitignore` now permits `lazy-lock.json`; the existing lockfile
is retained unchanged. It records plugin revisions, not Mason tools, parsers, or
all future first-start downloads. Neovim was not started to regenerate it.

The reviewed Work source has an external `~/.config/cspell.json` and a 45-entry
custom dictionary. Only the public technical terms `keymap` and `nvim` were
selected for `cspell-dicts/development.txt`; all other entries remain local-only.
The requested `lua/config` and `cspell-dicts` source directories were not present
in the inspected source trees. The new support files are a portable replacement,
not a wholesale copy or a claim that those missing sources were imported.

`lua/config/cspell.lua` builds a runtime cspell config in
`stdpath('state')/cspell/cspell.json`. It imports the tracked `cspell.json`, the
existing external `~/.config/cspell.json` if present, and optional ignored
`~/.config/nvim/cspell.local.json` if present. It does not copy external dictionaries.
The `<leader>cw` mapping writes, sorts, and deduplicates new words only in
`stdpath('state')/cspell/custom-words.txt`, normally
`~/.local/state/nvim/cspell/custom-words.txt`. It creates the directory on first use
and uses Lua APIs rather than a shell command with an unquoted dictionary path.
Private words never append to the tracked portable dictionary. Local dictionary
files under `cspell-dicts/local*.txt` and `cspell.local.json` are ignored and must
not be copied by the main installer.

## Offline validation

Use `bash -n` for both setup scripts and the Bash fragment, `luac -p` for changed
Lua files, and JSON/TOML parsers for config data. Check default and dry-run output
with an isolated home and stub providers. Exercise install-path orchestration only
with inert provider stubs in that isolated home. For Codex, verify the exact
`npm:@openai/codex@0.164.0` argument, the pinned Node dependency, deduplication of
repeated selections, and absence from other selected-tool plans. Also verify that
plan/help/error paths call no provider, private-state sentinels remain unchanged,
and no activation command is issued. Never validate by sourcing the live
`.bashrc`, invoking real `--install`, launching Neovim, or reloading tmux.
