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
Git and Python 3 must be available. The updated setup is on `sidebar`; the clone
command selects it explicitly because the remote default branch is still `main`.

```bash
git clone --branch sidebar https://github.com/Soyuz0/dotfiles_omachy.git ~/dotfiles_omachy
cd ~/dotfiles_omachy

# Inspect every proposed file replacement and package selection first.
./setup.sh --dry-run --backup --packages

# Install declared packages, preserve conflicts, and install configuration links.
./setup.sh --backup --packages
```

Without `--packages`, the script changes configuration only. To include the
optional applications referenced by the saved shortcuts, use `--packages --apps`
in both the preview and actual commands. `packages/apps.txt` includes Spotify,
Obsidian, Typora, 1Password, Signal, media/file tools, and Docker. Installing Docker
does not enable its service or change group membership. The script never installs
TPM, plugins, AI tools, drivers, or services as a side effect.

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
- Tmux configuration, including optional rather than mandatory private Pi includes.
- A Bash customization hook added after the target's existing Omarchy startup.
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
packages or undo actions you explicitly run through the optional helpers.

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
./setup_theme.sh --dry-run

# Explicit network/tool installation, not part of setup.sh:
./setup_dev.sh --install --tool node
./setup_dev.sh --install --tool prettier --tool cspell
./setup_dev.sh --install --tool codex
./setup_tmux.sh --install

# Run inside the new desktop session. This reloads themed components.
./setup_theme.sh --apply
```

The theme helper selects Tokyo Night and the original sunset wallpaper. The
wallpaper is byte-identical to Omarchy's shipped `1-sunset-lake.png`, so the repo
does not duplicate the image. The helper verifies its recorded SHA-256 and stops
if it is absent or different. No generated `omarchy/current` directory is copied.

TPM's other plugins, Neovim plugins, Treesitter parsers, Mason tools, and application
logins remain separate first-use/network actions. The Neovim lockfile does not
lock Mason tool versions. TPM itself is pinned; its plugin list is not.

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
- Private Pi configuration and its services. Restore those separately from the
  private `Soyuz0/pi-config` repository and follow its own setup documentation.
- Media/VPN automation, library state, backups, mounts, network identities,
  gateways, Tailscale enrollment, Docker enablement, SSH exposure, or fan services.
  No system or user services are enabled by the main installer.
- Every installed application or AUR package. The desktop/development manifests
  cover configuration dependencies, and the opt-in apps manifest covers selected
  shortcuts. They are not the entire machine's software inventory.
- The older Zsh/apt/Homebrew installation under `~/Work/dotfiles`. It is not run or
  merged wholesale. Only reviewed portable cspell inputs were used.

Git defaults contain no identity. Configure your name/email privately on the new
machine and authenticate Git, AI CLIs, and other applications manually. Existing
`~/.gitconfig` takes precedence over XDG Git preferences and is not replaced.

## Offline validation

See the [validation record](docs/validation.md) for checks performed and remaining
limits. The test suite uses only temporary homes and inert command stubs. It must not
install packages, fetch plugins, start desktop applications, or source live shell
startup files.

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
