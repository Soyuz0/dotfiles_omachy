# Optional hardware setup

The normal dotfiles installation is generic. A machine profile is not permission to change the kernel, drivers, `/etc`, services, or power management. The main setup's `--machine macmini-t2` option must only select `profiles/macmini-t2/monitors.conf` as the stored monitor template. It must not invoke the helper below. Hardware preparation stays a separate, explicit task.

The older misspelled `setup_thunderbold.sh` name is retained only as a wrapper. It passes arguments unchanged to `setup_displaylink.sh` using the wrapper's own directory, even when called from another working directory. This is DisplayLink USB graphics setup, not general Thunderbolt configuration.

## Preview first

Run from the repository root:

```bash
bash setup_displaylink.sh
bash setup_displaylink.sh --dry-run
bash setup_thunderbold.sh --dry-run
bash setup_displaylink.sh --help
```

No flags means a read-only preview. `--dry-run` also overrides either action, regardless of argument order. Preview never calls `sudo`, writes packages or configuration, compiles a module, loads a module, or changes services. It uses local metadata only and makes no network requests.

A preview exits 0 after reporting its findings, even when it prints `BLOCKED`. That exit code means the preview completed, not that the hardware is ready. Unknown flags or combined/repeated actions exit 2. A real action with failed prerequisites exits 1. A failed privileged command propagates failure rather than being ignored.

## What the helper checks

Actions require:

- Arch Linux (`ID=arch`) on x86_64, plus a connected, readable DisplayLink USB vendor in sysfs. A Targus name alone is not detection. A vendor match does not certify a particular chipset.
- A recognized installed kernel package base: `linux`, `linux-lts`, `linux-zen`, `linux-hardened`, `linux-t2`, or `linux-t2-lts`. This is a package-name allowlist, not a promise that EVDI supports every release of those kernels.
- For Apple hardware, the reviewed model `Macmini8,1`. That model requires a T2 package base. T2 package bases require that Apple model and a release string containing `t2`. Other Apple models, missing metadata, and unknown/custom package bases refuse actions. There is no force or skip-checks option.
- Headers in `/usr/lib/modules/$(uname -r)/build`, with a nonempty Makefile, kernel configuration, Module.symvers, generated UTS release, and kernel.release. Both recorded releases must exactly equal `uname -r`, and the configuration must support modules. Pacman's ownership and exact installed version must agree for the kernel and its corresponding `-headers` package. A similarly named header package is not enough.
- Exactly one local `/usr/src/evdi-*/dkms.conf`, owned by a recognized installed EVDI package. The script reads the directory's version but never sources that configuration itself. DKMS will execute the configuration during an explicitly requested build, so package ownership alone is not a security review.
- Installed `dkms`, `modinfo`, `pacman`, and `systemctl`, along with the installed `displaylink` package, its owned executable, and its owned service unit. Building also requires local `make` and `gcc`.

Preview and service activation inspect the installed EVDI module's filename and first vermagic field for the exact running release. `--install` may run when that module is absent so it can build it. No check substitutes another kernel's module or headers. Activation additionally requires the expected loaded packaged service unit, an empty `DropInPaths` property, and the exact DKMS installed record for this EVDI version, running kernel, and architecture. A nonempty `DropInPaths` or a failed property query blocks activation, including in an activation dry-run. The helper does not review or remove drop-ins; manage a customized service separately after reviewing its effective configuration.

These checks reject missing or unknown ABI information. They do not establish full ABI compatibility, source safety, module signing acceptance, successful module loading, correct output, suspend behavior, or a particular EVDI/kernel combination's upstream support. A package appearing in pacman's database is not a compatibility test.

## Manual prerequisites and explicit actions

First choose a kernel and exact matching headers through your existing trusted, signature-checked package configuration. On T2 hardware, verify the current T2 installation instructions, firmware requirements, and package provenance yourself. If an update leaves installed files out of sync with the running kernel, boot a matching kernel/header pair before continuing.

Obtain and review the EVDI and DisplayLink package recipes, upstream sources, install hooks, dependencies, and service definitions manually. An AUR recipe is not automatically reviewed or trusted. If multiple EVDI source versions remain installed, resolve that ambiguity yourself. This helper does not choose the newest version, remove packages, select an AUR helper, or provide an automatic AUR installation command.

The helper never adds repositories, changes signature policy, refreshes package databases, upgrades the system, downloads packages, removes drivers, stops/disables services, or runs `dkms autoinstall` across kernels. The previous script's unsigned repository configuration and forced driver removal are gone.

After reviewing the already installed source, an optional build is:

```bash
# Inspect the intended build without privilege or changes first.
bash setup_displaylink.sh --install --dry-run

# MUTATING: builds/installs only the one local EVDI source for uname -r.
bash setup_displaylink.sh --install
```

`--install` means a local `sudo dkms install -m evdi -v <detected-version> -k <running-release>`, not a package installation. It does not force/rebuild an already installed version, load the module, stop a running service, or enable anything. DKMS may run its normal build/signing hooks. Review those locally. Compilation errors are fatal. Post-build checks require matching vermagic and a module filename under `/usr/lib/modules/<running-release>/` or `/lib/modules/<running-release>/`. A matching vermagic with a filename outside those exact running-kernel trees fails. On failure, inspect the DKMS log under `/var/lib/dkms/evdi/` and preserve the working drivers and service; the helper performs no removal or rollback.

Only after reviewing the build, module-signing requirements, and effective service configuration:

```bash
bash setup_displaylink.sh --enable-service --dry-run

# MUTATING: separately enables and starts the packaged service.
bash setup_displaylink.sh --enable-service
```

`--enable-service` and `--install` cannot be combined. Activation runs `sudo systemctl enable --now displaylink.service` and checks that it is active. The packaged service may load EVDI itself and perform its declared dependencies/conflicts. The helper does not stop services as preparation and never restarts an already active service. If activation fails, it does not pretend success or automatically undo the requested enablement. Inspect the actual state and journal. A DKMS installed record is an additional activation-time check, not something the preview fabricates.

Verify the physical displays, `hyprctl monitors`, and the service journal after an actual activation. A service being active does not prove the screens work. No runtime activation was performed during this dotfiles update.

## Mac mini T2 templates

See [`profiles/macmini-t2/README.md`](../profiles/macmini-t2/README.md) for the monitor snapshot checksum and individual template notes. The profile contains no automatic installer.

Before applying anything, confirm the model locally using the readable DMI vendor and product files. Do not infer a match from a hostname. Compare each proposed file with the current `/etc` file and record a private backup. Never overwrite an existing custom rule just because an example exists.

For example, these are optional commands for a later, separately reviewed maintenance task. They were not run during this update:

```bash
# Read-only checks first. Both modules must match the current T2 kernel.
modinfo -k "$(uname -r)" apple-bce
modinfo -k "$(uname -r)" hci_bcm4377
modinfo -k "$(uname -r)" hid_apple

# ONLY after comparing existing contents and approving the changes.
# --backup=numbered retains an existing destination rather than discarding it.
sudo install -Dm644 --backup=numbered \
  profiles/macmini-t2/modules-load.d/t2.conf.example /etc/modules-load.d/t2.conf
sudo install -Dm644 --backup=numbered \
  profiles/macmini-t2/modprobe.d/hid_apple.conf.example /etc/modprobe.d/hid_apple.conf
```

Installing those files does not validate that the machine needs them. Existing T2 configurations may already load the modules automatically. Modprobe changes apply to future module loads; do not unload active hardware drivers to test them. Arrange a maintenance reboot if required by the kernel/initramfs configuration, not an automatic live reload from dotfiles setup.

The global USB autosuspend and Broadcom Wi-Fi examples are comments only. The live Wi-Fi comment described a MacBook workaround, so no Mac mini recommendation is inferred. The dock udev example is also inactive and omits actual USB IDs and PCI paths. Collect any required IDs locally and keep that machine-specific record private. Do not apply broad power rules, trigger all udev devices, reset USB, rebind controllers, or force reconnects during setup.

The audited fan controller is deliberately not reproduced as an executable template. Its fixed sensor/controller paths and 5000-RPM clamp are not safe portable defaults. Keep a working fan service in place while researching a fresh-install replacement, verify automatic fan fallback, and never run competing fan controllers.

## Local audit observations and limits

The readable machine reported Apple `Macmini8,1`, kernel `6.18.7-arch1-Watanare-T2-1-t2`, package base `linux-t2`, and matching `linux-t2`/`linux-t2-headers` versions `6.18.7-1`. Local metadata listed `evdi-dkms-git 1.14.16.r4.gcf0e2ad-1` and `displaylink 6.3-2`. The EVDI module's release field matched the running release, and DKMS listed an installed build for that release. These are observations, not pinned install instructions or a compatibility endorsement.

The readable USB inventory did not expose a DisplayLink vendor during the audit. The helper therefore reports a blocker on this machine until it can detect a dock. It does not bypass restricted paths or use the existing monitor configuration as proof of attached hardware. No package installation, privileged operation, network access, service change, desktop reload, or live `/etc` change was performed. The monitor file was copied into the profile without editing its live source. Private device identifiers, network data, mounts, and unrelated service configuration are not included.
