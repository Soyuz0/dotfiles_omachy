#!/usr/bin/env bash
# bootstrap_arch_machine.sh

set -euo pipefail

DOTFILES_DIR="$HOME/dotfiles_omachy"
PKGS=(stow git neovim curl wget base-devel make ripgrep unzip xclip tmux zsh fzf zoxide npm gcc ghostty)

msg() { printf "\n[+] %s\n" "$1"; }

# Detect the actual stow target path for a package
# Example: hypr/.config/hypr/hyprland.conf → ~/.config/hypr
get_target_dir() {
    local pkg_dir="$1"
    local first_file

    # Find any file inside the package
    first_file=$(find "$pkg_dir" -type f | head -n 1)
    [ -z "$first_file" ] && return 0

    # Strip dotfiles root, leave the target path
    local relative="${first_file#$pkg_dir}"
    local target_parent="$(dirname "$relative")"

    # Return target under $HOME
    printf "%s/%s\n" "$HOME" "$target_parent"
}

# ---------------------------------------------------------
msg "Updating system"
sudo pacman -Syu --noconfirm

msg "Installing packages"
sudo pacman -S --needed --noconfirm "${PKGS[@]}"

# ---------------------------------------------------------
msg "Checking dotfiles repo"
if [ ! -d "$DOTFILES_DIR" ]; then
    echo "Dotfiles repo missing at $DOTFILES_DIR"
    exit 1
fi

cd "$DOTFILES_DIR"

# ---------------------------------------------------------
msg "Preparing stow targets (deleting conflicting folders)"

for pkg in */ ; do
    pkg_name="${pkg%/}"
    pkg_path="$DOTFILES_DIR/$pkg_name"

    target_dir="$(get_target_dir "$pkg_path")"

    if [ -n "$target_dir" ] && [ -d "$target_dir" ] && [ ! -L "$target_dir" ]; then
        msg "Removing conflicting directory: $target_dir"
        rm -rf "$target_dir"
    fi
done

# ---------------------------------------------------------
msg "Stowing all packages"
for pkg in */ ; do
    pkg_name="${pkg%/}"
    msg "Stowing: $pkg_name"
    stow -R "$pkg_name"
done

# ---------------------------------------------------------
# Remove unwanted packages if present
# ---------------------------------------------------------
UNINSTALL_PKGS=(
    alacritty
)

msg "Removing unwanted terminal packages (if installed)"

for pkg in "${UNINSTALL_PKGS[@]}"; do
    if pacman -Q "$pkg" >/dev/null 2>&1; then
        msg "Removing: $pkg"
        sudo pacman -Rns --noconfirm "$pkg"
    else
        msg "$pkg not installed, skipping"
    fi

    # Cleanup possible leftover config dirs
    rm -rf "$HOME/.config/$pkg" || true
done

hyprctl reload

msg "Bootstrap complete 🎉"

