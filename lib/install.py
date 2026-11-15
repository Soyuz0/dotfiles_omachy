#!/usr/bin/env python3
"""Small, explicit dotfile installer. No Stow adoption or directory deletion."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import stat
import subprocess
import sys
import tempfile
import uuid

REPO = Path(__file__).resolve().parents[1]
ROOTS = (
    "hypr/.config/hypr", "ghostty/.config/ghostty", "waybar/.config/waybar",
    "nvim/.config/nvim", "tmux/.config/tmux", "bash/.config/bash",
    "git/.config/git", "mise/.config/mise", "kitty/.config/kitty",
    "swayosd/.config/swayosd", "wireplumber/.config/wireplumber",
)
BASH_HOOK = '[ -r "$HOME/.config/bash/custom.sh" ] && . "$HOME/.config/bash/custom.sh"'
STATE_REL = Path(".local/state/dotfiles-omachy/installs")


class SetupError(Exception):
    pass


def exists(path: Path) -> bool:
    return os.path.lexists(path)


def safe_rel(value: str) -> Path:
    rel = Path(value)
    if rel.is_absolute() or not rel.parts or any(p in (".", "..") for p in rel.parts):
        raise SetupError(f"Unsafe relative path: {value!r}")
    return rel


def check_parents(home: Path, path: Path) -> None:
    """Never follow a target ancestor symlink, including legacy Stow folders."""
    path.relative_to(home)
    for parent in reversed(path.parent.parents):
        if parent == home or home not in parent.parents:
            continue
        if parent.is_symlink() or (exists(parent) and not parent.is_dir()):
            raise SetupError(f"Unsafe parent {parent}. Refusing to write through or replace it.")
    parent = path.parent
    if parent != home and (parent.is_symlink() or (exists(parent) and not parent.is_dir())):
        raise SetupError(f"Unsafe parent {parent}. Refusing to write through or replace it.")


def fingerprint(path: Path) -> dict | None:
    if not exists(path):
        return None
    s = path.lstat()
    result = {"mode": s.st_mode, "ino": s.st_ino, "dev": s.st_dev,
              "size": s.st_size, "mtime_ns": s.st_mtime_ns}
    if stat.S_ISLNK(s.st_mode):
        result["link"] = os.readlink(path)
    elif stat.S_ISREG(s.st_mode):
        result["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    elif not stat.S_ISDIR(s.st_mode):
        raise SetupError(f"Refusing special file: {path}")
    return result


def atomic_bytes(path: Path, data: bytes, mode: int = 0o600) -> None:
    fd, temp = tempfile.mkstemp(prefix=".dotfiles-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as out:
            os.fchmod(out.fileno(), mode)
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
        fsync_dir(path.parent)
    finally:
        if os.path.lexists(temp):
            os.unlink(temp)


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def save_manifest(folder: Path, data: dict) -> None:
    atomic_bytes(folder / "manifest.json", (json.dumps(data, indent=2) + "\n").encode())


def check_source(item: dict) -> None:
    if item["kind"] == "link":
        source = Path(item["source"])
        if not source.is_file() or source.is_symlink() or REPO not in source.resolve().parents:
            raise SetupError(f"Missing or unsafe source: {source}")


def ignored_source(relative: Path, package: str) -> bool:
    # Check every component before walking/validating it. Private directory
    # contents and symlinks must not become install sources either.
    for name in relative.parts:
        if (name in {".git", ".gitignore", ".cache", "node_modules", "__pycache__",
                     ".pytest_cache", ".coverage", ".DS_Store", ".setup-state",
                     "local.sh", "local.conf", "auth.json", ".env"}
                or name.endswith(("~", ".sock", ".pyc", ".pyo", ".pyd")) or ".bak" in name
                or name.startswith((".env.", "credentials", "token", "local."))
                or ".local." in name):
            return True
    if package == "tmux" and "plugins" in relative.parts:
        return True
    if package == "nvim":
        if any(name in {"spell", "nvim", "tags", "test.sh", ".luarc.json"} for name in relative.parts):
            return True
        if "cspell-dicts" in relative.parts and relative.name.startswith("local"):
            return True
    return False


def config_items(home: Path, machine: str) -> list[dict]:
    items = []
    for root_name in ROOTS:
        root = REPO / root_name
        if not root.is_dir() or root.is_symlink() or REPO not in root.resolve().parents:
            raise SetupError(f"Missing or unsafe configuration source: {root}")
        package = root_name.split("/")[0]
        for folder, directories, filenames in os.walk(root, topdown=True, followlinks=False):
            folder = Path(folder)
            directories[:] = sorted(name for name in directories
                                    if not ignored_source((folder / name).relative_to(root), package))
            for name in directories:
                if (folder / name).is_symlink():
                    raise SetupError(f"Source directory symlinks are not portable: {folder / name}")
            for name in sorted(filenames):
                source = folder / name
                if ignored_source(source.relative_to(root), package):
                    continue
                if source.is_symlink():
                    raise SetupError(f"Source symlinks are not portable: {source}")
                if not source.is_file():
                    raise SetupError(f"Source is not a regular file: {source}")
                relative = source.relative_to(REPO / package)
                if str(relative) == ".config/hypr/monitors.conf":
                    continue
                items.append({"path": str(relative), "kind": "link", "source": str(source)})
    items.extend([
        {"path": ".config/hypr/monitors.conf", "kind": "link",
         "source": str(REPO / "profiles" / machine / "monitors.conf")},
        {"path": ".local/bin/smart-close.sh", "kind": "link",
         "source": str(REPO / "bin/smart-close.sh")},
    ])
    if machine == "generic":
        local = home / ".config/hypr/monitors.local.conf"
        if not exists(local):
            check_parents(home, local)
            items.append({"path": ".config/hypr/monitors.local.conf", "kind": "file", "expected_before": None,
                          "content": "# Optional local monitor overrides. This file is not managed after creation.\n"})
    bashrc = home / ".bashrc"
    check_parents(home, bashrc)
    if bashrc.is_symlink() or (exists(bashrc) and not bashrc.is_file()):
        raise SetupError("Refusing to edit a symlink or non-file ~/.bashrc. Add the documented hook manually.")
    bash_before = fingerprint(bashrc)
    old = bashrc.read_bytes() if bash_before is not None else b""
    if (fingerprint(bashrc) != bash_before
            or (bash_before is not None and hashlib.sha256(old).hexdigest() != bash_before["sha256"])):
        raise SetupError("~/.bashrc changed while reading it; retry after the edit finishes")
    hook = BASH_HOOK.encode()
    if hook not in old.splitlines():
        new = old + (b"\n" if old and not old.endswith(b"\n") else b"")
        new += b"\n# Personal dotfiles. Private overrides belong in ~/.config/bash/local.sh.\n" + hook + b"\n"
        items.append({"path": ".bashrc", "kind": "file", "expected_before": bash_before,
                      "content": new.decode("utf-8", errors="surrogateescape")})
    seen = set()
    for item in items:
        safe_rel(item["path"])
        if item["path"] in seen:
            raise SetupError(f"Duplicate destination: {item['path']}")
        seen.add(item["path"])
        check_source(item)
    return items


def matches(path: Path, item: dict) -> bool:
    if item["kind"] == "link":
        return path.is_symlink() and os.readlink(path) == item["source"]
    return path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def plan(home: Path, machine: str, backup: bool) -> list[dict]:
    actions = []
    errors = []
    for item in config_items(home, machine):
        path = home / item["path"]
        # A whole-folder legacy link is harmless only when no write is necessary.
        if item["kind"] == "link" and path.is_file() and path.resolve() == Path(item["source"]).resolve():
            continue
        try:
            check_parents(home, path)
        except SetupError as exc:
            errors.append(str(exc))
            continue
        before = fingerprint(path)
        if "expected_before" in item and before != item["expected_before"]:
            errors.append(f"Destination changed while planning: {path}. Retry without concurrent edits.")
            continue
        if before and stat.S_ISDIR(before["mode"]):
            errors.append(f"Destination is a directory, not a dotfile: {path}")
            continue
        if before and not backup:
            errors.append(f"Conflict: {path}. Use --backup to preserve it before replacement.")
        action = dict(item, before=before, installed=False, restored=False)
        if item["kind"] == "file":
            action["sha256"] = hashlib.sha256(item["content"].encode("utf-8", errors="surrogateescape")).hexdigest()
        actions.append(action)
    for item in actions:
        label = "BACK UP + INSTALL" if item["before"] else "INSTALL"
        print(f"{label}: ~/{item['path']}")
    if errors:
        raise SetupError("\n".join(dict.fromkeys(errors)))
    return actions


def make_dirs(home: Path, path: Path, journal: dict, folder: Path) -> None:
    missing = []
    current = path
    while current != home and not exists(current):
        missing.append(current)
        current = current.parent
    check_parents(home, path / "placeholder")
    for directory in reversed(missing):
        journal["created_dirs"].append(str(directory.relative_to(home)))
        save_manifest(folder, journal)
        directory.mkdir(mode=0o755)
        fsync_dir(directory.parent)


def restore(home: Path, folder: Path, dry_run: bool = False) -> None:
    base = home / STATE_REL
    if folder.is_symlink() or folder.parent != base:
        raise SetupError(f"Restore must name an install directory directly under {base}")
    check_parents(home, folder / "manifest.json")
    manifest_path = folder / "manifest.json"
    if manifest_path.is_symlink():
        raise SetupError("Refusing a symlinked manifest")
    journal = json.loads(manifest_path.read_text())
    if journal.get("version") != 1 or journal.get("home") != str(home):
        raise SetupError("Manifest version or home does not match")
    if journal.get("status") == "restored":
        print("This installation is already restored. No changes needed.")
        return
    actions = journal.get("actions")
    directories = journal.get("created_dirs")
    if not isinstance(actions, list) or not isinstance(directories, list):
        raise SetupError("Malformed action or directory list in manifest")
    seen = set()
    for item in actions:
        if not isinstance(item, dict) or item.get("kind") not in {"link", "file"}:
            raise SetupError("Malformed manifest action")
        rel = safe_rel(item["path"])
        if str(rel) in seen:
            raise SetupError(f"Duplicate manifest destination: {rel}")
        seen.add(str(rel))
    directory_paths = []
    for name in directories:
        directory = home / safe_rel(name)
        if not any(directory in (home / safe_rel(item["path"])).parents for item in actions):
            raise SetupError(f"Unowned created-directory record: {name}")
        check_parents(home, directory)
        directory_paths.append(directory)
    pending = []
    reconciled = []
    for index, item in enumerate(actions):
        path = home / safe_rel(item["path"])
        if path == home / STATE_REL or home / STATE_REL in path.parents:
            raise SetupError("Manifest may not overwrite installer state")
        check_parents(home, path)
        backup = folder / "backups" / str(index)
        check_parents(home, backup)
        if item.get("restored"):
            continue
        backed_up = exists(backup)
        if (item.get("restore_started") and not backed_up
                and fingerprint(path) == item["before"]):
            reconciled.append(item)
            continue
        if backed_up:
            if fingerprint(backup) != item["before"]:
                raise SetupError(f"Protected backup changed: {backup}")
            if backup.is_dir() and not backup.is_symlink():
                raise SetupError(f"Unexpected directory backup: {backup}")
        if not backed_up and not exists(path) and not item.get("installed") and item["before"] is None:
            continue  # A planned creation never began; its parent may not exist.
        # Reconcile a crash between rename/link and the following journal write.
        installed = exists(path) and matches(path, item)
        if exists(path) and not installed:
            if not backed_up and not item.get("installed") and fingerprint(path) == item["before"]:
                continue  # Action never began.
            raise SetupError(f"Changed since install, refusing restore: {path}")
        if item["before"] and not backed_up:
            if not item.get("installed") and not installed:
                continue
            raise SetupError(f"Missing protected backup for {path}")
        pending.append((item, path, backup, installed, backed_up))
    if not dry_run:
        for item in reconciled:
            item["restored"] = True
        if reconciled:
            save_manifest(folder, journal)
    for item, path, backup, installed, backed_up in reversed(pending):
        print(f"RESTORE: ~/{item['path']}")
        if dry_run:
            continue
        check_parents(home, path)
        if exists(path) and not matches(path, item):
            raise SetupError(f"Destination changed during restore: {path}")
        item["restore_started"] = True
        save_manifest(folder, journal)
        if exists(path):
            path.unlink()
        if backed_up:
            os.replace(backup, path)
            fsync_dir(backup.parent)
        fsync_dir(path.parent)
        item["restored"] = True
        save_manifest(folder, journal)
    if not dry_run:
        for directory in reversed(directory_paths):
            check_parents(home, directory)
            with contextlib.suppress(FileNotFoundError, OSError):
                directory.rmdir()  # Never remove nonempty directories.
        journal["status"] = "restored"
        save_manifest(folder, journal)


@contextlib.contextmanager
def locked_state(home: Path):
    state = home / STATE_REL
    check_parents(home, state / "placeholder")
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state, 0o700)
    lock = state / ".lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SetupError("Another dotfiles installation or restore is running") from exc
        yield state
    finally:
        os.close(fd)


def install(home: Path, actions: list[dict]) -> Path | None:
    if not actions:
        print("Already installed. No changes needed.")
        return None
    with locked_state(home) as state:
        for item in actions:
            check_source(item)
            path = home / item["path"]
            check_parents(home, path)
            if fingerprint(path) != item["before"]:
                raise SetupError(f"Destination changed since preflight: {path}")
        name = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
        folder = state / name
        folder.mkdir(mode=0o700)
        (folder / "backups").mkdir(mode=0o700)
        journal = {"version": 1, "home": str(home), "repo": str(REPO), "status": "installing",
                   "created_dirs": [], "actions": actions}
        save_manifest(folder, journal)
        try:
            for index, item in enumerate(actions):
                check_source(item)
                path = home / item["path"]
                make_dirs(home, path.parent, journal, folder)
                if fingerprint(path) != item["before"]:
                    raise SetupError(f"Destination changed during install: {path}")
                if item["before"]:
                    os.replace(path, folder / "backups" / str(index))
                    fsync_dir(path.parent)
                    fsync_dir(folder / "backups")
                if item["kind"] == "link":
                    path.symlink_to(item["source"])
                    fsync_dir(path.parent)
                else:
                    old_mode = stat.S_IMODE(item["before"]["mode"]) if item["before"] else 0o644
                    atomic_bytes(path, item["content"].encode("utf-8", errors="surrogateescape"), old_mode)
                item["installed"] = True
                # The content of a user's .bashrc remains private in the state directory.
                save_manifest(folder, journal)
            journal["status"] = "complete"
            save_manifest(folder, journal)
        except (Exception, KeyboardInterrupt):
            print(f"Installation interrupted. Attempting protected restore from {folder}", file=sys.stderr)
            try:
                restore(home, folder)
            except Exception as error:
                print(f"Automatic restore blocked: {error}. Keep {folder} for recovery.", file=sys.stderr)
            raise
    print(f"Installed. Backup and restore record: {folder}")
    undo = [str(REPO / "setup.sh")]
    if home != Path.home().resolve():
        undo.extend(["--home", str(home)])
    undo.extend(["--restore", str(folder)])
    print("Undo with: " + shlex.join(undo))
    return folder


def package_names(include_apps: bool = False) -> list[str]:
    result = []
    groups = ("desktop", "development", "apps") if include_apps else ("desktop", "development")
    for name in groups:
        path = REPO / "packages" / f"{name}.txt"
        if not path.is_file():
            raise SetupError(f"Missing package manifest: {path}")
        for line in path.read_text().splitlines():
            value = line.split("#", 1)[0].strip()
            if not value:
                continue
            if not re.fullmatch(r"[a-z0-9][a-z0-9@._+\-]*", value):
                raise SetupError(f"Invalid package name in {path}: {value!r}")
            if value not in result:
                result.append(value)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="setup.sh", description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Preview only; create no files and run no package manager")
    parser.add_argument("--backup", action="store_true", help="Back up conflicting files instead of refusing them")
    parser.add_argument("--packages", action="store_true", help="Also install declared Arch/Omarchy packages; no system upgrade")
    parser.add_argument("--apps", action="store_true", help="With --packages, include optional applications used by saved shortcuts")
    parser.add_argument("--machine", choices=("generic", "macmini-t2"), default="generic", help="Monitor profile only; never changes /etc or services")
    parser.add_argument("--home", type=Path, help="Stage config in another existing home; disables package operations and Omarchy checks")
    parser.add_argument("--restore", type=Path, metavar="INSTALL_DIR", help="Undo a recorded installation, refusing to overwrite later changes")
    args = parser.parse_args(argv)
    home = (args.home or Path.home()).absolute()
    if home.is_symlink() or not home.is_dir() or home == Path("/"):
        raise SetupError("Home must be an existing real directory other than /")
    home = home.resolve()
    if args.restore:
        if args.packages or args.apps or args.backup or args.machine != "generic":
            raise SetupError("--restore cannot be combined with installation options")
        folder = args.restore.absolute()
        if args.dry_run:
            restore(home, folder, True)
        else:
            with locked_state(home):
                restore(home, folder)
        return 0
    if args.apps and not args.packages:
        raise SetupError("--apps requires --packages; application installation is always explicit")
    if args.home and args.packages:
        raise SetupError("--packages cannot be used with --home staging")
    if not args.home and not (home / ".local/share/omarchy/default/hypr").is_dir():
        raise SetupError("Install Omarchy first. Use --home DIR only for offline config staging.")
    actions = plan(home, args.machine, args.backup)
    for item in actions:
        target = home / item["path"]
        if target == REPO or REPO in target.parents:
            raise SetupError(f"Refusing a destination inside the source repository: {target}")
    if args.packages:
        packages = package_names(args.apps)
        print("PACKAGES: sudo pacman -S --needed " + " ".join(packages))
        if not args.dry_run:
            if not shutil.which("pacman") or not shutil.which("sudo"):
                raise SetupError("sudo and pacman are required for --packages")
            subprocess.run(["sudo", "pacman", "-S", "--needed", *packages], check=True)
    if args.dry_run:
        print(f"Preview complete. {len(actions)} file change(s); no writes or commands executed.")
        return 0
    install(home, actions)
    print("No desktop reload or service changes were performed. See README.md for optional tools and theme activation.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SetupError, OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"setup: {error}", file=sys.stderr)
        raise SystemExit(1)
