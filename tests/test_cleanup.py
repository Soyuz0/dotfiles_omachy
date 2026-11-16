"""Fixture-only tests. No installed packages, services or real-home writes."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("scoped_cleanup", REPO / "lib/cleanup.py")
cleanup = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = cleanup
spec.loader.exec_module(cleanup)


class FakeCommands:
    def __init__(self, installed=(), rc=0, remaining=(), hook=None):
        self.installed = set(installed)
        self.rc = rc
        self.remaining = set(remaining)
        self.hook = hook
        self.removals = []
        self.queries = 0

    def inventory(self):
        self.queries += 1
        return set(self.installed)

    def remove(self, packages):
        self.removals.append(tuple(packages))
        self.installed = set(self.remaining)
        if self.hook:
            self.hook()
        return self.rc


def tree(path):
    result = {}
    for entry in sorted(path.rglob("*")):
        info = entry.lstat()
        data = os.readlink(entry) if entry.is_symlink() else entry.read_bytes() if entry.is_file() else None
        result[str(entry.relative_to(path))] = (info.st_mode, data)
    return result


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scoped-cleanup-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir(mode=0o700)
        self.messages = []

    def write(self, relative, data):
        path = self.home / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def desktop(self, name="Zoom", command=None):
        command = command or "omarchy-webapp-handler-zoom %u"
        return self.write(f"{cleanup.APPLICATIONS}/{name}.desktop",
                          f"[Desktop Entry]\nName={name}\nType=Application\nExec={command}\n".encode())

    def engine(self, commands=None, **kwargs):
        return cleanup.Cleanup(self.home, commands or FakeCommands(), system_dirs=(),
                               out=self.messages.append, **kwargs)

    def manifests(self):
        return list((self.home / cleanup.STATE).glob("*/manifest.json"))

    def test_default_and_dry_run_cli_are_read_only_with_inert_pacman(self):
        self.desktop()
        self.write(cleanup.MIME, b"[Default Applications]\nx-scheme-handler/mailto=HEY.desktop;keep.desktop;\n")
        bindir = self.base / "bin"
        bindir.mkdir()
        # Run the actual CLI parser/implementation, but substitute empty fixture-only
        # system desktop roots. The wrapper still has to pass -B and its real args.
        (bindir / "python3").write_text(
            f"#!{sys.executable} -B\nimport sys\nsys.path.insert(0, {str(REPO / 'lib')!r})\n"
            "import cleanup\noriginal = cleanup.Cleanup\n"
            "cleanup.Cleanup = lambda home: original(home, system_dirs=())\n"
            "assert sys.argv[1] == '-B'\n"
            f"assert sys.argv[2] == {str(REPO / 'lib/cleanup.py')!r}\n"
            "sys.exit(cleanup.main(sys.argv[3:]))\n")
        (bindir / "python3").chmod(0o755)
        (bindir / "dirname").write_text('#!/bin/sh\n[ "$1" != -- ] || shift\nprintf "%s\\n" "${1%/*}"\n')
        (bindir / "dirname").chmod(0o755)
        for name in ("pacman", "sudo", "omarchy", "systemctl", "update-desktop-database"):
            script = '#!/bin/sh\nif [ "$0" = "' + str(bindir / "pacman") + '" ] && [ "$#" = 1 ] && [ "$1" = -Qq ]; then printf "spotify\\naether\\ncliamp\\nbluetui\\n"; exit 0; fi\nprintf "FORBIDDEN PROVIDER\\n" >&2\nexit 99\n'
            (bindir / name).write_text(script)
            (bindir / name).chmod(0o755)
        before = tree(self.base)
        env = {**os.environ, "HOME": str(self.home), "PATH": str(bindir), "PYTHONDONTWRITEBYTECODE": "1"}
        for args in ([], ["--dry-run"]):
            result = subprocess.run(["/bin/bash", str(REPO / "setup_cleanup.sh"), *args],
                                    env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Native targets: spotify", result.stdout)
            self.assertIn("Preview only", result.stdout)
            self.assertEqual(result.stderr, "")
            self.assertEqual(tree(self.base), before)

    def test_noop_apply_and_rerun_do_not_write(self):
        engine = self.engine()
        before = tree(self.base)
        self.assertEqual(engine.run(apply=True), 0)
        self.assertEqual(tree(self.base), before)
        self.desktop()
        self.assertEqual(engine.run(apply=True, shortcuts_only=True), 0)
        before = tree(self.base)
        self.assertEqual(engine.run(apply=True, shortcuts_only=True), 0)
        self.assertEqual(tree(self.base), before)
        self.assertEqual(len(self.manifests()), 1)

    def test_exact_names_with_spaces_and_no_app_data_deletion(self):
        for name, hosts in cleanup.WEB.items():
            self.desktop(name, f"omarchy-launch-webapp https://{hosts[0]}/")
        untouched = {}
        for relative in (".config/spotify/prefs", ".config/Signal/state", ".config/alacritty/alacritty.toml",
                         ".local/share/icons/Zoom.png", ".cache/spotify/data", ".config/chromium/Profile 1/History",
                         f"{cleanup.APPLICATIONS}/X Tools.desktop", f"{cleanup.APPLICATIONS}/aether.desktop"):
            data = b"[Desktop Entry]\nType=Application\nName=Unrelated\nExec=unrelated\n" if relative.endswith(".desktop") else b"keep exactly\x00\xff"
            self.write(relative, data)
            untouched[relative] = data
        command = FakeCommands(("spotify", "aether", "cliamp", "bluetui", "snapd"))
        self.assertEqual(self.engine(command).run(apply=True), 0)
        self.assertEqual(command.removals, [("spotify",)])
        for name in cleanup.WEB:
            self.assertFalse((self.home / cleanup.APPLICATIONS / f"{name}.desktop").exists())
        for relative, data in untouched.items():
            self.assertEqual((self.home / relative).read_bytes(), data)

    def test_real_command_adapter_uses_only_fixed_subset_and_plain_R(self):
        for tty, expected in ((True, ["sudo"]), (False, ["sudo", "-n"])):
            with patch.object(cleanup.sys.stdin, "isatty", return_value=tty), patch.object(cleanup.subprocess, "run") as run:
                run.return_value.returncode = 0
                cleanup.Commands().remove(("spotify",))
                self.assertEqual(run.call_args.args[0], expected + ["pacman", "-R", "--noconfirm", "--", "spotify"])
        with patch.object(cleanup.subprocess, "run") as run:
            run.return_value = SimpleNamespace(returncode=0, stdout="spotify\naether\n", stderr="")
            self.assertEqual(cleanup.Commands().inventory(), {"spotify", "aether"})
            self.assertEqual(run.call_args.args[0], ["pacman", "-Qq"])

    def test_native_fixed_installed_subset_and_all_other_packages_untouched(self):
        commands = FakeCommands(("blueberry", "signal-desktop", "aether", "cliamp", "bluetui", "nvidia", "snapd"))
        self.assertEqual(self.engine(commands).run(apply=True), 0)
        self.assertEqual(commands.removals, [("signal-desktop", "blueberry")])
        self.assertEqual(commands.queries, 3)  # preflight, locked preflight, reconciliation

    def test_shortcuts_only_never_queries_or_removes_native_packages(self):
        commands = FakeCommands(("spotify",))
        self.desktop()
        self.assertEqual(self.engine(commands).run(apply=True, shortcuts_only=True), 0)
        self.assertEqual(commands.queries, 0)
        self.assertEqual(commands.removals, [])

    def test_dependency_and_auth_failures_reconcile_once_and_still_clean_shortcut(self):
        for rc in (1, 127):
            with self.subTest(rc=rc):
                self.desktop()
                commands = FakeCommands(("spotify",), rc=rc, remaining=("spotify",))
                self.assertEqual(self.engine(commands).run(apply=True), 1)
                self.assertEqual(commands.removals, [("spotify",)])
                self.assertEqual(commands.queries, 3)
                self.assertFalse((self.home / cleanup.APPLICATIONS / "Zoom.desktop").exists())
                manifest = json.loads(self.manifests()[-1].read_text())
                self.assertEqual(manifest["status"], "partial")
                self.assertEqual(next(e for e in manifest["events"] if e["event"] == "package-result")["remaining"], ["spotify"])
                self.assertIn("normal user terminal", " ".join(self.messages))

    def test_ambiguous_nonzero_but_removed_inventory_is_recorded_without_retry(self):
        commands = FakeCommands(("spotify",), rc=1, remaining=())
        self.assertEqual(self.engine(commands).run(apply=True), 1)
        self.assertEqual(commands.removals, [("spotify",)])
        manifest = json.loads(self.manifests()[0].read_text())
        self.assertEqual(manifest["status"], "partial")
        self.assertEqual(manifest["events"][-1]["remaining"], [])

    def test_rc_zero_with_package_remaining_is_incomplete(self):
        commands = FakeCommands(("spotify",), remaining=("spotify",))
        self.assertEqual(self.engine(commands).run(apply=True), 1)
        self.assertEqual(len(commands.removals), 1)

    def test_inventory_failure_after_removal_is_incomplete_without_retry(self):
        class Broken(FakeCommands):
            def inventory(self):
                if self.removals:
                    raise cleanup.CleanupError("inventory unavailable")
                return super().inventory()
        commands = Broken(("spotify",))
        self.assertEqual(self.engine(commands).run(apply=True), 1)
        self.assertEqual(len(commands.removals), 1)
        manifest = json.loads(self.manifests()[0].read_text())
        self.assertIsNone(manifest["events"][-1]["remaining"])

    def test_invalid_entry_blocks_packages_and_mime_before_any_write(self):
        path = self.desktop("HEY", "firefox https://app.hey.com/")
        self.write(cleanup.MIME, b"[Default Applications]\nx-scheme-handler/mailto=HEY.desktop;keep.desktop;\n")
        commands = FakeCommands(("spotify",))
        before = tree(self.base)
        with self.assertRaisesRegex(cleanup.CleanupError, "Ambiguous"):
            self.engine(commands).run(apply=True)
        self.assertEqual(tree(self.base), before)
        self.assertEqual(commands.removals, [])
        self.assertTrue(path.exists())

    def test_mismatched_Name_duplicate_keys_and_wrong_type_refuse(self):
        path = self.desktop()
        for data in (b"[Desktop Entry]\nName=Other\nType=Application\nExec=omarchy-webapp-handler-zoom %u\n",
                     b"[Desktop Entry]\nName=Zoom\nName=Zoom\nType=Application\nExec=omarchy-webapp-handler-zoom %u\n",
                     b"[Desktop Entry]\nName=Zoom\nType=Link\nExec=omarchy-webapp-handler-zoom %u\n"):
            path.write_bytes(data)
            before = tree(self.base)
            with self.assertRaises(cleanup.CleanupError):
                self.engine().run(apply=True)
            self.assertEqual(tree(self.base), before)

    def test_Name_alias_collision_blocks_even_absent_exact_entry_and_MIME(self):
        self.write(f"{cleanup.APPLICATIONS}/other.desktop", b"[Desktop Entry]\nName=HEY\nType=Application\nExec=anything\n")
        self.write(cleanup.MIME, b"[Default Applications]\nx-scheme-handler/mailto=HEY.desktop;\n")
        before = tree(self.base)
        with self.assertRaisesRegex(cleanup.CleanupError, "alias"):
            self.engine().run(apply=True)
        self.assertEqual(tree(self.base), before)

    def test_symlink_entry_parent_home_and_state_are_refused(self):
        outside = self.base / "outside"
        outside.mkdir()
        for relative in (f"{cleanup.APPLICATIONS}/Zoom.desktop", cleanup.APPLICATIONS, cleanup.STATE):
            with self.subTest(relative=relative):
                # Use a fresh fixture home for each path.
                self.home = self.base / ("home-" + str(len(list(self.base.iterdir()))))
                self.home.mkdir(mode=0o700)
                path = self.home / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(outside)
                before = tree(self.base)
                with self.assertRaises((OSError, cleanup.CleanupError)):
                    self.engine(FakeCommands(("spotify",))).run(apply=True)
                self.assertEqual(tree(self.base), before)
        link = self.base / "home-link"
        link.symlink_to(self.home)
        with self.assertRaises(cleanup.CleanupError):
            cleanup.Cleanup(link, FakeCommands(), system_dirs=())

    def test_unowned_regular_file_refused(self):
        path = self.desktop()
        inode = path.stat().st_ino
        original = cleanup.os.fstat
        def changed_owner(fd):
            info = original(fd)
            if info.st_ino == inode:
                return SimpleNamespace(st_mode=info.st_mode, st_uid=os.getuid() + 1, st_nlink=1)
            return info
        with patch.object(cleanup.os, "fstat", side_effect=changed_owner):
            with self.assertRaisesRegex(cleanup.CleanupError, "owned"):
                self.engine().run(apply=True)
        self.assertTrue(path.exists())
        self.assertFalse(self.manifests())

    def test_hardlink_and_special_file_refused(self):
        path = self.desktop()
        os.link(path, self.base / "hardlink")
        with self.assertRaises(cleanup.CleanupError):
            self.engine().run(apply=True)
        path.unlink()
        os.mkfifo(path)
        with self.assertRaises(cleanup.CleanupError):
            self.engine().run(apply=True)

    def test_changed_after_package_operation_preserved_and_partial(self):
        path = self.desktop()
        changed = b"new unrelated content\n"
        commands = FakeCommands(("spotify",), hook=lambda: path.write_bytes(changed))
        self.assertEqual(self.engine(commands).run(apply=True), 1)
        self.assertEqual(path.read_bytes(), changed)
        manifest = json.loads(self.manifests()[0].read_text())
        self.assertEqual(manifest["status"], "partial")
        self.assertIn("Changed since preflight", manifest["problems"][0])

    def test_changed_at_last_CAS_preserved(self):
        path = self.desktop()
        class Changed(cleanup.Cleanup):
            def mutate(inner, relative, expected, replacement, journal):
                path.write_bytes(b"concurrent replacement")
                return super().mutate(relative, expected, replacement, journal)
        engine = Changed(self.home, FakeCommands(), system_dirs=(), out=self.messages.append)
        self.assertEqual(engine.run(apply=True), 1)
        self.assertEqual(path.read_bytes(), b"concurrent replacement")
        self.assertEqual(json.loads(self.manifests()[0].read_text())["status"], "failed")

    def test_backup_bytes_modes_intents_and_MIME_preservation(self):
        desktop = self.desktop()
        original_desktop = desktop.read_bytes()
        desktop_mode = desktop.stat().st_mode
        original = (b"# keep comment\r\n[Default Applications]\r\n"
                    b"x-scheme-handler/mailto=HEY.desktop;keep.desktop;other.desktop;\r\n"
                    b"application/foo=notHEY.desktop;X.desktop.extra;\r\n"
                    b"[Added Associations]\ntext/plain=before.desktop;Google Maps.desktop;after.desktop;\n"
                    b"[Removed Associations]\nimage/png=Zoom.desktop;\n"
                    b"[Unrelated]\nkey=HEY.desktop;\n# HEY.desktop; remains\n")
        expected = original.replace(b"mailto=HEY.desktop;", b"mailto=").replace(b";Google Maps.desktop;", b";").replace(b"image/png=Zoom.desktop;", b"image/png=")
        mime = self.write(cleanup.MIME, original)
        mime.chmod(0o640)
        self.assertEqual(self.engine().run(apply=True, shortcuts_only=True), 0)
        self.assertEqual(mime.read_bytes(), expected)
        self.assertEqual(stat.S_IMODE(mime.stat().st_mode), 0o640)
        manifest_path = self.manifests()[0]
        journal = manifest_path.parent
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(stat.S_IMODE(journal.stat().st_mode), 0o700)
        for entry in journal.iterdir():
            if not entry.name.endswith(".held"):
                self.assertEqual(stat.S_IMODE(entry.stat().st_mode), 0o600)
        for relative, item in manifest["files"].items():
            before = original if relative == cleanup.MIME else original_desktop
            self.assertEqual((journal / item["backup"]).read_bytes(), before)
            held = journal / item["held"]
            self.assertEqual(held.read_bytes(), before)
            self.assertEqual(stat.S_IMODE(held.stat().st_mode), 0o640 if relative == cleanup.MIME else stat.S_IMODE(desktop_mode))
        self.assertEqual([e["event"] for e in manifest["events"]], [
            "file-intent", "capture-intent", "capture-held", "file-complete",
            "file-intent", "capture-intent", "capture-held", "publish-intent", "file-complete"])

    def test_absent_HEY_allows_only_exact_MIME_tokens(self):
        data = b"[Default Applications]\na=HEY.desktop;HEY.desktop.backup;hey.desktop;keep.desktop;\n"
        mime = self.write(cleanup.MIME, data)
        self.assertEqual(self.engine().run(apply=True, shortcuts_only=True), 0)
        self.assertEqual(mime.read_bytes(), data.replace(b"a=HEY.desktop;", b"a="))

    def test_system_desktop_reported_but_not_removed_or_masked(self):
        system = self.base / "system-applications"
        system.mkdir()
        (system / "Zoom.desktop").write_bytes(b"[Desktop Entry]\nName=Zoom\nType=Application\nExec=anything\n")
        before = tree(self.base)
        engine = cleanup.Cleanup(self.home, FakeCommands(("spotify",)), system_dirs=(system,), out=self.messages.append)
        with self.assertRaisesRegex(cleanup.CleanupError, "Unsupported system desktop"):
            engine.run(apply=True)
        self.assertEqual(tree(self.base), before)

    def test_durable_intent_and_backup_exist_before_native_removal(self):
        path = self.desktop()
        original = path.read_bytes()
        def inspect_before_removal():
            manifest_path, = self.manifests()
            manifest = json.loads(manifest_path.read_text())
            self.assertEqual(manifest["status"], "intent")
            self.assertEqual(manifest["events"][-1]["event"], "package-intent")
            item = manifest["files"][f"{cleanup.APPLICATIONS}/Zoom.desktop"]
            self.assertEqual((manifest_path.parent / item["backup"]).read_bytes(), original)
            self.assertEqual(path.read_bytes(), original)
        commands = FakeCommands(("spotify",), hook=inspect_before_removal)
        self.assertEqual(self.engine(commands).run(apply=True), 0)

    def test_unsafe_state_conflict_prevents_native_and_file_changes(self):
        self.desktop()
        self.write(cleanup.STATE, b"not a directory")
        commands = FakeCommands(("spotify",))
        before = tree(self.base)
        with self.assertRaises((OSError, cleanup.CleanupError)):
            self.engine(commands).run(apply=True)
        self.assertEqual(commands.removals, [])
        self.assertEqual(tree(self.base), before)

    def test_new_Name_collision_after_native_removal_blocks_file_cleanup(self):
        path = self.desktop()
        original = path.read_bytes()
        def add_collision():
            self.write(f"{cleanup.APPLICATIONS}/Zoom alias.desktop", original)
        commands = FakeCommands(("spotify",), hook=add_collision)
        self.assertEqual(self.engine(commands).run(apply=True), 1)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(json.loads(self.manifests()[0].read_text())["status"], "partial")

    def held_record(self, relative):
        manifest_path, = self.manifests()
        manifest = json.loads(manifest_path.read_text())
        held = manifest_path.parent / manifest["files"][relative]["held"]
        return manifest, held

    def test_changed_zoom_at_capture_boundary_is_restored_and_actual_inode_retained(self):
        path = self.desktop()
        relative = f"{cleanup.APPLICATIONS}/Zoom.desktop"
        original = path.read_bytes()
        changed = b"[Desktop Entry]\nName=Unrelated\nType=Application\nExec=unrelated\n"
        original_rename = cleanup.rename_noreplace
        def concurrent_write(source_fd, source, target_fd, target):
            if source == "Zoom.desktop":
                path.write_bytes(changed)
            return original_rename(source_fd, source, target_fd, target)
        with patch.object(cleanup, "rename_noreplace", side_effect=concurrent_write):
            self.assertEqual(self.engine().run(apply=True, shortcuts_only=True), 1)
        manifest, held = self.held_record(relative)
        self.assertEqual(manifest["status"], "partial")
        self.assertEqual(path.read_bytes(), changed)
        self.assertEqual(held.read_bytes(), changed)
        self.assertEqual(path.stat().st_ino, held.stat().st_ino)
        self.assertEqual((held.parent / manifest["files"][relative]["backup"]).read_bytes(), original)
        self.assertEqual(manifest["events"][-1]["outcome"], "linked-if-absent")
        self.assertNotIn("file-complete", [e["event"] for e in manifest["events"]])

    def test_new_inode_with_identical_bytes_at_capture_is_not_accepted(self):
        path = self.desktop()
        original = path.read_bytes()
        old_inode = path.stat().st_ino
        original_rename = cleanup.rename_noreplace
        def replace_inode(source_fd, source, target_fd, target):
            if source == "Zoom.desktop":
                new_file = self.base / "new-desktop"
                new_file.write_bytes(original)
                os.replace(new_file, path)
            return original_rename(source_fd, source, target_fd, target)
        with patch.object(cleanup, "rename_noreplace", side_effect=replace_inode):
            self.assertEqual(self.engine().run(apply=True, shortcuts_only=True), 1)
        manifest, held = self.held_record(f"{cleanup.APPLICATIONS}/Zoom.desktop")
        self.assertEqual(manifest["status"], "partial")
        self.assertNotEqual(held.stat().st_ino, old_inode)
        self.assertEqual(path.stat().st_ino, held.stat().st_ino)
        self.assertEqual(held.read_bytes(), original)

    def test_new_mailto_choice_at_capture_is_not_overwritten(self):
        original = b"[Default Applications]\nx-scheme-handler/mailto=HEY.desktop;keep.desktop;\n"
        changed = b"[Default Applications]\nx-scheme-handler/mailto=new-user-choice.desktop;\n"
        path = self.write(cleanup.MIME, original)
        original_rename = cleanup.rename_noreplace
        def concurrent_choice(source_fd, source, target_fd, target):
            if source == "mimeapps.list":
                path.write_bytes(changed)
            return original_rename(source_fd, source, target_fd, target)
        with patch.object(cleanup, "rename_noreplace", side_effect=concurrent_choice):
            self.assertEqual(self.engine().run(apply=True, shortcuts_only=True), 1)
        manifest, held = self.held_record(cleanup.MIME)
        self.assertEqual(path.read_bytes(), changed)
        self.assertEqual(held.read_bytes(), changed)
        self.assertEqual(path.stat().st_ino, held.stat().st_ino)
        self.assertEqual(manifest["status"], "partial")
        self.assertNotIn("file-complete", [e["event"] for e in manifest["events"]])

    def test_new_file_immediately_before_mime_publication_wins(self):
        original = b"[Default Applications]\nx-scheme-handler/mailto=HEY.desktop;keep.desktop;\n"
        changed = b"[Default Applications]\nx-scheme-handler/mailto=latest-user-choice.desktop;\n"
        path = self.write(cleanup.MIME, original)
        old_inode = path.stat().st_ino
        original_rename = cleanup.rename_noreplace
        def create_before_publish(source_fd, source, target_fd, target):
            if source.endswith(".authored"):
                self.assertFalse(path.exists())
                path.write_bytes(changed)
            return original_rename(source_fd, source, target_fd, target)
        with patch.object(cleanup, "rename_noreplace", side_effect=create_before_publish):
            self.assertEqual(self.engine().run(apply=True, shortcuts_only=True), 1)
        manifest, held = self.held_record(cleanup.MIME)
        self.assertEqual(path.read_bytes(), changed)
        self.assertEqual(held.read_bytes(), original)
        self.assertEqual(held.stat().st_ino, old_inode)
        self.assertNotEqual(path.stat().st_ino, held.stat().st_ino)
        self.assertEqual(manifest["status"], "partial")
        self.assertEqual(manifest["events"][-1]["outcome"], "occupied-preserved-both")
        self.assertNotIn("file-complete", [e["event"] for e in manifest["events"]])

    def test_restore_never_overwrites_file_created_at_its_link_boundary(self):
        path = self.desktop()
        changed = b"changed at capture"
        newer = b"new file created before restore"
        original_rename = cleanup.rename_noreplace
        original_link = cleanup.os.link
        def change_before_capture(source_fd, source, target_fd, target):
            if source == "Zoom.desktop":
                path.write_bytes(changed)
            return original_rename(source_fd, source, target_fd, target)
        def create_before_restore(*args, **kwargs):
            self.assertFalse(path.exists())
            path.write_bytes(newer)
            return original_link(*args, **kwargs)
        with patch.object(cleanup, "rename_noreplace", side_effect=change_before_capture), patch.object(cleanup.os, "link", side_effect=create_before_restore):
            self.assertEqual(self.engine().run(apply=True, shortcuts_only=True), 1)
        manifest, held = self.held_record(f"{cleanup.APPLICATIONS}/Zoom.desktop")
        self.assertEqual(path.read_bytes(), newer)
        self.assertEqual(held.read_bytes(), changed)
        self.assertEqual(manifest["status"], "partial")
        self.assertEqual(manifest["events"][-1]["outcome"], "occupied-preserved-both")

    def test_open_writer_can_change_claimed_inode_without_losing_its_bytes(self):
        path = self.desktop()
        changed = b"written through an open fd after capture\n"
        fd = os.open(path, os.O_WRONLY | os.O_TRUNC)
        # Populate before preflight so the authorized contents remain valid.
        os.write(fd, b"[Desktop Entry]\nName=Zoom\nType=Application\nExec=omarchy-webapp-handler-zoom %u\n")
        original_rename = cleanup.rename_noreplace
        def write_after_capture(source_fd, source, target_fd, target):
            result = original_rename(source_fd, source, target_fd, target)
            if source == "Zoom.desktop":
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, changed)
                os.ftruncate(fd, len(changed))
            return result
        try:
            with patch.object(cleanup, "rename_noreplace", side_effect=write_after_capture):
                self.assertEqual(self.engine().run(apply=True, shortcuts_only=True), 1)
        finally:
            os.close(fd)
        manifest, held = self.held_record(f"{cleanup.APPLICATIONS}/Zoom.desktop")
        self.assertEqual(held.read_bytes(), changed)
        self.assertEqual(path.read_bytes(), changed)
        self.assertEqual(manifest["status"], "partial")

    def test_success_never_unlinks_captured_inode_even_for_late_open_fd_write(self):
        path = self.desktop()
        inode = path.stat().st_ino
        fd = os.open(path, os.O_WRONLY)
        original_unlink = cleanup.os.unlink
        def no_user_unlink(name, *args, **kwargs):
            self.assertNotEqual(name, "Zoom.desktop")
            self.assertFalse(str(name).endswith(".held"))
            return original_unlink(name, *args, **kwargs)
        try:
            with patch.object(cleanup.os, "unlink", side_effect=no_user_unlink):
                self.assertEqual(self.engine().run(apply=True, shortcuts_only=True), 0)
            manifest, held = self.held_record(f"{cleanup.APPLICATIONS}/Zoom.desktop")
            self.assertEqual(held.stat().st_ino, inode)
            later = b"later write after the final observation\n"
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, later)
            os.ftruncate(fd, len(later))
            self.assertEqual(held.read_bytes(), later)
            self.assertFalse(path.exists())
            self.assertEqual(manifest["status"], "complete")  # Not a perpetual writer lock.
        finally:
            os.close(fd)

    def test_cross_filesystem_capture_refused_before_native_or_file_mutation(self):
        self.desktop()
        commands = FakeCommands(("spotify",))
        engine = self.engine(commands)
        before = tree(self.base)
        with patch.object(engine.home, "existing_device", return_value=self.home.stat().st_dev + 1), patch.object(cleanup, "rename_noreplace") as rename:
            with self.assertRaisesRegex(cleanup.CleanupError, "Cross-filesystem"):
                engine.run(apply=True)
        rename.assert_not_called()
        self.assertEqual(commands.removals, [])
        self.assertEqual(commands.queries, 0)
        self.assertEqual(tree(self.base), before)

    def test_exec_validation_is_not_substring_or_shell_matching(self):
        for command in ("echo omarchy-webapp-handler-zoom %u", "sh -c 'omarchy-launch-webapp https://zoom.us'",
                        "omarchy-launch-webapp https://evil.invalid/", "omarchy-webapp-handler-zoom-other %u",
                        "omarchy-launch-webapp https://zoom.us/ --extra", "'/tmp/omarchy-webapp-handler-zoom' %u"):
            self.assertFalse(cleanup.recognized_exec("Zoom", command), command)
        self.assertTrue(cleanup.recognized_exec("Zoom", "omarchy-webapp-handler-zoom %u"))

    def test_cli_flags_reject_staging_home_and_conflicting_actions(self):
        for args in (("--home", str(self.home)), ("--dry-run", "--apply"), ("--all",)):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                cleanup.main(args)
            self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
