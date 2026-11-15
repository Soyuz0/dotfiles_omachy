#!/usr/bin/env bash
# Optional local EVDI build and separately requested DisplayLink service activation.
# No package downloads, repository edits, driver removal, or service preparation.
set -euo pipefail

usage() {
    printf '%s\n' \
        'Usage: bash setup_displaylink.sh [--dry-run] [--install | --enable-service]' \
        '' \
        'No flags: read-only preview. --dry-run also overrides either action.' \
        '--install         Build/install ONE already installed, manually reviewed EVDI' \
        '                  DKMS source for the running kernel. No packages are fetched.' \
        '--enable-service  Separately enable and start displaylink.service, only after' \
        '                  installed module, header, package, and hardware checks pass.' \
        '--help, -h        Show this help.' \
        '' \
        'Actions are mutually exclusive. Unsupported/ambiguous prerequisites refuse' \
        'actions; preview reports blockers without changing anything. See docs/hardware.md.'
}

action=preview
dry_run=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) dry_run=true ;;
        --install|--enable-service)
            if [[ "$action" != preview ]]; then
                printf 'Choose one action per invocation.\n' >&2
                exit 2
            fi
            action=${arg#--}
            ;;
        --help|-h) usage; exit 0 ;;
        *) printf 'Unknown argument: %s\n' "$arg" >&2; usage >&2; exit 2 ;;
    esac
done

blockers=()
block() { blockers+=("$*"); }
have() { command -v "$1" >/dev/null 2>&1; }
owner() { pacman -Qqo -- "$1" 2>/dev/null; }
package_version() { pacman -Q -- "$1" 2>/dev/null | awk '{print $2}'; }

kernel=$(uname -r)
arch=$(uname -m)
build=/usr/lib/modules/$kernel/build
pkgbase=''
source_version=''
printf 'DisplayLink preview for running kernel %s (%s)\n' "$kernel" "$arch"
printf 'Requested action: %s; explicit dry-run: %s\n' "$action" "$dry_run"
printf 'No package manager writes, repository changes, removals, or service stops are supported.\n'

[[ "$arch" == x86_64 ]] || block 'Only x86_64 has been considered by this helper.'
if [[ ! -r /etc/os-release ]] || ! grep -qx 'ID=arch' /etc/os-release; then
    block 'Only Arch Linux is supported; no derivative/other-distribution fallback.'
fi
for tool in pacman modinfo dkms systemctl; do
    have "$tool" || block "Missing tool: $tool. Install reviewed prerequisites manually."
done

# Read only vendor/product names, never serial numbers or board/device identifiers.
vendor=''
model=''
[[ ! -r /sys/class/dmi/id/sys_vendor ]] || vendor=$(</sys/class/dmi/id/sys_vendor)
[[ ! -r /sys/class/dmi/id/product_name ]] || model=$(</sys/class/dmi/id/product_name)
if [[ "$vendor" == Apple* && "$model" != Macmini8,1 ]]; then
    block 'This helper has no reviewed Apple hardware profile for this model.'
fi
usb_found=false
for vendor_file in /sys/bus/usb/devices/*/idVendor; do
    if [[ -r "$vendor_file" && "$(<"$vendor_file")" == 17e9 ]]; then
        usb_found=true
    fi
done
if [[ "$usb_found" == true ]]; then
    printf 'DisplayLink USB vendor detected. This does not verify a chipset/driver combination.\n'
else
    block 'No readable DisplayLink USB vendor detected. Connect the dock; do not force detection.'
fi

if [[ -r /usr/lib/modules/$kernel/pkgbase ]]; then
    pkgbase=$(<"/usr/lib/modules/$kernel/pkgbase")
fi
case "$pkgbase" in
    linux|linux-lts|linux-zen|linux-hardened) ;;
    linux-t2|linux-t2-lts)
        [[ "$vendor" == Apple* && "$model" == Macmini8,1 && "$kernel" == *t2* ]] ||
            block 'T2 package base requires detected Apple Macmini8,1 and a T2 kernel release.'
        ;;
    *) block 'Unknown or missing kernel package base. No header-name or ABI fallback is allowed.' ;;
esac
if [[ "$vendor" == Apple* && "$model" == Macmini8,1 && "$pkgbase" != linux-t2 && "$pkgbase" != linux-t2-lts ]]; then
    block 'Macmini8,1 requires a reviewed T2 kernel/header pair, not generic fallback headers.'
fi
printf 'Kernel package base: %s\n' "${pkgbase:-unknown}"

for file in Makefile .config Module.symvers include/config/kernel.release include/generated/utsrelease.h; do
    [[ -r "$build/$file" && -s "$build/$file" ]] || block "Missing/empty matching header artifact: $file"
done
if [[ ! -r "$build/include/config/kernel.release" ]] || [[ "$(<"$build/include/config/kernel.release")" != "$kernel" ]]; then
    block 'Header kernel.release does not exactly match uname -r.'
fi
if [[ ! -r "$build/include/generated/utsrelease.h" ]] || ! grep -Fxq "#define UTS_RELEASE \"$kernel\"" "$build/include/generated/utsrelease.h"; then
    block 'Generated UTS_RELEASE does not exactly match the running kernel.'
fi
if [[ ! -r "$build/.config" ]] || ! grep -qx 'CONFIG_MODULES=y' "$build/.config"; then
    block 'Matching kernel configuration with CONFIG_MODULES=y is required.'
fi
if have pacman && [[ -n "$pkgbase" ]]; then
    kernel_owner=$(owner "/usr/lib/modules/$kernel/pkgbase" || true)
    header_owner=$(owner "$build/Makefile" || true)
    kernel_version=$(package_version "$pkgbase" || true)
    header_version=$(package_version "$pkgbase-headers" || true)
    if [[ "$kernel_owner" != "$pkgbase" || "$header_owner" != "$pkgbase-headers" || -z "$kernel_version" || "$kernel_version" != "$header_version" ]]; then
        block 'Kernel/header package owners or installed versions differ. Select the exact pair manually.'
    fi
fi

# Refuse multiple source versions rather than guessing the latest. Do not source dkms.conf.
sources=()
for conf in /usr/src/evdi-*/dkms.conf; do
    [[ ! -r "$conf" ]] || sources+=("$conf")
done
if (( ${#sources[@]} != 1 )); then
    block 'Exactly one installed EVDI DKMS source is required; missing/ambiguous sources need manual review.'
else
    source_dir=${sources[0]%/dkms.conf}
    source_version=${source_dir#/usr/src/evdi-}
    if [[ ! "$source_version" =~ ^[[:alnum:]][[:alnum:].+_~-]*$ ]]; then
        block 'Unrecognized EVDI source version format.'
    fi
    if have pacman; then
        source_owner=$(owner "${sources[0]}" || true)
        case "$source_owner" in
            evdi|evdi-dkms|evdi-dkms-git|evdi-git|evdi-compat-git) ;;
            *) block 'EVDI DKMS source is not owned by a recognized installed EVDI package.' ;;
        esac
    fi
    printf 'Local EVDI source version: %s. Package ownership is NOT a source review or compatibility proof.\n' "$source_version"
fi

if have pacman; then
    if ! pacman -Q displaylink >/dev/null 2>&1 ||
       [[ ! -x /usr/lib/displaylink/DisplayLinkManager ]] ||
       [[ "$(owner /usr/lib/displaylink/DisplayLinkManager || true)" != displaylink ]] ||
       [[ "$(owner /usr/lib/systemd/system/displaylink.service || true)" != displaylink ]]; then
        block 'Installed displaylink package, owned manager executable, and owned service unit are required.'
    fi
fi

# A failed build is never ignored. --install does not require a pre-existing module.
module_ok=false
if have modinfo; then
    vermagic=$(modinfo -k "$kernel" -F vermagic evdi 2>/dev/null || true)
    module_path=$(modinfo -k "$kernel" -F filename evdi 2>/dev/null || true)
    if [[ "${vermagic%% *}" == "$kernel" && ( "$module_path" == /usr/lib/modules/"$kernel"/* || "$module_path" == /lib/modules/"$kernel"/* ) ]]; then
        module_ok=true
        printf 'Installed EVDI release matches uname -r; runtime compatibility is still unverified.\n'
    fi
fi
if [[ "$action" != install && "$module_ok" != true ]]; then
    block 'No installed EVDI module with an exact running-kernel vermagic/path match. Review/build first.'
fi
if [[ "$action" == install ]]; then
    for tool in make gcc; do
        have "$tool" || block "Missing local build prerequisite: $tool"
    done
fi
if [[ "$action" == enable-service ]] && have systemctl; then
    load_state=$(systemctl show displaylink.service -p LoadState --value 2>/dev/null || true)
    fragment=$(systemctl show displaylink.service -p FragmentPath --value 2>/dev/null || true)
    if [[ "$load_state" != loaded || "$fragment" != /usr/lib/systemd/system/displaylink.service ]]; then
        block 'Service is missing, masked, overridden, or not the expected packaged unit. Review it manually.'
    fi
    if ! drop_ins=$(systemctl show displaylink.service -p DropInPaths --value 2>/dev/null); then
        block 'Cannot verify service DropInPaths. Service activation requires a verified absence of drop-ins.'
    elif [[ -n "$drop_ins" ]]; then
        block 'Service has drop-ins. Refusing activation of an overridden packaged unit; review it manually.'
    fi
fi

printf '\nManual prerequisites: obtain the EXACT running-kernel headers through your trusted,\nsignature-checked configuration. Review any EVDI/DisplayLink PKGBUILD, sources, hooks,\nand service/drop-ins before installing them yourself. This helper never runs an AUR\nhelper or claims that a package version supports your kernel. Reboot into a matching\nkernel/header pair when needed; do not substitute generic headers for a T2 kernel.\n'
if (( ${#blockers[@]} )); then
    printf '\nBLOCKED: %s\n' "${blockers[@]}"
    if [[ "$action" != preview && "$dry_run" != true ]]; then
        exit 1
    fi
    printf '\nPreview only. No action would be allowed with these blockers.\n'
    exit 0
fi

if [[ "$action" == preview || "$dry_run" == true ]]; then
    printf '\nRead-only checks passed. No changes made.\n'
    printf 'Explicit --install would run: sudo dkms install -m evdi -v %q -k %q\n' "$source_version" "$kernel"
    printf 'Separate --enable-service would verify the DKMS record, then enable/start displaylink.service.\n'
    printf 'These checks do not prove module loadability, signing acceptance, or correct video output.\n'
    exit 0
fi

have sudo || { printf 'Missing sudo; no action taken.\n' >&2; exit 1; }
if [[ "$action" == install ]]; then
    printf 'Building locally installed source. Use this action only after reviewing that source.\n'
    sudo dkms install -m evdi -v "$source_version" -k "$kernel"
    vermagic=$(modinfo -k "$kernel" -F vermagic evdi)
    module_path=$(modinfo -k "$kernel" -F filename evdi)
    [[ "${vermagic%% *}" == "$kernel" && ( "$module_path" == /usr/lib/modules/"$kernel"/* || "$module_path" == /lib/modules/"$kernel"/* ) ]] || { printf 'Post-build vermagic/path mismatch. Service left unchanged.\n' >&2; exit 1; }
    printf 'Module installed for the exact release; no module loaded and no service changed.\n'
    printf 'Inspect DKMS logs and signing requirements, then separately request --enable-service.\n'
else
    # Only an exact DKMS installed record is accepted, not merely another kernel's build.
    status=$(dkms status -m evdi -v "$source_version" -k "$kernel")
    if ! grep -Fxq "evdi/$source_version, $kernel, $arch: installed" <<< "$status"; then
        printf 'No exact installed DKMS record. Service left unchanged.\n' >&2
        exit 1
    fi
    sudo systemctl enable --now displaylink.service
    systemctl is-active --quiet displaylink.service
    printf 'Service enabled and active. Verify actual display output and journal logs manually.\n'
fi
