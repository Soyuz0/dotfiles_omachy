# Personal Omarchy dotfiles

This repository restores the portable parts of my desktop and development setup
**after Omarchy is installed**. It is not an Arch or Omarchy operating-system
installer, a full home backup, or an unattended server installer.

The source machine was inspected on 2026-11-15. It runs Omarchy 3.8.3,
Hyprland 0.56.2, Ghostty 1.3.1, Waybar 0.15.0, Neovim 0.12.6, and tmux 3.8 on
an Apple T2 Mac mini with a DisplayLink dock. These are the configuration baseline,
not a claim that a new VM or every later Omarchy release has been tested.

## Fresh installation

Install a supported Omarchy release first and complete its normal first login.
Keep the new system updated using Omarchy's supported updater. The script does
not run `pacman -Syu`, refresh package databases, or change package repositories.
Git and Python 3 must be available. The setup update has been merged into `main`.
For the full personal restore below, authenticate GitHub access to the private
`Soyuz0/pi-config` repo first. Omit `--pi` for a desktop-only restore.

```bash
git clone --branch main https://github.com/Soyuz0/dotfiles_omachy.git ~/dotfiles_omachy
cd ~/dotfiles_omachy

# Inspect every proposed file replacement and package selection first.
./setup.sh --dry-run --backup --packages --pi --cleanup

# Install dependencies, restore Pi, link configs, then apply selected cleanup.
./setup.sh --backup --packages --pi --cleanup
```

Without `--packages`, `--pi` or `--cleanup`, the script changes configuration only. `--pi`
authorizes the separate Pi/tool restore even without system package installation,
provided its prerequisites already exist. To include the optional applications
referenced by the saved shortcuts, use `--packages --apps`
in both the preview and actual commands. `packages/apps.txt` includes Obsidian,
Typora, 1Password, media/file tools, and Docker. Spotify and Signal are deliberately
excluded so this option does not reinstall cleanup targets. Installing Docker
does not enable its service or change group membership. Pi and its resources are
restored only with `--pi`; TPM, drivers, gateways and services are not enabled as
a side effect.

The default monitor configuration uses the preferred mode and automatic placement
and scale. Personal overrides go in `~/.config/hypr/monitors.local.conf`, which is
created only if absent and is not managed afterward. For the original Mac mini
monitor layout, add `--machine macmini-t2` to both commands. This selects the
stored display layout only, not a kernel or driver setup. Connector names may
change after reboot, docking, or a driver update. Review that profile first.

Most configuration entries are symlinks to this clone. Keep the clone at its
installed location. If you move it, the old links remain and must be deliberately
backed up/reinstalled. Existing changes in this working copy are preserved; the
setup does not reset Git, pull, commit, or push.

## What is restored

- The personal Hyprland bindings, workspace letters, gaps, window styling,
  input/scroll behavior, lock and idle settings, and screen-sharing picker choice.
- The left-side Waybar, Ghostty terminal settings and extended key encodings.
- Neovim configuration, Python query, portable cspell support, and plugin lockfile.
- Tmux configuration, optional private Pi includes, and persistence settings.
- A Bash customization hook after Omarchy startup, including Fastfetch and local-only Atuin history.
- LazyGit's Tokyo Night colors, Nerd Font icons, automatic refresh, and Neovim editor.
- Portable Git preferences and the mise Node 26.12.1 version declaration.
- Kitty and SwayOSD customizations and Bluetooth A2DP auto-connect preferences.
- One reviewed `smart-close.sh` source script. It is optional and does not replace
  the existing close-window keybinding.

The installer has an explicit list of configuration roots. It does not loop over
all top-level repository directories or use `stow --adopt`. Adding a directory to
the repository cannot make it an install target automatically.

Your current fingerprint-disabled lock setting and long idle-lock timeout are
preserved. Review `hypr/.config/hypr/hypridle.conf` and `hyprlock.conf` if a new
machine should use a different security policy.

## Selected shortcuts and history

- Neovim `<leader>cr` copies the current file path relative to the working directory
  when possible. An unnamed buffer leaves the clipboard alone.
- `<leader>a` runs `LspRestart`.
- **`<leader>v` runs `e!` and discards this buffer's unsaved changes.** This is
  intentional and does not ask for confirmation.
- Fastfetch shows the system summary once in each new interactive terminal. It
  skips scripts, piped output and a missing binary. Set `DOTFILES_DISABLE_FASTFETCH=1`
  before the custom hook to opt out.
- Atuin owns Ctrl-R in new interactive Bash shells. Up-arrow keeps its existing
  behavior. Enter in Atuin accepts and executes the selected command.
- Atuin cloud sync, AI hooks, PTY recording, daemon use, and automatic history
  import are disabled. Secret filtering is enabled, but it cannot recognize every
  possible secret. Do not type credentials as shell command arguments.
- Tmux persistence saves layouts every 60 minutes when status refreshes allow it.
  `prefix` then uppercase `S` saves; uppercase `U` restores layouts manually.
  Automatic restore, process replay, pane capture, and shell-history capture are
  disabled. Manual restore may create new shells; it does not resume running jobs.

Fastfetch, Atuin and LazyGit are included in `--packages`. No Atuin account is needed. Open a
new terminal for the Bash hook; existing shells are not restarted. Set
`DOTFILES_DISABLE_ATUIN=1` before the custom hook to opt out. LazyGit's colors are
fixed Tokyo Night values rather than an automatically generated Omarchy theme.
See [tmux persistence](docs/tmux-persistence.md) for source pins and activation.

## Pi and the private config repo

`--pi` calls `setup_pi.sh`, installs the Pi version and Node version recorded by
the private repo, clones `Soyuz0/pi-config` into a fresh `~/.pi`, restores its
reviewed dependency lockfiles and pinned source checkouts, and builds RTK. It uses
a user-owned runtime prefix and publishes local launchers only after an isolated
no-model startup check.

```bash
./setup_pi.sh --dry-run      # No writes, network, logins or providers.
./setup_pi.sh --preflight    # Local path/tool checks only; not a GitHub access check.
```

This is a fresh-home bootstrap, not an updater. It refuses an existing `~/.pi`,
existing Pi on PATH, existing target runtime, or reserved source/tool destinations.
It will not merge, reset or replace your running Pi. Private GitHub access must
already work through normal Git authentication. Provider login remains manual;
credentials, model stores, sessions and history are never restored from Git.
Dashboard, computer-control, gateway services and optional Slack setup stay manual.
See [Pi setup](docs/pi-setup.md) for the exact scope, intentional portability edits,
network/build requirements, incomplete-restore recovery, and validation limits.

Pi downloads, builds and restored checkouts are outside the file installer's undo
transaction. A failed bootstrap can retain its owned partials and receipt for
review; it does not erase those or silently retry an unknown installation.

## Selected app cleanup

`--cleanup` is an explicit opt-in, applied after the configuration install. It
removes installed copies of **Alacritty, Signal, Blueberry and Spotify**. It keeps
Aether, cliamp, bluetui, the iCloud Snap bundle, drivers and unrelated packages.
Package removal is exact and nonrecursive, without orphan cleanup or profile deletion.

It also removes these named Omarchy web shortcuts, when safely identified:

- Zoom, HEY and Basecamp
- Google Contacts, Google Messages and Google Maps
- X, Figma, Discord and Fizzy

These are launcher shortcuts, not separate browser installations. Browser profiles,
account data and unrelated shortcuts are preserved. Only associations naming the
selected desktop IDs are eligible for cleanup; no new default handler is chosen.

For an existing machine, use the dedicated helper rather than rerunning the full
config installer through legacy directory links:

```bash
./setup_cleanup.sh --dry-run
./setup_cleanup.sh --apply                  # May ask for normal sudo authentication.
./setup_cleanup.sh --apply --shortcuts-only # No native package removal.
```

Cleanup previews may query installed-package metadata but make no changes. The
helper does not restart the desktop or services. Package removal requires normal
administrator authentication when selected packages are installed. Removing app
packages or launchers is outside the configuration installer's undo transaction;
private scoped launcher/MIME backups and operation records are retained. Read
[cleanup details](docs/cleanup.md) before applying it.

## Backups, repeat runs, and undo

By default a conflicting destination causes preflight to fail **before any
configuration or package installation**. `--backup` authorizes backing up
conflicting regular files and leaf symlinks. It does not authorize deleting
folders, following parent symlinks, or overwriting a directory with a file.

Backups and an installation journal are stored privately under:

```text
~/.local/state/dotfiles-omachy/installs/<installation-id>/
```

The installer prints the exact undo command. For example:

```bash
./setup.sh --dry-run --restore ~/.local/state/dotfiles-omachy/installs/<installation-id>
./setup.sh --restore ~/.local/state/dotfiles-omachy/installs/<installation-id>
```

Use the actual directory name, not the literal angle-bracket placeholder.
Undo restores original file bytes, modes, and symlinks. It refuses to overwrite
files changed after installation, and it does not remove nonempty directories.
Do not delete the journal or backups before you are sure they are no longer
needed. A failed file installation attempts a protected rollback; any blocked
recovery reports the retained journal path.

A repeat installation skips links already pointing to this clone and does not
append a second Bash hook. It will not overwrite local monitor overrides.
Package installation is outside the file transaction. Undo cannot uninstall
packages, reinstall removed apps, restore cleanup launchers, or undo actions you
explicitly run through the optional helpers.

### Existing directory-level Stow links

The original machine uses whole-directory links such as `~/.config/hypr` and
`~/.local/bin`. These are left intact. A file already resolving to the desired
source is a no-op, but the installer refuses changes through a symlinked parent,
even with `--backup`. It does not convert the legacy directories automatically.
This prevents writes into the repository or unrelated link targets and avoids
hiding the many installed tools in the legacy `~/.local/bin` tree.

Use the fresh-home staging test below to inspect the new layout without touching
the current desktop. Migrating an existing directory-link installation needs a
separate reviewed backup/migration, not a forced rerun of setup.

## Optional tools and desktop activation

These helpers print plans by default. Run their install/apply modes only on the
intended machine after reviewing their output.

```bash
./setup_dev.sh --dry-run
./setup_tmux.sh --dry-run
./setup_tmux_persistence.sh --dry-run
./setup_theme.sh --dry-run

# Explicit network/tool installation, not part of setup.sh:
./setup_dev.sh --install --tool node
./setup_dev.sh --install --tool prettier --tool cspell
./setup_dev.sh --install --tool codex
./setup_tmux.sh --install
./setup_tmux_persistence.sh --install

# Run inside the new desktop session. This reloads themed components.
./setup_theme.sh --apply
```

The theme helper selects Tokyo Night and the original sunset wallpaper. The
wallpaper is byte-identical to Omarchy's shipped `1-sunset-lake.png`, so the repo
does not duplicate the image. The helper verifies its recorded SHA-256 and stops
if it is absent or different. No generated `omarchy/current` directory is copied.

TPM's other plugins, Neovim plugins, Treesitter parsers, Mason tools, and application
logins remain separate first-use/network actions. The Neovim lockfile does not
lock Mason tool versions. TPM itself and the two persistence plugins have pinned
installers. Other TPM plugins are not locked. The persistence helper installs
sources only; activation is a separate documented step.

See [development setup](docs/development.md) for providers, versions, cspell,
manual plugin steps, and the private Bash/Git override locations.

See [hardware setup](docs/hardware.md) before using the optional DisplayLink
helper. `setup_thunderbold.sh` remains only as a compatibility entry point to the
new, separately gated `setup_displaylink.sh`. Neither runs from `setup.sh`.

## Deliberately not copied

- Passwords, tokens, SSH/GPG keys, credentials, browser profiles, history, and
  authenticated application state. Credentials found in the old Bash startup
  were not copied. Use the ignored `~/.config/bash/local.sh` for private overrides,
  or an appropriate secrets manager.
- Downloaded binaries, Python entry points, virtual environments, runtime installs,
  caches, or absolute links to this machine's tools. The old `scripts/` tree stays
  on the source machine and is ignored by Git, not deleted.
- Private Pi credentials, model stores, sessions and runtime state. `--pi` clones
  the non-secret config from the private `Soyuz0/pi-config` repository rather than
  copying it into this public repo. Services and account enrollment remain separate.
- Media/VPN automation, library state, backups, mounts, network identities,
  gateways, Tailscale enrollment, Docker enablement, SSH exposure, or fan services.
  No system or user services are enabled by the main installer.
- Every installed application or AUR package. The desktop/development manifests
  cover configuration dependencies, and the opt-in apps manifest covers selected
  shortcuts. They are not the entire machine's software inventory.
- The older Zsh/apt/Homebrew installation under `~/Work/dotfiles`. It is not run or
  merged wholesale. Selected editor, cspell, and LazyGit additions were reviewed
  individually; its OS and shell installers are not used.

Git defaults contain no identity. Configure your name/email privately on the new
machine and authenticate Git, AI CLIs, and other applications manually. Existing
`~/.gitconfig` takes precedence over XDG Git preferences and is not replaced.

## Offline validation

See the [validation record](docs/validation.md) for checks performed and remaining
limits. Tests use temporary homes, inert provider stubs, and isolated Atuin and
headless Neovim checks without live startup configuration. They must not install
packages, fetch plugins, start desktop applications, or source live shell startup
files.

```bash
python3 -B -m unittest discover -s tests -v
for script in setup*.sh; do bash -n "$script" || exit 1; done

# Preview configuration against a disposable, empty home. No writes by preview.
mkdir -p /tmp/my-dotfiles-preview
./setup.sh --home /tmp/my-dotfiles-preview --dry-run --backup
```

`--home DIR` is for offline staging in an existing real directory. It skips the
Omarchy presence check and refuses `--packages`; it is not an OS-installation
mode. Do not point it at the repository, `/`, or a directory you do not own.
Staging creates links to the current clone, not a standalone portable archive.

Shell syntax and offline file-safety tests do not prove driver compatibility,
package availability on a later Arch snapshot, or a successful graphical login.
A full disposable fresh-Omarchy VM and actual dock/display checks remain the
final end-to-end validation steps.
