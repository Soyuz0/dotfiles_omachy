"""Black-box coverage of setup.sh. All destinations and HOME are temporary."""
import os
import stat

from support import CliCase, HOOK, REPO, ROOT_FILES, STATE, put, snapshot


class SetupCliTests(CliCase):
    def test_preview_empty_home_writes_nothing(self):
        before = snapshot(self.home)
        result = self.cli('--dry-run')
        self.assertEqual(snapshot(self.home), before)
        self.assertIn('Preview', result.stdout)
        self.assertIn('smart-close.sh', result.stdout)
        self.assertFalse((self.home / STATE).exists())

    def test_preview_backup_does_not_touch_conflicts_or_hook(self):
        put(self.home / '.config/ghostty/config', b'local terminal\n', 0o600)
        put(self.home / '.bashrc', b'export FIXTURE=local\r\n', 0o640)
        before = snapshot(self.home)
        self.cli('--dry-run', '--backup')
        self.assertEqual(snapshot(self.home), before)
        self.assertFalse((self.home / STATE).exists())

    def test_fresh_home_links_all_explicit_roots_and_records_manifest(self):
        self.cli()
        for root, relative in ROOT_FILES.items():
            with self.subTest(root=root):
                self.assert_link(self.home / relative, REPO / root / relative)
        self.assert_link(self.home / '.local/bin/smart-close.sh', REPO / 'bin/smart-close.sh')
        self.assertEqual((self.home / '.bashrc').read_bytes().splitlines().count(HOOK), 1)
        folder = self.install_dir()
        journal = self.read_journal(folder)
        self.assertEqual(journal['home'], str(self.home))
        self.assertEqual(journal['status'], 'complete')
        self.assertTrue(journal['actions'])
        self.assertTrue(all(item['installed'] for item in journal['actions']))
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((folder / 'backups').stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((folder / 'manifest.json').stat().st_mode), 0o600)

    def test_repeat_install_is_noop_and_hook_is_not_duplicated(self):
        self.cli()
        before = snapshot(self.home)
        self.cli()
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual((self.home / '.bashrc').read_bytes().splitlines().count(HOOK), 1)
        self.install_dir()

    def test_existing_bashrc_append_requires_backup_and_restores_original(self):
        original = b'# private shell settings\r\nexport FIXTURE_VALUE=1'
        path = put(self.home / '.bashrc', original, 0o640)
        original_stat = path.stat()
        before = snapshot(self.home)
        result = self.cli(ok=False)
        self.assertIn('--backup', result.stderr)
        self.assertEqual(snapshot(self.home), before)
        self.assertFalse((self.home / STATE).exists())

        self.cli('--backup')
        self.assertTrue(path.read_bytes().startswith(original))
        self.assertEqual(path.read_bytes().splitlines().count(HOOK), 1)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
        folder = self.install_dir()
        journal = self.read_journal(folder)
        index = next(i for i, action in enumerate(journal['actions'])
                     if action['path'] == '.bashrc')
        backup = folder / 'backups' / str(index)
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o640)

        self.cli('--restore', folder)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
        self.assertEqual(path.stat().st_ino, original_stat.st_ino)
        self.assertEqual(path.stat().st_mtime_ns, original_stat.st_mtime_ns)
        self.assertEqual(self.read_journal(folder)['status'], 'restored')

    def test_existing_hook_needs_no_bashrc_write(self):
        original = b'# fixture\r\n' + HOOK + b'\r\n# keep trailing comment\n'
        path = put(self.home / '.bashrc', original, 0o600)
        before = path.stat()
        self.cli()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(path.stat().st_ino, before.st_ino)
        self.assertEqual(path.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertNotIn('.bashrc', [a['path'] for a in self.read_journal()['actions']])

    def test_conflict_refusal_preflights_everything_and_creates_no_state(self):
        put(self.home / '.config/ghostty/config', b'keep terminal settings\n')
        # The second conflict appears late, after many otherwise valid actions.
        put(self.home / '.local/bin/smart-close.sh', b'keep script\n', 0o700)
        before = snapshot(self.home)
        self.cli(ok=False)
        self.assertEqual(snapshot(self.home), before)
        self.assertFalse((self.home / STATE).exists())
        self.assertFalse((self.home / '.bashrc').exists())

    def test_backup_cannot_replace_a_directory_leaf(self):
        put(self.home / '.config/ghostty/config/keep', b'not a dotfile\n')
        before = snapshot(self.home)
        self.cli('--backup', ok=False)
        self.assertEqual(snapshot(self.home), before)
        self.assertFalse((self.home / STATE).exists())

    def test_backup_restore_roundtrip_bytes_modes_and_dangling_leaf_symlink(self):
        file = put(self.home / '.config/ghostty/config', b'original\x00terminal\r\n', 0o640)
        bashrc = put(self.home / '.bashrc', b'# local\r\nexport FIXTURE=1', 0o600)
        dangling = self.home / '.config/git/config'
        dangling.parent.mkdir(parents=True)
        dangling.symlink_to('../../absent fixture target')
        original_file = file.read_bytes()
        original_bashrc = bashrc.read_bytes()
        self.cli('--backup')
        folder = self.install_dir()
        journal = self.read_journal(folder)
        actions = {item['path']: (index, item) for index, item in enumerate(journal['actions'])}
        for relative, expected in [('.config/ghostty/config', original_file), ('.bashrc', original_bashrc)]:
            index, _ = actions[relative]
            self.assertEqual((folder / 'backups' / str(index)).read_bytes(), expected)
        index, _ = actions['.config/git/config']
        self.assertTrue((folder / 'backups' / str(index)).is_symlink())
        self.assertEqual(os.readlink(folder / 'backups' / str(index)), '../../absent fixture target')
        self.cli('--restore', folder)
        self.assertFalse(file.is_symlink())
        self.assertEqual(file.read_bytes(), original_file)
        self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o640)
        self.assertEqual(bashrc.read_bytes(), original_bashrc)
        self.assertEqual(stat.S_IMODE(bashrc.stat().st_mode), 0o600)
        self.assertTrue(dangling.is_symlink())
        self.assertEqual(os.readlink(dangling), '../../absent fixture target')
        self.assertFalse(dangling.exists())
        self.assertEqual(self.read_journal(folder)['status'], 'restored')
        self.assertFalse((self.home / '.local/bin/smart-close.sh').exists())
        before = snapshot(self.home)
        self.cli('--restore', folder)
        self.assertEqual(snapshot(self.home), before)

    def test_fresh_restore_removes_new_files_but_preserves_unrelated_files(self):
        keep = put(self.home / '.config/unrelated/keep', b'untouched\n')
        self.cli()
        self.cli('--restore', self.install_dir())
        self.assertEqual(keep.read_bytes(), b'untouched\n')
        self.assertFalse((self.home / '.bashrc').exists())
        self.assertFalse(os.path.lexists(self.home / '.config/hypr/monitors.conf'))
        self.assertFalse((self.home / '.config/hypr/monitors.local.conf').exists())

    def test_restoring_fresh_install_twice_is_noop(self):
        self.cli()
        folder = self.install_dir()
        self.cli('--restore', folder)
        self.assertEqual(self.read_journal(folder)['status'], 'restored')
        before = snapshot(self.home)
        result = self.cli('--restore', folder)
        self.assertIn('already restored', result.stdout)
        self.assertEqual(snapshot(self.home), before)

    def test_restore_preview_writes_nothing(self):
        self.cli()
        before = snapshot(self.home)
        self.cli('--restore', self.install_dir(), '--dry-run')
        self.assertEqual(snapshot(self.home), before)

    def test_restore_refuses_changed_regular_file_before_any_changes(self):
        self.cli()
        path = self.home / '.config/ghostty/config'
        path.unlink()
        put(path, b'user changed terminal settings\n')
        before = snapshot(self.home)
        self.cli('--restore', self.install_dir(), ok=False)
        self.assertEqual(snapshot(self.home), before)

    def test_restore_refuses_changed_generated_hook_file(self):
        self.cli()
        with (self.home / '.bashrc').open('ab') as stream:
            stream.write(b'# later user change\n')
        before = snapshot(self.home)
        self.cli('--restore', self.install_dir(), ok=False)
        self.assertEqual(snapshot(self.home), before)

    def test_restore_refuses_retargeted_leaf_symlink(self):
        self.cli()
        path = self.home / '.config/ghostty/config'
        path.unlink()
        path.symlink_to(self.base / 'different-source')
        before = snapshot(self.home)
        self.cli('--restore', self.install_dir(), ok=False)
        self.assertEqual(snapshot(self.home), before)

    def test_unsafe_ancestor_symlink_is_never_migrated_even_with_backup(self):
        outside = self.base / 'outside'
        put(outside / 'config', b'outside original\n')
        (self.home / '.config').mkdir()
        (self.home / '.config/ghostty').symlink_to(outside, target_is_directory=True)
        before_home, before_outside = snapshot(self.home), snapshot(outside)
        self.cli('--backup', ok=False)
        self.assertEqual(snapshot(self.home), before_home)
        self.assertEqual(snapshot(outside), before_outside)
        self.assertFalse((self.home / STATE).exists())

    def test_restore_refuses_changed_parent_symlink_without_touching_either_tree(self):
        self.cli()
        directory = self.home / '.config/ghostty'
        outside = self.base / 'moved ghostty'
        directory.rename(outside)
        directory.symlink_to(outside, target_is_directory=True)
        before_home, before_outside = snapshot(self.home), snapshot(outside)
        self.cli('--restore', self.install_dir(), ok=False)
        self.assertEqual(snapshot(self.home), before_home)
        self.assertEqual(snapshot(outside), before_outside)

    def test_symlinked_bashrc_is_not_edited_or_replaced(self):
        outside = put(self.base / 'outside bashrc', b'private fixture\n')
        (self.home / '.bashrc').symlink_to(outside)
        before = snapshot(self.home)
        self.cli('--backup', ok=False)
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(outside.read_bytes(), b'private fixture\n')
        self.assertFalse((self.home / STATE).exists())

    def test_generic_profile_and_local_override_are_separate(self):
        local = put(self.home / '.config/hypr/monitors.local.conf', b'# user monitor override\n')
        self.cli()
        self.assert_link(self.home / '.config/hypr/monitors.conf', REPO / 'profiles/generic/monitors.conf')
        self.assertFalse(local.is_symlink())
        self.assertEqual(local.read_bytes(), b'# user monitor override\n')
        self.cli('--restore', self.install_dir())
        self.assertEqual(local.read_bytes(), b'# user monitor override\n')

    def test_macmini_profile_only_changes_home_mapping(self):
        self.cli('--machine', 'macmini-t2')
        self.assert_link(self.home / '.config/hypr/monitors.conf', REPO / 'profiles/macmini-t2/monitors.conf')
        self.assertFalse((self.home / '.config/hypr/monitors.local.conf').exists())
        destinations = [item['path'] for item in self.read_journal()['actions']]
        self.assertFalse(any('modprobe' in p or 'udev' in p or 'modules-load' in p for p in destinations))
        self.assertFalse((self.home / 'etc').exists())

    def test_private_local_files_stay_local_and_are_not_printed(self):
        secret = b'fixture-private-value-not-a-real-credential-73942\n'
        paths = ['.config/bash/local.sh', '.config/git/local.conf',
                 '.config/mise/config.local.toml', '.config/hypr/monitors.local.conf']
        for relative in paths:
            put(self.home / relative, secret, 0o600)
        result = self.cli('--backup')
        self.assertNotIn(secret.decode().strip(), result.stdout + result.stderr)
        actions = [item['path'] for item in self.read_journal()['actions']]
        for relative in paths:
            self.assertEqual((self.home / relative).read_bytes(), secret)
            self.assertNotIn(relative, actions)

    def test_packages_with_staging_home_is_rejected_without_writes(self):
        for args in [('--packages',), ('--packages', '--dry-run'),
                     ('--packages', '--apps'), ('--packages', '--apps', '--dry-run')]:
            with self.subTest(args=args):
                before = snapshot(self.home)
                self.cli(*args, ok=False)
                self.assertEqual(snapshot(self.home), before)

    def test_package_preview_uses_fake_home_and_never_executes_commands(self):
        # Only the preview path is exercised. Never run a real package operation.
        (self.home / '.local/share/omarchy/default/hypr').mkdir(parents=True)
        before = snapshot(self.home)
        self.cli('--packages', '--dry-run', staged=False)
        self.assertEqual(snapshot(self.home), before)

    def test_apps_without_packages_is_rejected_without_writes(self):
        for staged in (False, True):
            for args in [('--apps',), ('--apps', '--dry-run')]:
                with self.subTest(staged=staged, args=args):
                    before = snapshot(self.home)
                    result = self.cli(*args, staged=staged, ok=False)
                    self.assertIn('--apps requires --packages', result.stderr)
                    self.assertEqual(snapshot(self.home), before)
                    self.assertFalse((self.home / STATE).exists())

    def test_optional_apps_preview_prints_app_names_without_running_providers(self):
        (self.home / '.local/share/omarchy/default/hypr').mkdir(parents=True)
        before = snapshot(self.home)
        default = self.cli('--packages', '--dry-run', staged=False)
        optional = self.cli('--packages', '--apps', '--dry-run', staged=False)
        prefix = 'PACKAGES: sudo pacman -S --needed '
        default_line, = [line for line in default.stdout.splitlines() if line.startswith(prefix)]
        optional_line, = [line for line in optional.stdout.splitlines() if line.startswith(prefix)]
        default_names = set(default_line.removeprefix(prefix).split())
        optional_names = optional_line.removeprefix(prefix).split()
        apps = {line.split('#', 1)[0].strip()
                for line in (REPO / 'packages/apps.txt').read_text().splitlines()}
        apps.discard('')
        self.assertTrue(apps - default_names, 'Expected optional app names beyond the default plan')
        self.assertEqual(set(optional_names), default_names | apps)
        self.assertEqual(len(optional_names), len(set(optional_names)))
        self.assertIn('Preview complete', optional.stdout)
        self.assertEqual(snapshot(self.home), before)
        self.assertFalse((self.home / STATE).exists())

    def test_default_without_omarchy_refuses_without_host_actions(self):
        before = snapshot(self.home)
        self.cli(staged=False, ok=False)
        self.assertEqual(snapshot(self.home), before)

    def test_missing_home_is_rejected_and_not_created(self):
        missing = self.base / 'missing home'
        before = snapshot(self.home)
        self.cli('--home', missing, staged=False, ok=False)
        self.assertFalse(missing.exists())
        self.assertEqual(snapshot(self.home), before)

    def test_home_directory_symlink_is_refused(self):
        alias = self.base / 'alias-home'
        alias.symlink_to(self.home, target_is_directory=True)
        before = snapshot(self.home)
        self.cli('--home', alias, staged=False, ok=False)
        self.assertEqual(snapshot(self.home), before)
        self.assertTrue(alias.is_symlink())

    def test_unknown_machine_fails_before_writes(self):
        before = snapshot(self.home)
        self.cli('--machine', 'unknown', ok=False)
        self.assertEqual(snapshot(self.home), before)

    def test_restore_rejects_incompatible_options_without_writes(self):
        self.cli()
        folder = self.install_dir()
        for args in [('--backup',), ('--packages',), ('--apps',),
                     ('--packages', '--apps'), ('--machine', 'macmini-t2')]:
            with self.subTest(args=args):
                before = snapshot(self.home)
                self.cli('--restore', folder, *args, ok=False)
                self.assertEqual(snapshot(self.home), before)


if __name__ == '__main__':
    import unittest
    unittest.main()
