#!/usr/bin/env python3
"""Fixed, opt-in Omarchy cleanup. No recursive deletion or package expansion."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import ctypes
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys
from urllib.parse import urlsplit
import uuid

NATIVE = ("alacritty", "signal-desktop", "blueberry", "spotify")
WEB = {
    "Zoom": ("zoom.us", "app.zoom.us"),
    "HEY": ("hey.com", "app.hey.com"),
    "Basecamp": ("basecamp.com", "launchpad.37signals.com"),
    "Google Contacts": ("contacts.google.com",),
    "Google Messages": ("messages.google.com",),
    "Google Maps": ("maps.google.com", "www.google.com"),
    "X": ("x.com", "twitter.com"),
    "Figma": ("figma.com", "www.figma.com"),
    "Discord": ("discord.com",),
    "Fizzy": ("fizzy.do", "app.fizzy.do"),
}
APPLICATIONS = ".local/share/applications"
MIME = ".config/mimeapps.list"
STATE = ".local/state/dotfiles-omachy/cleanup"
ASSOCIATIONS = {b"Default Applications", b"Added Associations", b"Removed Associations"}
DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class CleanupError(Exception):
    pass


@dataclass(frozen=True)
class Snapshot:
    data: bytes
    identity: tuple

    def proof(self):
        return {"sha256": hashlib.sha256(self.data).hexdigest(),
                "stat": self.identity, "bytes": len(self.data)}

    def matches_claim(self, expected):
        # Moving the inode can change ctime, but not its bytes, inode, mode,
        # ownership, link count, size, or mtime. Compare all of those after capture.
        return self.data == expected.data and self.identity[:-1] == expected.identity[:-1]


class Home:
    """Use no-follow directory descriptors; never write through a redirected parent."""
    def __init__(self, path: Path):
        self.path = path
        if not path.is_absolute() or ".." in path.parts:
            raise CleanupError("HOME must be an absolute, non-redirected directory")
        self.uid = os.getuid()
        # Check every component, including HOME itself, without resolving symlinks.
        fd = os.open("/", DIRECTORY)
        try:
            for part in path.parts[1:]:
                next_fd = os.open(part, DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            self.check_directory(fd)
            self.identity = self.dir_identity(fd)
        except OSError as exc:
            raise CleanupError(f"Unsafe HOME {path}: {exc}") from exc
        finally:
            os.close(fd)

    def check_directory(self, fd):
        info = os.fstat(fd)
        if info.st_uid != self.uid or info.st_mode & 0o022:
            raise CleanupError("Home/target parent must be owned by this user and not writable by others")

    @staticmethod
    def dir_identity(fd):
        info = os.fstat(fd)
        return info.st_dev, info.st_ino

    @contextmanager
    def directory(self, relative="", create=False, private=False):
        fd = os.open("/", DIRECTORY)
        try:
            for part in self.path.parts[1:]:
                new_fd = os.open(part, DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = new_fd
            self.check_directory(fd)
            if self.dir_identity(fd) != self.identity:
                raise CleanupError("HOME changed since preflight")
            parts = Path(relative).parts
            if Path(relative).is_absolute() or ".." in parts:
                raise CleanupError("Unsafe relative path")
            for part in parts:
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                        os.fsync(fd)
                    except FileExistsError:
                        pass
                new_fd = os.open(part, DIRECTORY, dir_fd=fd)
                os.close(fd)
                fd = new_fd
                self.check_directory(fd)
            if private and stat.S_IMODE(os.fstat(fd).st_mode) != 0o700:
                raise CleanupError(f"Private state directory must have mode 0700: {relative}")
            yield fd
        finally:
            os.close(fd)

    def read(self, relative):
        path = Path(relative)
        try:
            with self.directory(str(path.parent)) as parent:
                return self.read_at(parent, path.name)
        except FileNotFoundError:
            return None

    def read_at(self, parent, name):
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        except FileNotFoundError:
            return None
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_uid != self.uid or before.st_nlink != 1:
                raise CleanupError(f"Not a regular, singly linked file owned by this user: {name}")
            with os.fdopen(os.dup(fd), "rb") as stream:
                data = stream.read()
            after = os.fstat(fd)
            def identity(s):
                return (s.st_dev, s.st_ino, s.st_uid, s.st_mode, s.st_nlink,
                        s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if identity(before) != identity(after):
                raise CleanupError(f"File changed while reading: {name}")
            return Snapshot(data, identity(after))
        finally:
            os.close(fd)

    def compare(self, relative, expected):
        if self.read(relative) != expected:
            raise CleanupError(f"Changed since preflight; preserving: {relative}")

    def existing_device(self, relative):
        """Find the filesystem that will contain a not-yet-created state path."""
        while True:
            try:
                with self.directory(relative) as fd:
                    return os.fstat(fd).st_dev
            except FileNotFoundError:
                relative = str(Path(relative).parent)


def rename_function():
    try:
        function = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise CleanupError("Linux renameat2(RENAME_NOREPLACE) is required; no unsafe fallback") from exc
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    return function


def rename_noreplace(source_fd, source, target_fd, target):
    """Atomically move a directory entry only if its destination is absent."""
    if rename_function()(source_fd, os.fsencode(source), target_fd, os.fsencode(target), 1):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), target)


def desktop_fields(data):
    """Read only the main group. Reject duplicate keys/groups and invalid encoding."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CleanupError("Desktop entry is not UTF-8") from exc
    active = False
    seen_group = False
    fields = {}
    for line in text.splitlines():
        line = line.lstrip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            active = line.rstrip() == "[Desktop Entry]"
            if active and seen_group:
                raise CleanupError("Duplicate Desktop Entry group")
            seen_group |= active
        elif active and "=" in line:
            key, value = line.split("=", 1)
            key = key.strip()
            if key in fields:
                raise CleanupError(f"Duplicate desktop key: {key}")
            fields[key] = value
    return fields


def recognized_exec(name, command):
    try:
        args = shlex.split(command)
        slug = name.lower().replace(" ", "-")
        if args == [f"omarchy-webapp-handler-{slug}", "%u"]:
            return True
        if len(args) != 2 or args[0] != "omarchy-launch-webapp":
            return False
        url = urlsplit(args[1])
        return (url.scheme == "https" and url.hostname in WEB[name]
                and not url.username and not url.password)
    except ValueError:
        return False


def clean_mime(data, desktop_ids):
    """Remove whole semicolon-list tokens only; leave all other bytes as supplied."""
    ids = {value.encode("utf-8") for value in desktop_ids}
    section = None
    result = []
    for line in data.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith(b"[") and stripped.endswith(b"]"):
            section = stripped[1:-1]
        elif (section in ASSOCIATIONS and stripped and not stripped.startswith((b"#", b";"))
              and b"=" in line):
            key, value = line.split(b"=", 1)
            body = value.rstrip(b"\r\n")
            ending = value[len(body):]
            tokens = body.split(b";")
            kept = [token for token in tokens if token.strip() not in ids]
            if len(tokens) != len(kept):
                line = key + b"=" + b";".join(kept) + ending
        result.append(line)
    return b"".join(result)


@dataclass
class Plan:
    files: dict
    changes: dict  # None means retain in journal only, bytes means publish replacement.
    installed: tuple


class Commands:
    def inventory(self):
        result = subprocess.run(["pacman", "-Qq"], capture_output=True, text=True, check=False)
        if result.returncode:
            raise CleanupError(f"pacman inventory failed: {result.stderr.strip()}")
        names = result.stdout.splitlines()
        if any(not re.fullmatch(r"[a-zA-Z0-9@_+.-]+", name) for name in names):
            raise CleanupError("Unrecognized pacman inventory output")
        return set(names)

    def remove(self, packages):
        args = ["sudo"]
        if not sys.stdin.isatty():
            args.append("-n")
        args += ["pacman", "-R", "--noconfirm", "--", *packages]
        # In a terminal sudo uses its normal prompt. No askpass or credential workaround.
        return subprocess.run(args, check=False).returncode


class Cleanup:
    def __init__(self, home, commands=None, system_dirs=None, out=print):
        self.home = Home(Path(home))
        self.commands = commands if commands is not None else Commands()
        self.system_dirs = (Path("/usr/local/share/applications"), Path("/usr/share/applications")) if system_dirs is None else system_dirs
        self.out = out

    def preflight(self, shortcuts_only=False):
        files = {}
        changes = {}
        # Validate all exact user entries before considering ANY mutation.
        for name in WEB:
            relative = f"{APPLICATIONS}/{name}.desktop"
            snapshot = self.home.read(relative)
            files[relative] = snapshot
            if snapshot is not None:
                fields = desktop_fields(snapshot.data)
                if (fields.get("Name") != name or fields.get("Type") != "Application"
                        or not recognized_exec(name, fields.get("Exec", ""))):
                    raise CleanupError(f"Ambiguous desktop entry; preserving all targets: {relative}")
                changes[relative] = None
        # An alias with the same Name is a collision, not another deletion target.
        try:
            with self.home.directory(APPLICATIONS) as parent:
                for filename in sorted(os.listdir(parent)):
                    if not filename.endswith(".desktop") or filename in {f"{n}.desktop" for n in WEB}:
                        continue
                    info = os.stat(filename, dir_fd=parent, follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        # A link could conceal a selected Name. Refuse rather than follow it.
                        raise CleanupError(f"Cannot rule out desktop Name collision: {filename}")
                    snapshot = self.home.read_at(parent, filename)
                    fields = desktop_fields(snapshot.data)
                    if fields.get("Name") in WEB:
                        raise CleanupError(f"Selected Name has an unsupported alias: {filename}")
        except FileNotFoundError:
            pass
        # Never remove a system launcher or reveal one underneath a user launcher.
        for directory in self.system_dirs:
            for name in WEB:
                path = directory / f"{name}.desktop"
                if os.path.lexists(path):
                    raise CleanupError(f"Unsupported system desktop; no system deletion or mask: {path}")
        mime = self.home.read(MIME)
        files[MIME] = mime
        if mime is not None:
            cleaned = clean_mime(mime.data, {f"{name}.desktop" for name in WEB})
            if cleaned != mime.data:
                changes[MIME] = cleaned
        # Validate state conflicts read-only even before package removal.
        try:
            with self.home.directory(STATE, private=True):
                pass
        except FileNotFoundError:
            pass
        if changes:
            rename_function()  # Fail closed if the required Linux primitive is unavailable.
            self.check_capture_devices(files, changes, self.home.existing_device(STATE))
        inventory = set() if shortcuts_only else self.commands.inventory()
        installed = tuple(p for p in NATIVE if p in inventory)
        return Plan(files, changes, installed)

    def check_capture_devices(self, files, changes, state_device):
        for relative in changes:
            with self.home.directory(str(Path(relative).parent)) as parent:
                if (os.fstat(parent).st_dev != state_device
                        or files[relative].identity[0] != state_device):
                    raise CleanupError(f"Cross-filesystem protected capture is unsupported: {relative}")

    def verify(self, plan):
        for relative, snapshot in plan.files.items():
            self.home.compare(relative, snapshot)

    def run(self, apply=False, shortcuts_only=False):
        plan = self.preflight(shortcuts_only)
        self.out("Native targets: " + ("skipped (--shortcuts-only)" if shortcuts_only else ", ".join(plan.installed) or "already absent"))
        for name in WEB:
            relative = f"{APPLICATIONS}/{name}.desktop"
            self.out(f"Web shortcut {name}: " + ("remove verified user entry" if relative in plan.changes else "already absent"))
        self.out("MIME associations: " + ("remove exact selected desktop-ID tokens" if MIME in plan.changes else "unchanged"))
        if not apply:
            self.out("Preview only. No files, packages, services or caches changed.")
            return 0
        if not plan.changes and not plan.installed:
            self.out("Already clean. No journal or other files written.")
            return 0
        with self.home.directory(STATE, create=True, private=True) as state_fd:
            try:
                fcntl.flock(state_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CleanupError("Another cleanup owns the state directory") from exc
            # Redo the whole preflight after acquiring the cleanup lock.
            current = self.preflight(shortcuts_only)
            if current != plan:
                raise CleanupError("Cleanup plan changed before intent; run preview again")
            self.verify(plan)
            journal = Journal(self.home, state_fd, plan)
            problems = []
            try:
                self.check_capture_devices(plan.files, plan.changes, os.fstat(journal.fd).st_dev)
                if plan.installed:
                    # One attempt only, followed by fresh inventory even on errors.
                    journal.event("package-intent", packages=list(plan.installed))
                    rc = None
                    error = None
                    try:
                        rc = self.commands.remove(plan.installed)
                    except (OSError, CleanupError) as exc:
                        error = str(exc)
                    try:
                        inventory = self.commands.inventory()
                        remaining = [p for p in NATIVE if p in inventory]
                    except (OSError, CleanupError) as exc:
                        remaining = None
                        error = f"{error or ''} Inventory reconciliation failed: {exc}".strip()
                    journal.event("package-result", returncode=rc, remaining=remaining, error=error)
                    if rc != 0 or remaining or remaining is None:
                        problems.append(f"Native removal incomplete or command failed (exit {rc}); fresh remaining inventory: {remaining}. {error or ''} No retry was attempted. Use a normal user terminal for sudo authentication or dependency errors.")
                # A package failure does not block independent, verified user shortcuts.
                self.verify(plan)
                # Recheck collisions and system entries too, including names absent at preview.
                fresh = self.preflight(shortcuts_only=True)
                if fresh.files != plan.files or fresh.changes != plan.changes:
                    raise CleanupError("Changed since preflight; preserving remaining file targets")
                for relative, replacement in plan.changes.items():
                    journal.event("file-intent", path=relative, before=plan.files[relative].proof(),
                                  after_sha256=None if replacement is None else hashlib.sha256(replacement).hexdigest())
                    self.mutate(relative, plan.files[relative], replacement, journal)
                    journal.event("file-complete", path=relative)
                journal.finish(("partial" if journal.changed else "failed") if problems else "complete", problems)
            except (OSError, CleanupError) as exc:
                problems.append(str(exc))
                journal.finish("partial" if journal.changed else "failed", problems)
            finally:
                journal.close()
            self.out(f"Journal and exact before-bytes: {self.home.path / journal.relative}")
            for problem in problems:
                self.out(problem)
            if not problems:
                self.out("Cleanup complete. No app data, icons or services changed.")
            return 1 if problems else 0

    def mutate(self, relative, expected, replacement, journal):
        path = Path(relative)
        item = journal.data["files"][relative]
        held = item["held"]
        with self.home.directory(str(path.parent)) as parent:
            if self.home.read_at(parent, path.name) != expected:
                raise CleanupError(f"Changed before mutation; preserving: {relative}")
            if os.fstat(parent).st_dev != os.fstat(journal.fd).st_dev:
                raise CleanupError(f"Cross-filesystem protected capture is unsupported: {relative}")
            authored = None
            if replacement is not None:
                authored = item["authored"]
                atomic(journal.fd, authored, replacement, stat.S_IMODE(expected.identity[3]))
            journal.event("capture-intent", path=relative, held=held)
            # This is the boundary, not the earlier comparison. Never unlink a
            # user's inode. Capture whichever inode is actually at the name.
            rename_noreplace(parent, path.name, journal.fd, held)
            journal.changed = True
            published = False
            try:
                os.fsync(journal.fd)
                os.fsync(parent)
                claimed = self.home.read_at(journal.fd, held)
                journal.event("capture-held", path=relative, held=held,
                              actual=None if claimed is None else claimed.proof())
                if claimed is None or not claimed.matches_claim(expected):
                    raise CleanupError(f"Changed at capture; current inode protected: {relative}")
                if replacement is not None:
                    journal.event("publish-intent", path=relative, authored=authored)
                    # Another writer's newly created target wins, even if it
                    # appears immediately before the rename system call.
                    rename_noreplace(journal.fd, authored, parent, path.name)
                    published = True
                    os.fsync(parent)
                    os.fsync(journal.fd)
                # Detect observed writes via pre-existing open FDs too. The
                # held inode stays protected even if a later write is unobserved.
                final_claim = self.home.read_at(journal.fd, held)
                if final_claim is None or not final_claim.matches_claim(expected):
                    raise CleanupError(f"Held inode changed during cleanup; retained: {relative}")
                after = self.home.read_at(parent, path.name)
                if replacement is None and after is not None:
                    raise CleanupError(f"New entry appeared after capture; preserving both: {relative}")
                if replacement is not None and (after is None or after.data != replacement):
                    raise CleanupError(f"MIME publication changed concurrently; preserving both: {relative}")
            except (OSError, CleanupError) as exc:
                # Retain the actual inode even on success, mismatch or failed
                # publication. Linking it back is atomic-if-absent, not restore
                # by overwrite, and never removes the journal's protected link.
                outcome = "not-restored-after-publication"
                if not published:
                    journal.event("restore-intent", path=relative, held=held)
                    try:
                        os.link(held, path.name, src_dir_fd=journal.fd,
                                dst_dir_fd=parent, follow_symlinks=False)
                        outcome = "linked-if-absent"
                        os.fsync(parent)
                        os.fsync(journal.fd)
                    except FileExistsError:
                        outcome = "occupied-preserved-both"
                    except OSError as restore_error:
                        outcome = f"held-only: {restore_error}"
                journal.event("capture-protected", path=relative, held=held, outcome=outcome,
                              error=str(exc))
                raise CleanupError(f"{relative}: {exc}. Protected inode: {journal.relative}/{held}; {outcome}") from exc


def atomic(parent, name, data, mode=0o600):
    temp = ".cleanup-" + uuid.uuid4().hex
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try:
            os.unlink(temp, dir_fd=parent)
        except FileNotFoundError:
            pass


class Journal:
    def __init__(self, home, state_fd, plan):
        run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex
        self.relative = f"{STATE}/{run_id}"
        os.mkdir(run_id, 0o700, dir_fd=state_fd)
        os.fsync(state_fd)
        self.fd = os.open(run_id, DIRECTORY, dir_fd=state_fd)
        self.changed = False
        self.data = {"status": "intent", "native": list(plan.installed), "files": {}, "events": []}
        try:
            for index, (relative, replacement) in enumerate(plan.changes.items()):
                snapshot = plan.files[relative]
                backup = f"{index:02d}.before"
                atomic(self.fd, backup, snapshot.data)
                self.data["files"][relative] = {"backup": backup, "before": snapshot.proof(),
                    "held": f"{index:02d}.held", "authored": f"{index:02d}.authored" if replacement is not None else None,
                    "action": "capture" if replacement is None else "replace"}
            self.save()  # All backups and intent are durable before the first mutation.
        except BaseException:
            os.close(self.fd)
            raise

    def save(self):
        atomic(self.fd, "manifest.json", (json.dumps(self.data, indent=2) + "\n").encode())

    def event(self, kind, **details):
        self.data["events"].append({"event": kind, **details})
        if kind == "package-result" and details.get("remaining") != self.data["native"]:
            self.changed = True
        self.save()

    def finish(self, status, problems):
        self.data.update(status=status, problems=problems)
        self.save()

    def close(self):
        os.close(self.fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--dry-run", action="store_true", help="read-only preview (default)")
    action.add_argument("--apply", action="store_true", help="apply the fixed authorized native and web targets")
    parser.add_argument("--shortcuts-only", action="store_true", help="skip all native package operations, including inventory")
    args = parser.parse_args(argv)
    try:
        return Cleanup(Path.home()).run(apply=args.apply, shortcuts_only=args.shortcuts_only)
    except (CleanupError, OSError) as exc:
        print(f"Cleanup refused/incomplete: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
