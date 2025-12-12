#!/usr/bin/env bash
# displaylink_fix_headers_repo.sh
# Fix DisplayLink on Arch when evdi module is missing due to missing kernel headers repo (T2 Macs).

set -euo pipefail

log() { printf "\n==> %s\n" "$*"; }

KVER="$(uname -r)"
PKGBASE_FILE="/usr/lib/modules/${KVER}/pkgbase"
PACMAN_CONF="/etc/pacman.conf"

log "Kernel: ${KVER}"

log "Stop DisplayLink service (avoid restart spam)"
sudo systemctl disable --now displaylink.service >/dev/null 2>&1 || true

add_arch_mact2_repo() {
  if grep -qE '^\[arch-mact2\]' "$PACMAN_CONF"; then
    log "[arch-mact2] repo already present"
    return 0
  fi

  log "Adding [arch-mact2] repo to ${PACMAN_CONF}"
  # t2linux wiki install guide shows this repo block. :contentReference[oaicite:1]{index=1}
  sudo tee -a "$PACMAN_CONF" >/dev/null <<'EOF'

[arch-mact2]
Server = https://mirror.funami.tech/arch-mact2/os/x86_64
SigLevel = Never
EOF
}

log "Update system + tools"
sudo pacman -Syu --noconfirm
sudo pacman -S --needed --noconfirm base-devel git dkms

if [[ ! -f "${PKGBASE_FILE}" ]]; then
  echo "Missing ${PKGBASE_FILE}. Can't infer kernel pkgbase."
  echo "Still continuing, but header install may need manual selection."
  PKGBASE=""
else
  PKGBASE="$(cat "${PKGBASE_FILE}")"
  log "Detected kernel pkgbase: ${PKGBASE}"
fi

# If this looks like a T2 kernel, ensure the T2 repo is configured.
if [[ "${KVER}" == *t2* || "${PKGBASE}" == *t2* ]]; then
  add_arch_mact2_repo
  log "Refresh pacman DB"
  sudo pacman -Syy --noconfirm
fi

install_headers() {
  local candidate="$1"
  if [[ -z "$candidate" ]]; then return 1; fi
  if sudo pacman -Si "${candidate}" >/dev/null 2>&1; then
    log "Installing headers: ${candidate}"
    sudo pacman -S --needed --noconfirm "${candidate}"
    return 0
  fi
  return 1
}

log "Install matching kernel headers"
HEADERS_OK=0
if [[ -n "${PKGBASE}" ]]; then
  install_headers "${PKGBASE}-headers" && HEADERS_OK=1 || true
fi

if [[ "${HEADERS_OK}" -ne 1 ]]; then
  # fallback for common names
  install_headers linux-t2-headers && HEADERS_OK=1 || true
fi

if [[ "${HEADERS_OK}" -ne 1 ]]; then
  echo "Could not find matching headers via pacman."
  echo "Check your kernel pkgbase: ${PKGBASE:-<unknown>}"
  echo "and available headers with: pacman -Ss 'headers' | grep -i t2"
  exit 1
fi

log "Ensure AUR helper (yay/paru) exists"
AUR=""
command -v yay >/dev/null 2>&1 && AUR="yay" || true
command -v paru >/dev/null 2>&1 && AUR="${AUR:-paru}" || true
if [[ -z "$AUR" ]]; then
  echo "No AUR helper (yay/paru). Install one, then re-run."
  exit 1
fi
log "Using: $AUR"

log "Install evdi via DKMS + DisplayLink userspace"
$AUR -Rns --noconfirm evdi evdi-git evdi-compat-git >/dev/null 2>&1 || true
$AUR -S --noconfirm --needed evdi-dkms displaylink

log "Build/load evdi"
sudo dkms autoinstall || true
sudo modprobe evdi

log "Start DisplayLink service"
sudo systemctl enable --now displaylink.service
sudo systemctl --no-pager --full status displaylink.service || true

log "If it still fails: check 'dkms status' and '/var/lib/dkms/evdi/*/build/make.log'"

