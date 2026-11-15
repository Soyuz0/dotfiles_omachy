# Mac mini T2 reference profile

This directory is optional data for an Apple Mac mini 2018, DMI model `Macmini8,1`. It is not a Stow package or a hardware installer. The normal setup profile must remain generic. Selecting `--machine macmini-t2` in the main setup only selects this directory's `monitors.conf`; it must not run hardware setup, install packages, copy `/etc` files, or control services. See [hardware instructions](../../docs/hardware.md).

## Monitor snapshot

`monitors.conf` is a byte-for-byte snapshot of the readable live `~/.config/hypr/monitors.conf` taken during this change. The original was not edited. Its SHA-256 is:

```text
bf04db8941b108fa359483d5b6f3e89934be2e97802d707e5bcc8c77844b600d
```

It contains a connector-specific `DVI-I-2` setting for 3440x1440 at 100 Hz, plus the original comments and scaling setting. Connector names can change after a dock or driver change. Review it against `hyprctl monitors` before selecting the profile. It contains no monitor serial/EDID data. The snapshot preserves user content; it is not proof the dock was connected during the audit.

## Optional templates

Files ending in `.example` are never automatically applied.

- `modprobe.d/hid_apple.conf.example` preserves the local `fnmode=2` keyboard preference.
- `modules-load.d/t2.conf.example` lists the two modules found in the live T2 configuration. Verify both against the running kernel first.
- `modprobe.d/usb-autosuspend.conf.example` documents the live global workaround but leaves it commented out. Prefer a scoped device rule.
- `modprobe.d/brcmfmac.conf.example` leaves a locally observed Wi-Fi workaround commented out. Its source comment referred to a MacBook; this audit did not establish that the Mac mini needs it.
- `udev/dock-keep-awake.rules.example` is an inactive, sanitized pattern. It intentionally excludes all local device IDs and controller paths. Replace the placeholders only after local review.

Do not blanket-copy this directory into `/etc`. Do not disable or replace existing fan control, modprobe rules, dock helpers, or services while preparing a reinstall. Save private machine-specific records separately, with restricted access.

## Fan control is not portable

The readable local fan unit runs `/usr/local/bin/macmini-fancurve`. Its script hard-codes a sysfs controller path and a numbered `hwmon` temperature source. Both minimum and maximum RPM are 5000, so its apparent curve is clamped to that value. Its stop handler restores automatic control through another fixed path. These are not safe fresh-install defaults.

No executable fan script or service is supplied. For a fresh installation, first verify automatic fan operation, sensor identity, valid RPM limits, and a reliable automatic-control fallback. Review a maintained T2 fan solution and its current documentation separately. Never enable two fan controllers, stop a working controller just to prepare files, or assume numbered `hwmon` paths survive a reboot.

## Audit boundary

The audit read only named hardware settings, the fan unit/script, the dock keep-awake rule, kernel/header metadata, package metadata, module metadata, and monitor configuration. It did not copy board identifiers, USB IDs, PCI addresses, network settings, mounts, secrets, or unrelated service contents. No denied path was bypassed. Installed packages and service state are observations, not a reproducible package lock or runtime compatibility guarantee.
